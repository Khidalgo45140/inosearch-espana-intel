import re
import yaml
import pandas as pd
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "posts.csv"
CFG_PATH = ROOT / "config" / "keywords.yaml"
REPORTS_DIR = ROOT / "reports"

def normalize(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text

def contains_any(text: str, keywords: list[str]) -> bool:
    for kw in keywords:
        kw_n = normalize(kw)
        if kw_n and kw_n in text:
            return True
    return False

def load_config():
    with open(CFG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_posts():
    df = pd.read_csv(DATA_PATH)
    # Ensure expected columns exist
    expected = ["platform","competitor","author","date","url","content","likes","comments","reposts"]
    for col in expected:
        if col not in df.columns:
            df[col] = ""
    # Normalize numerics
    for c in ["likes","comments","reposts"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    df["content_norm"] = df["content"].apply(normalize)
    return df

def assign_categories(df, cfg):
    categories = cfg.get("categories", {})
    cat_names = []
    for _, row in df.iterrows():
        text = row["content_norm"]
        matched = []
        for cat_key, cat in categories.items():
            kws = cat.get("keywords", [])
            if contains_any(text, kws):
                matched.append(cat.get("label", cat_key))
        cat_names.append(matched if matched else ["(non classé)"])
    df["categories"] = cat_names
    return df

def assign_formats(df, cfg):
    formats = cfg.get("formats", {})
    fmt_names = []
    for _, row in df.iterrows():
        text = row["content_norm"]
        matched = []
        for fmt_key, fmt in formats.items():
            kws = fmt.get("keywords", [])
            if contains_any(text, kws):
                matched.append(fmt_key)
        fmt_names.append(matched if matched else ["(non détecté)"])
    df["formats"] = fmt_names
    return df

def score_engagement(df):
    # Simple weighted score (modifiable later)
    df["engagement_score"] = df["likes"] + 2*df["comments"] + 3*df["reposts"]
    return df

def build_report(df, cfg) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = len(df)

    # Top posts
    top = df.sort_values("engagement_score", ascending=False).head(10)

    # Category counts
    cat_exploded = df.explode("categories")
    cat_counts = cat_exploded["categories"].value_counts()

    # Format counts
    fmt_exploded = df.explode("formats")
    fmt_counts = fmt_exploded["formats"].value_counts()

    lines = []
    lines.append(f"# Inosearch España — Veille & Analyse (V0)")
    lines.append(f"_Généré le {now}_")
    lines.append("")
    lines.append(f"## 1) Volume analysé")
    lines.append(f"- Posts analysés : **{total}**")
    lines.append("")

    lines.append("## 2) Répartition par thématique (mots-clés)")
    for cat, cnt in cat_counts.items():
        lines.append(f"- **{cat}** : {int(cnt)}")
    lines.append("")

    lines.append("## 3) Répartition par format (détection simple)")
    for fmt, cnt in fmt_counts.items():
        lines.append(f"- **{fmt}** : {int(cnt)}")
    lines.append("")

    lines.append("## 4) Top posts (score = likes + 2×comments + 3×reposts)")
    lines.append("")
    lines.append("| Rang | Plateforme | Concurrent | Date | Catégories | Formats | Score | Extrait |")
    lines.append("|---:|---|---|---|---|---|---:|---|")
    for i, row in enumerate(top.itertuples(index=False), start=1):
        cats = ", ".join(getattr(row, "categories"))
        fmts = ", ".join(getattr(row, "formats"))
        snippet = str(getattr(row, "content"))[:120].replace("\n", " ")
        score = int(getattr(row, "engagement_score"))
        platform = getattr(row, "platform")
        comp = getattr(row, "competitor")
        date = getattr(row, "date")
        lines.append(f"| {i} | {platform} | {comp} | {date} | {cats} | {fmts} | {score} | {snippet} |")
    lines.append("")

    lines.append("## 5) Angles recommandés (première passe)")
    lines.append("- Identifier 3 sujets à forte traction chez les concurrents, puis produire une version **Inosearch** (cadre méthodo + erreurs fréquentes + CTA diagnostic).")
    lines.append("- Prioriser les posts où **Bonificación SS** et **Deducción I+D+i** sont confondus : excellent terrain pour un post clarificateur.")
    lines.append("- Exploiter un format récurrent détecté (checklist / myth-busting) en le rendant plus rigoureux (conditions, périmètre, pièces justificatives).")
    lines.append("")

    return "\n".join(lines)

def main():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    df = load_posts()
    df = assign_categories(df, cfg)
    df = assign_formats(df, cfg)
    df = score_engagement(df)
    report_md = build_report(df, cfg)

    out_path = REPORTS_DIR / "report.md"
    out_path.write_text(report_md, encoding="utf-8")
    print(f"OK — Rapport généré : {out_path}")

if __name__ == "__main__":
    main()
