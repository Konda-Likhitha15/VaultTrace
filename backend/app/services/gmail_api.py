"""Gmail API email transport using OAuth refresh-token credentials."""

import base64
import logging
from email.message import EmailMessage
from urllib.parse import quote
from pydantic import SecretStr

from app.core.config import settings
from app.services.email import EmailDeliveryError

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages/send"
logger = logging.getLogger("vaulttrace.email")


def _secret_value(value: str | SecretStr | None) -> str | None:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return value


class GmailConfigurationError(Exception):
    """Raised when Gmail API delivery is selected without required settings."""


class GmailResponseError(Exception):
    """A Gmail API response with a non-success HTTP status."""

    def __init__(self, status_code: int):
        self.status_code = status_code


def _google_auth_components():
    """Load Google dependencies lazily so Mailpit does not require OAuth setup."""
    from google.auth.exceptions import GoogleAuthError, RefreshError
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2.credentials import Credentials
    from requests.exceptions import RequestException

    return Credentials, AuthorizedSession, GoogleAuthError, RefreshError, RequestException


def _diagnostic(status_code: int | None, exc: Exception) -> str:
    """Map failures to fixed safe messages; exception text can contain secrets."""
    if status_code == 403:
        return "Gmail API denied the send request"
    if status_code == 429:
        return "Gmail API rate limited the send request"
    if status_code is not None and status_code >= 500:
        return "Gmail API is temporarily unavailable"
    if isinstance(exc, GmailConfigurationError):
        return "Gmail API configuration is incomplete"
    if isinstance(exc, GmailResponseError):
        return "Gmail API rejected the send request"
    if type(exc).__name__.endswith("RefreshError"):
        return "Gmail OAuth refresh failed"
    if isinstance(exc, TimeoutError) or type(exc).__name__ == "Timeout":
        return "Gmail API request timed out"
    if isinstance(exc, OSError):
        return "Gmail API network request failed"
    return "Gmail API authentication or request failed"


def _log_failure(exc: Exception, status_code: int | None = None) -> None:
    logger.warning(
        "Gmail API email delivery failed (exception_type=%s http_status=%s diagnostic=%s)",
        type(exc).__name__,
        status_code if status_code is not None else "none",
        _diagnostic(status_code, exc),
    )


def send_gmail_api_email(
    recipient: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> None:
    """Send a MIME email via Gmail API over HTTPS without logging message data."""
    required = {
        "GMAIL_CLIENT_ID": settings.gmail_client_id,
        "GMAIL_CLIENT_SECRET": _secret_value(settings.gmail_client_secret),
        "GMAIL_REFRESH_TOKEN": _secret_value(settings.gmail_refresh_token),
        "GMAIL_SENDER_EMAIL": settings.gmail_sender_email,
    }
    missing = [name for name, value in required.items() if not value or not value.strip()]
    if missing:
        exc = GmailConfigurationError()
        _log_failure(exc)
        raise EmailDeliveryError("Email delivery is not configured") from exc

    try:
        Credentials, AuthorizedSession, GoogleAuthError, RefreshError, RequestException = _google_auth_components()
    except ImportError as exc:
        _log_failure(exc)
        raise EmailDeliveryError("Gmail API dependencies are unavailable") from exc

    try:
        # A refresh token lets google-auth obtain a fresh short-lived access
        # token automatically when AuthorizedSession makes the HTTPS request.
        credentials = Credentials(
            token=None,
            refresh_token=_secret_value(settings.gmail_refresh_token),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.gmail_client_id,
            client_secret=_secret_value(settings.gmail_client_secret),
            scopes=[GMAIL_SEND_SCOPE],
        )

        message = EmailMessage()
        message["From"] = settings.gmail_sender_email
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        if html_body:
            message.add_alternative(html_body, subtype="html")
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")

        # Gmail validates this userId against the OAuth credential. Requiring
        # the configured sender as userId also prevents silently sending from
        # a different Gmail account than the one that granted this refresh token.
        with AuthorizedSession(credentials, refresh_timeout=10) as session:
            response = session.post(
                GMAIL_SEND_URL.format(user_id=quote(settings.gmail_sender_email, safe="")),
                json={"raw": raw_message},
                timeout=(5, 20),
            )
            status_code = response.status_code
            response.close()
            if status_code < 200 or status_code >= 300:
                raise GmailResponseError(status_code)
    except GmailResponseError as exc:
        _log_failure(exc, exc.status_code)
        raise EmailDeliveryError("Email delivery failed") from exc
    except RefreshError as exc:
        _log_failure(exc)
        raise EmailDeliveryError("Email delivery failed") from exc
    except (GoogleAuthError, RequestException, TimeoutError, OSError, ValueError) as exc:
        _log_failure(exc)
        raise EmailDeliveryError("Email delivery failed") from exc
