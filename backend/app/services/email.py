"""SMTP email delivery for OTPs and registration decisions."""

import html
import smtplib
from email.message import EmailMessage

from app.core.config import settings


class EmailDeliveryError(Exception):
    """Raised when SMTP cannot accept an application email."""


def send_email(recipient: str, subject: str, body: str, html_body: str | None = None) -> None:
    """Send a plain-text and optional HTML message using environment SMTP."""
    message = EmailMessage()
    message["From"] = settings.smtp_from_email or settings.smtp_from
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    try:
        smtp_type = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
        with smtp_type(settings.smtp_host, settings.smtp_port, timeout=10) as client:
            use_tls = settings.smtp_use_tls if settings.smtp_use_tls is not None else settings.smtp_starttls
            if use_tls and not settings.smtp_use_ssl:
                client.starttls()
            if settings.smtp_username and settings.smtp_password:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError("Email delivery failed") from exc


def send_otp_email(recipient: str, otp: str) -> None:
    """Deliver a short-lived verification code without logging it."""
    safe_otp = html.escape(otp)
    minutes = settings.otp_expiration_minutes
    send_email(
        recipient,
        "VaultTrace email verification",
        f"Your VaultTrace verification code is {otp}. It expires in {minutes} minutes.",
        f"<html><body><h1>VaultTrace verification</h1><p>Your verification code is:</p><p style='font-size:28px;font-weight:bold;letter-spacing:6px'>{safe_otp}</p><p>This code expires in {minutes} minutes. If you did not request it, ignore this email.</p></body></html>",
    )


def send_application_decision(recipient: str, approved: bool, reason: str | None = None) -> None:
    """Notify an applicant of an administrator's decision."""
    if approved:
        body = "Your VaultTrace registration application has been approved. You may now sign in."
        subject = "VaultTrace registration approved"
    else:
        body = "Your VaultTrace registration application was not approved."
        if reason:
            body += f"\nReason: {reason}"
        subject = "VaultTrace registration update"
    send_email(recipient, subject, body)
