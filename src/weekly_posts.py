from pathlib import Path
import json
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
BRIEF_PATH = ROOT / "reports" / "brief.json"
OUT_PATH = ROOT / "reports" / "weekly_posts.md"

def pick_two_posts(brief: dict) -> list[dict]:
    """
    Heuristique V0.2.2 :
    - Post #1 : Clarification Bonificación SS vs Deducción I+D+i (différenciant, evergreen, fort ROI)
    - Post #2 : Opportunité top (traction × rareté) issue du brief
    """
    opportunities = brief.get("opportunities", [])
    # Nettoyage : ignorer "(non classé)"
    opportunities = [o for o in opportunities if o.get("theme") and o["theme"] != "(non classé)"]

    # Post 2 : meilleur thème opportunité (ou fallback)
    post2_theme = opportunities[0]["theme"] if opportunities else "Documentación / Riesgo"

    return [
        {
            "title": "Bonificación SS vs Deducción I+D+i: cómo no equivocarse",
            "why_now": "Tema recurrente y confuso. Buen rendimiento en contenidos de mercado y alto potencial de diferenciación si se trata de forma audit-ready.",
            "angle_inosearch": "Comparación estructurada + criterios de elegibilidad + evidencias mínimas + errores frecuentes (enfoque 'pre-auditoría').",
            "format": "Checklist + myth-busting",
            "structure": [
                "Hook: ‘Si estás mezclando bonificación y deducción, estás asumiendo un riesgo innecesario.’",
                "3 diferencias clave (objetivo, base, documentación).",
                "Qué documentos mirar (lista corta).",
                "Errores frecuentes y cómo evitarlos.",
                "CTA: prediagnóstico 20 min / revisión de elegibilidad."
            ],
            "x_version": "Hilo 5 tweets: 1) confusión común 2) diferencia #1 3) diferencia #2 4) diferencia #3 5) checklist + CTA"
        },
        {
            "title": f"Semana: enfoque en «{post2_theme}» (audit-ready)",
            "why_now": "Basado en la señal de tracción/rareza detectada esta semana en la veille concurrentielle.",
            "angle_inosearch": "Convertir el tema en guía operativa: qué hacer, qué probar, qué medir, y cómo reducir riesgo fiscal.",
            "format": "Guía paso a paso (breve) + mini-caso hipotético",
            "structure": [
                "Hook orientado a dolor: ‘El problema no es el incentivo, es la prueba.’",
                "Qué espera ver un auditor/administración (3 puntos).",
                "Qué métricas/evidencias generan tranquilidad (3 ejemplos).",
                "Mini-caso (simplificado) + lección.",
                "CTA: ‘si quieres, te damos una checklist de evidencias adaptada a tu proyecto’."
            ],
            "x_version": "Post X corto: 1 insight + 3 bullets + 1 CTA. Variante: hilo 4 tweets."
        }
    ]

def render_markdown(posts: list[dict], generated_at: str) -> str:
    lines = []
    lines.append("# Weekly Posts — Inosearch España (V0.2.2)")
    lines.append(f"_Generado: {generated_at}_")
    lines.append("")
    for i, p in enumerate(posts, start=1):
        lines.append(f"## Post {i} — {p['title']}")
        lines.append("")
        lines.append(f"**Por qué ahora:** {p['why_now']}")
        lines.append("")
        lines.append(f"**Ángulo Inosearch:** {p['angle_inosearch']}")
        lines.append("")
        lines.append(f"**Formato recomendado:** {p['format']}")
        lines.append("")
        lines.append("**Estructura sugerida:**")
        for s in p["structure"]:
            lines.append(f"- {s}")
        lines.append("")
        lines.append(f"**Versión X:** {p['x_version']}")
        lines.append("")
    return "\n".join(lines)

def main():
    if not BRIEF_PATH.exists():
        raise FileNotFoundError("reports/brief.json not found. Run analyze.py first.")
    brief = json.loads(BRIEF_PATH.read_text(encoding="utf-8"))
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    posts = pick_two_posts(brief)
    OUT_PATH.write_text(render_markdown(posts, generated_at), encoding="utf-8")
    print(f"OK — Weekly posts generated: {OUT_PATH}")

if __name__ == "__main__":
    main()
