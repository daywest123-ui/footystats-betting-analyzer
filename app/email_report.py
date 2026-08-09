import os
import smtplib
from email.message import EmailMessage
from datetime import datetime, timezone


def send_email(subject: str, body: str) -> None:
    host = os.environ.get("SMTP_HOST", "smtp-mail.outlook.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ["SMTP_USERNAME"]
    password = os.environ["SMTP_PASSWORD"]
    recipient = os.environ.get("REPORT_TO", "day_west_123@hotmail.com")

    msg = EmailMessage()
    msg["From"] = username
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(username, password)
        server.send_message(msg)


if __name__ == "__main__":
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    send_email(
        "⚽ Football Analyzer — bağlantı testi",
        f"Football Analyzer e-posta bağlantısı başarıyla çalıştı.\n\nZaman: {now}\n\nBu ilk test mesajıdır. Maç analiz raporu sistemi ayrı adımda devreye alınacaktır.",
    )
    print("Email sent successfully")
