import logging
import os
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

_REQUIRED_ENV = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD"]
_missing = [k for k in _REQUIRED_ENV if not os.environ.get(k)]
if _missing:
    raise EnvironmentError(f"Missing required environment variables: {', '.join(_missing)}")

SMTP_HOST = os.environ["SMTP_HOST"]
SMTP_PORT = int(os.environ["SMTP_PORT"])
SMTP_USER = os.environ["SMTP_USER"]
SMTP_PASSWORD = os.environ["SMTP_PASSWORD"]

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
    except (smtplib.SMTPException, OSError) as e:
        logger.error("Failed to send email to %s: %s", to, e)
        return False


def notify_user(username: str, event: str) -> None:
    entry = f"Notification: {username} triggered {event}\n"
    try:
        with open(LOG_PATH, "a") as f:
            f.write(entry)
    except OSError:
        logger.warning("Could not write notification log to %s", LOG_PATH)


def send_bulk(recipients: list[str], subject: str, body: str) -> dict[str, bool]:
    results = {}
    for r in recipients:
        results[r] = send_email(r, subject, body)
    return results


def format_message(template: str, **kwargs) -> str:
    return template.format(**kwargs)
