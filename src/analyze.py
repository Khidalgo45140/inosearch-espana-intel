import re
import json
import yaml
import pandas as pd
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

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
    expected = ["platform","competitor","author","date","url","content","likes","comments","reposts"]
    for col in expected:
        if col not in df.columns:
            df[col] = ""
    for c in ["likes","comments","reposts"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    df["content_norm"] = df["content"].apply(normalize)
    df["competitor"] = df["competitor"].fillna("").astype(str)
    df["platform"] = df["platform"].fillna("").astype(str)
    df["date"] = df["date"].fillna("").astype(str)
    return df

def assign_categories(df, cfg):
    categories = cfg.get("categories", {})
    out = []
    for _, row in df.iterrows():
        text = row["content_norm"]
        matched = []
        for cat_key, cat in categories.items():
            kws = cat.get("keywords", [])
            if contains_any(text, kws):
                matched.append(cat.get("label", cat_key))
        out.append(matched if matched else ["(non classé)"])
    df["categories"] = out
    return df

def assign_formats(df, cfg):
    formats = cfg.get("formats", {})
    out = []
    for _, row in df.iterrows():
        text = row["content_norm"]
        matched = []
        for fmt_key, fmt in formats.items():
            kws = fmt.get("keywords", [])
            if contains_any(text, kws):
                matched.append(fmt_key)
        out.append(matched if matched else ["(non détecté)"])
    df["formats"] = out
    return df

def score_engagement(df):
    df["engagement_score"] = df["likes"] + 2*df["comments"] + 3*df["reposts"]
    return df

def explode_counts(df, col):
    return df.explode(col)[col].value_counts()

def competitor_theme_matrix(df):
    # Returns: dict competitor -> Counter(theme)
    comp = defaultdict(Counter)
    for row in df.itertuples(index=False):
        competitor = getattr(row, "competitor") or "(inconnu)"
        for c in getattr(row, "categories"):
            comp[competitor][c] += 1
    return comp

def competitor_format_matrix(df):
    comp = defaultdict(Counter)
    for row in df.itertuples(index=False):
        competitor = getattr(row, "competitor") or "(inconnu)"
        for f in getattr(row, "formats"):
            comp[competitor][f] += 1
    return comp

def compute_opportunities(df):
    """
    Heuristique simple:
    - Traction: thèmes présents dans le TOP engagement
    - Rareté: thèmes peu couverts globalement
    => Opportunité = traction élevée * rareté
    """
    if len(df) == 0:
        return []

    df_sorted = df.sort_values("engagement_score", ascending=False)
    top_n = max(3, min(15, int(len(df)*0.3)))  # top 30% capped
    top = df_sorted.head(top_n)

    global_counts = explode_counts(df, "categories")
    top_counts = explode_counts(top, "categories")

    opportunities = []
    for theme, top_cnt in top_counts.items():
        global_cnt = int(global_counts.get(theme, 0))
        # rareté: plus global_cnt est faible, plus rareté est forte
        rarity = 1.0 / (1 + global_cnt)
        traction = float(top_cnt)
        score = traction * rarity
        opportunities.append({
            "theme": theme,
            "top_mentions": int(top_cnt),
            "global_mentions": int(global_cnt),
            "opportunity_score": round(score, 4)
        })

    opportunities.sort(key=lambda x: x["opportunity_score"], reverse=True)
    return opportunities[:10]

def build_brief_json(df, opportunities):
    """
    Sortie structurée pour l’outil 2.
    On ne copie pas de texte concurrent: on ne sort que des résumés et extraits courts.
    """
    top_posts = df.sort_values("engagement_score", ascending=False).head(10)
    top_list = []
    for row in top_posts.itertuples(index=False):
        top_list.append({
            "platform": row.platform,
            "competitor": row.competitor,
            "date": row.date,
            "score": int(row.engagement_score),
            "categories": list(row.categories),
            "formats": list(row.formats),
            "snippet": str(row.content)[:160].replace("\n", " ")
        })

    comp_themes = competitor_theme_matrix(df)
    comp_formats = competitor_format_matrix(df)

    brief = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "counts": {
            "posts": int(len(df)),
        },
        "top_posts": top_list,
        "competitors": {
            comp: {
                "themes": dict(comp_themes[comp]),
                "formats": dict(comp_formats[comp])
            }
            for comp in sorted(set(df["competitor"].tolist())) if comp
        },
        "opportunities": opportunities,
        "recommended_playbook": [
            "Produire un post clarificateur Bonificación SS vs Deducción I+D+i (périmètre, conditions, pièces).",
            "Exploiter un format récurrent (checklist / myth-busting) avec un niveau de preuve supérieur (méthodo, risques, exemples).",
            "Créer une série 'erreurs fréquentes' orientée audit (ce que l’administration/les auditeurs regardent réellement)."
        ]
    }
    return brief

