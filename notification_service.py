import logging
import os
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

LOG_PATH = os.environ.get("NOTIFICATION_LOG", "/var/log/notifications.log")


def send_email(to: str, subject: str, body: str) -> bool:
    if not SMTP_USER or not SMTP_PASSWORD:
        raise ValueError("SMTP_USER and SMTP_PASSWORD environment variables must be set")

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
    entry = f"Notification: {username} triggered {event}\n"
    try:
        with open(LOG_PATH, "a") as f:
            f.write(entry)
    except OSError:
        logger.warning("Could not write notification log to %s", LOG_PATH)


def send_bulk(recipients: list, subject: str, body: str) -> dict:
    results = {}
    for r in recipients:
        results[r] = send_email(r, subject, body)
    return results


def format_message(template: str, **kwargs) -> str:
    return template.format(**kwargs)
