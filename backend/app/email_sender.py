"""
Plain SMTP via stdlib smtplib - no third-party email service dependency,
since the admin already has an SMTP server one way or another (their own
email provider almost always exposes one, even a personal Gmail account
with an app password) and this is the only outbound email the hub ever
sends. Kept to exactly one use so far: password reset links.
"""
import smtplib
from email.mime.text import MIMEText

from . import hub_settings


class EmailError(Exception):
    pass


def send_email(to_address: str, subject: str, body: str) -> None:
    settings = hub_settings.get_smtp_settings()
    if not settings["configured"]:
        raise EmailError("Outgoing email isn't configured yet - set it up on the Settings page")

    message = MIMEText(body)
    message["Subject"] = subject
    message["From"] = settings["from_address"]
    message["To"] = to_address

    try:
        if settings["use_tls"]:
            with smtplib.SMTP(settings["host"], settings["port"], timeout=15) as server:
                server.starttls()
                if settings["username"]:
                    server.login(settings["username"], settings["password"])
                server.send_message(message)
        else:
            with smtplib.SMTP_SSL(settings["host"], settings["port"], timeout=15) as server:
                if settings["username"]:
                    server.login(settings["username"], settings["password"])
                server.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise EmailError("The SMTP username/password on the Settings page were rejected") from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise EmailError(f"Couldn't send email: {exc}") from exc
