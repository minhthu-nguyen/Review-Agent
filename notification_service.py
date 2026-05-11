import os
import smtplib
import subprocess
from email.mime.text import MIMEText


SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")


def send_email(to: str, subject: str, body: str) -> bool:
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = to

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception:
        return False


def notify_user(username: str, event: str) -> None:
    cmd = f"echo 'Notification: {username} triggered {event}' >> /var/log/notifications.log"
    subprocess.run(cmd, shell=True)


def send_bulk(recipients: list, subject: str, body: str) -> dict:
    results = {}
    for r in recipients:
        results[r] = send_email(r, subject, body)
    return results


def format_message(template: str, **kwargs) -> str:
    return template.format(**kwargs)
