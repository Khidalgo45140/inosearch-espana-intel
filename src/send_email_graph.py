import os
import json
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "weekly_posts.md"

def get_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value

def get_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
        "scope": "https://graph.microsoft.com/.default",
    }).encode("utf-8")

    request = urllib.request.Request(token_url, data=data, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")

    with urllib.request.urlopen(request) as response:
        payload = json.loads(response.read().decode("utf-8"))

    return payload["access_token"]

def send_mail(token: str, mail_from: str, mail_to: str, subject: str, body: str):
    url = f"https://graph.microsoft.com/v1.0/users/{urllib.parse.quote(mail_from)}/sendMail"

    message = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "Text",
                "content": body
            },
            "toRecipients": [
                {"emailAddress": {"address": mail_to}}
            ],
        },
        "saveToSentItems": True
    }

    data = json.dumps(message).encode("utf-8")

    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(request) as response:
        response.read()

def main():
    if not REPORT.exists():
        raise FileNotFoundError("reports/weekly_posts.md not found")

    tenant_id = get_env("M365_TENANT_ID")
    client_id = get_env("M365_CLIENT_ID")
    client_secret = get_env("M365_CLIENT_SECRET")
    mail_from = get_env("MAIL_FROM")
    mail_to = get_env("MAIL_TO")

    content = REPORT.read_text(encoding="utf-8")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    subject = f"Inosearch España — Weekly posts (copier-coller dans ChatGPT) — {now}"

    prompt = (
        "PROMPT A COPIER-COLLER DANS CHATGPT\n"
        "---------------------------------\n"
        "Tu es responsable contenu d’Inosearch España. À partir du brief ci-dessous, "
        "rédige 2 posts LinkedIn en espagnol (ton expert, concret, orienté valeur). "
        "Pour chaque post : propose 2 hooks, une structure claire, une section audit-ready "
        "(preuves, documentation, risques, erreurs fréquentes) et un CTA discret.\n\n"
        "BRIEF\n"
        "-----\n"
    )

    body = prompt + content

    token = get_token(tenant_id, client_id, client_secret)
    send_mail(token, mail_from, mail_to, subject, body)

    print("OK — Email sent via Microsoft Graph")

if __name__ == "__main__":
    main()
