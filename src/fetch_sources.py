cat > src/fetch_sources.py << 'EOF'
import re
import json
import time
import gzip
import io
from pathlib import Path
import xml.etree.ElementTree as ET

import yaml
import requests
import pandas as pd
from bs4 import BeautifulSoup
import trafilatura

ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / "config" / "sources.yaml"
SEEN_PATH = ROOT / "data" / "seen_urls.json"
POSTS_PATH = ROOT / "data" / "posts.csv"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; InosearchIntelBot/0.2.1; +https://inosearch.fr)"
}

def load_sources():
    with open(CFG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("sources", [])

def load_seen():
    if SEEN_PATH.exists():
        return set(json.loads(SEEN_PATH.read_text(encoding="utf-8")))
    return set()

def save_seen(seen: set[str]):
    SEEN_PATH.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")

def ensure_posts_csv():
    if not POSTS_PATH.exists():
        df = pd.DataFrame(columns=[
            "platform","competitor","author","date","url","content","likes","comments","reposts"
        ])
        df.to_csv(POSTS_PATH, index=False)

def append_posts(rows: list[dict]):
    if not rows:
        return
    df_new = pd.DataFrame(rows)
    df_old = pd.read_csv(POSTS_PATH)
    df_all = pd.concat([df_old, df_new], ignore_index=True)
    df_all.to_csv(POSTS_PATH, index=False)

def fetch_bytes(url: str) -> bytes:
    r = requests.get(url, headers=DEFAULT_HEADERS, timeout=30)
    r.raise_for_status()
    return r.content

def fetch_text(url: str) -> str:
    return fetch_bytes(url).decode("utf-8", errors="replace")

def extract_links_from_list(html: str, include_regex: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    pattern = re.compile(include_regex)
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("/"):
            href = base_url.rstrip("/") + href
        if pattern.match(href):
            links.append(href.split("#")[0])
    # de-dup preserving order
    out, seen = [], set()
    for u in links:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

def discover_sitemaps(base_url: str) -> list[str]:
    """
    Try:
    - robots.txt Sitemap: lines
    - common sitemap endpoints
    """
    sitemaps = []

    # 1) robots.txt
    robots_url = base_url.rstrip("/") + "/robots.txt"
    try:
        txt = fetch_text(robots_url)
        for line in txt.splitlines():
            if line.lower().startswith("sitemap:"):
                sm = line.split(":", 1)[1].strip()
                if sm:
                    sitemaps.append(sm)
    except Exception:
        pass

    # 2) common endpoints
    for p in ["/sitemap.xml", "/sitemap_index.xml", "/sitemap.xml.gz", "/sitemap-index.xml"]:
        sitemaps.append(base_url.rstrip("/") + p)

    # de-dup preserving order
    out, seen = [], set()
    for u in sitemaps:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

def parse_sitemap_urls(sitemap_url: str, max_urls: int = 5000) -> list[str]:
    """
    Supports sitemapindex and urlset, gz or plain xml.
    Returns a list of URLs (loc).
    """
    try:
        content = fetch_bytes(sitemap_url)
    except Exception:
        return []

    # gunzip if needed
    if sitemap_url.endswith(".gz"):
        try:
            content = gzip.GzipFile(fileobj=io.BytesIO(content)).read()
        except Exception:
            return []

    try:
        root = ET.fromstring(content)
    except Exception:
        return []

    # Handle namespaces
    def strip_ns(tag: str) -> str:
        return tag.split("}", 1)[-1] if "}" in tag else tag

    tag = strip_ns(root.tag)

    urls = []
    if tag == "sitemapindex":
        # recurse into sub-sitemaps
        for sm in root.findall(".//{*}sitemap/{*}loc"):
            loc = sm.text.strip() if sm.text else ""
            if loc:
                urls.extend(parse_sitemap_urls(loc, max_urls=max_urls))
            if len(urls) >= max_urls:
                break
    elif tag == "urlset":
        for loc_el in root.findall(".//{*}url/{*}loc"):
            loc = loc_el.text.strip() if loc_el.text else ""
            if loc:
                urls.append(loc)
            if len(urls) >= max_urls:
                break

    # de-dup
    out, seen = [], set()
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

def links_from_sitemap(base_url: str, include_regex: str) -> list[str]:
    pattern = re.compile(include_regex)
    candidates = []
    for sm in discover_sitemaps(base_url):
        urls = parse_sitemap_urls(sm)
        for u in urls:
            if pattern.match(u):
                candidates.append(u.split("#")[0])
        if candidates:
            break  # stop at first sitemap source that yields results
    # de-dup preserving order
    out, seen = [], set()
    for u in candidates:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

def extract_article(url: str) -> dict:
    html = fetch_text(url)

    downloaded = trafilatura.fetch_url(url)
    if downloaded is None:
        downloaded = html

    extracted = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
    if extracted is None:
        extracted = ""

    soup = BeautifulSoup(html, "lxml")

    title = soup.title.text.strip() if soup.title and soup.title.text else ""
    date_iso = ""

    meta = soup.find("meta", attrs={"property": "article:published_time"})
    if meta and meta.get("content"):
        date_iso = meta["content"][:10]
    if not date_iso:
        meta = soup.find("meta", attrs={"name": "date"})
        if meta and meta.get("content"):
            date_iso = meta["content"][:10]

    return {"title": title, "date": date_iso, "content": extracted.strip()}

def main():
    sources = load_sources()
    seen = load_seen()
    ensure_posts_csv()

    total_new = 0

    for src in sources:
        name = src["name"]
        url = src["url"]
        base_url = src.get("base_url", "https://leyton.com")
        include_regex = src.get("include_url_regex", ".*")

        print(f"[fetch] Source={name} type=html_list url={url}")

        links = []
        # 1) try HTML list
        try:
            list_html = fetch_text(url)
            links = extract_links_from_list(list_html, include_regex, base_url)
        except Exception as e:
            print(f"[warn] Cannot fetch/parse list page: {e}")

        # 2) fallback to sitemap if needed
        if len(links) == 0:
            print("[fetch] Found 0 candidate links via HTML list; trying sitemap fallback...")
            links = links_from_sitemap(base_url, include_regex)

        print(f"[fetch] Found {len(links)} candidate links")
        new_links = [u for u in links if u not in seen]
        print(f"[fetch] New links this run: {len(new_links)}")

        rows = []
        for u in new_links:
            try:
                art = extract_article(u)
                content = art["content"]
                if not content or len(content) < 200:
                    print(f"[skip] Low content extracted for {u}")
                    seen.add(u)
                    continue

                rows.append({
                    "platform": "web",
                    "competitor": name,
                    "author": "",
                    "date": art["date"] or "",
                    "url": u,
                    "content": content,
                    "likes": 0,
                    "comments": 0,
                    "reposts": 0,
                })
                seen.add(u)
                total_new += 1
                time.sleep(0.4)
            except Exception as e:
                print(f"[warn] Failed article {u}: {e}")

        append_posts(rows)

    save_seen(seen)
    print(f"OK — New items appended: {total_new}")
    print(f"OK — Seen URLs stored: {SEEN_PATH}")

if __name__ == "__main__":
    main()
EOF
