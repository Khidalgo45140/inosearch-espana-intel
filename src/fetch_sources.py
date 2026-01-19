import re
import json
import time
from pathlib import Path
from datetime import datetime
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
    "User-Agent": "Mozilla/5.0 (compatible; InosearchIntelBot/0.2; +https://inosearch.fr)"
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

def fetch_url(url: str) -> str:
    r = requests.get(url, headers=DEFAULT_HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def extract_links_from_list(html: str, include_regex: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    pattern = re.compile(include_regex)
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("/"):
            href = "https://leyton.com" + href
        if pattern.match(href):
            links.append(href.split("#")[0])
    # de-dup conservant ordre
    out = []
    seen = set()
    for u in links:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

def extract_article_text(url: str) -> dict:
    html = fetch_url(url)
    downloaded = trafilatura.fetch_url(url)  # may return None depending on environment
    if downloaded is None:
        downloaded = html
    extracted = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
    title = ""
    if extracted is None:
        extracted = ""
    # best-effort title from HTML
    soup = BeautifulSoup(html, "lxml")
    if soup.title and soup.title.text:
        title = soup.title.text.strip()
    # date: best effort (metadata)
    date_iso = ""
    # try meta property/article:published_time
    meta = soup.find("meta", attrs={"property": "article:published_time"})
    if meta and meta.get("content"):
        date_iso = meta["content"][:10]
    if not date_iso:
        meta = soup.find("meta", attrs={"name": "date"})
        if meta and meta.get("content"):
            date_iso = meta["content"][:10]

    return {
        "title": title,
        "date": date_iso,
        "content": extracted.strip(),
    }

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

def main():
    sources = load_sources()
    seen = load_seen()
    ensure_posts_csv()

    total_new = 0
    for src in sources:
        name = src["name"]
        src_type = src["type"]
        url = src["url"]
        include_regex = src.get("include_url_regex", ".*")

        print(f"[fetch] Source={name} type={src_type} url={url}")
        try:
            list_html = fetch_url(url)
        except Exception as e:
            print(f"[warn] Cannot fetch list page: {e}")
            continue

        if src_type != "html_list":
            print(f"[warn] Unsupported source type in V0.2: {src_type}")
            continue

        links = extract_links_from_list(list_html, include_regex)
        # heuristique : exclure la page liste elle-même
        links = [u for u in links if u.rstrip("/") != url.rstrip("/")]
        print(f"[fetch] Found {len(links)} candidate links")

        new_links = [u for u in links if u not in seen]
        print(f"[fetch] New links this run: {len(new_links)}")

        rows = []
        for u in new_links:
            try:
                art = extract_article_text(u)
                content = art["content"]
                if not content or len(content) < 200:
                    # si extraction trop faible, on ne garde pas (évite bruit)
                    print(f"[skip] Low content extracted for {u}")
                    seen.add(u)  # mark seen to avoid retry loops; can revise later
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
                time.sleep(0.5)  # politeness
            except Exception as e:
                print(f"[warn] Failed article {u}: {e}")

        append_posts(rows)

    save_seen(seen)
    print(f"OK — New items appended: {total_new}")
    print(f"OK — Seen URLs stored: {SEEN_PATH}")

if __name__ == "__main__":
    main()