def build_report_md(df, opportunities):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = len(df)

    top = df.sort_values("engagement_score", ascending=False).head(10)
    cat_counts = explode_counts(df, "categories")
    fmt_counts = explode_counts(df, "formats")

    comp_themes = competitor_theme_matrix(df)
    comp_formats = competitor_format_matrix(df)

    lines = []
    lines.append("# Inosearch España — Veille & Analyse (V0.1)")
    lines.append(f"_Généré le {now}_")
    lines.append("")
    lines.append("## 1) Volume analysé")
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

    lines.append("## 4) Opportunités éditoriales (traction × rareté)")
    if opportunities:
        lines.append("| Rang | Thème | Mentions TOP | Mentions globales | Score opportunité |")
        lines.append("|---:|---|---:|---:|---:|")
        for i, o in enumerate(opportunities, start=1):
            lines.append(f"| {i} | {o['theme']} | {o['top_mentions']} | {o['global_mentions']} | {o['opportunity_score']} |")
    else:
        lines.append("- (Aucune opportunité calculable)")
    lines.append("")

    lines.append("## 5) Matrice concurrents → thèmes dominants")
    for comp, counter in comp_themes.items():
        top3 = counter.most_common(3)
        if not top3:
            continue
        t = ", ".join([f"{k} ({v})" for k, v in top3])
        lines.append(f"- **{comp}** : {t}")
    lines.append("")

    lines.append("## 6) Matrice concurrents → formats dominants")
    for comp, counter in comp_formats.items():
        top3 = counter.most_common(3)
        if not top3:
            continue
        t = ", ".join([f"{k} ({v})" for k, v in top3])
        lines.append(f"- **{comp}** : {t}")
    lines.append("")

    lines.append("## 7) Top posts (score = likes + 2×comments + 3×reposts)")
    lines.append("")
    lines.append("| Rang | Plateforme | Concurrent | Date | Catégories | Formats | Score | Extrait |")
    lines.append("|---:|---|---|---|---|---|---:|---|")
    for i, row in enumerate(top.itertuples(index=False), start=1):
        cats = ", ".join(row.categories)
        fmts = ", ".join(row.formats)
        snippet = str(row.content)[:120].replace("\n", " ")
        score = int(row.engagement_score)
        lines.append(f"| {i} | {row.platform} | {row.competitor} | {row.date} | {cats} | {fmts} | {score} | {snippet} |")
    lines.append("")

    lines.append("## 8) Recommandations Inosearch (première passe)")
    lines.append("- Construire une série 'audit-ready' : périmètre, conditions, preuves, erreurs fréquentes.")
    lines.append("- Systématiser un CTA discret : diagnostic 20 min / pré-qualification I+D vs IT.")
    lines.append("- Réutiliser le même sujet en 2 versions : LinkedIn (long) + X (thread).")
    lines.append("")

    return "\n".join(lines)

def main():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    df = load_posts()
    df = assign_categories(df, cfg)
    df = assign_formats(df, cfg)
    df = score_engagement(df)

    opportunities = compute_opportunities(df)

    report_md = build_report_md(df, opportunities)
    (REPORTS_DIR / "report.md").write_text(report_md, encoding="utf-8")

    brief = build_brief_json(df, opportunities)
    (REPORTS_DIR / "brief.json").write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK — Rapport généré : {REPORTS_DIR / 'report.md'}")
    print(f"OK — Brief généré : {REPORTS_DIR / 'brief.json'}")

if __name__ == "__main__":
    main()
