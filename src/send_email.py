import os
import ssl
import smtplib
from email.message import EmailMessage
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "weekly_posts.md"

def main():
    if not REPORT.exists():
        raise FileNotFoundError("reports/weekly_posts.md not found. Run weekly_posts.py first.")

    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASS"]

    to_email = os.environ.get("TO_EMAIL", "kevin.hidalgo@inosearch.fr")
    from_email = os.environ.get("FROM_EMAIL", smtp_user)

    content = REPORT.read_text(encoding="utf-8")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    prompt = (
        "PROMPT A COPIER-COLLER DANS CHATGPT\n"
        "---------------------------------\n"
        "Tu es responsable contenu d’Inosearch España. À partir du brief ci-dessous, rédige 2 posts LinkedIn en espagnol "
        "(ton expert, concret, orienté valeur), sans copier les concurrents. Pour chaque post : propose 2 hooks, une structure claire, "
        "1 section audit-ready (preuves/documentation/risques/erreurs fréquentes), et un CTA discret vers un échange de pré-qualification. "
        "Fournis aussi pour chaque post : une version X (tweet court) + une option thread (4–6 tweets).\n\n"
        "BRIEF\n"
        "-----\n"
    )

    msg = EmailMessage()
    msg["Subject"] = f"Inosearch España — Weekly posts (copier-coller dans ChatGPT) — {now}"
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(prompt + content)

    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls(context=context)
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)

    print("OK — Email sent")

if __name__ == "__main__":
    main()
