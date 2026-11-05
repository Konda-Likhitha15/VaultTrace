"""Send one explicit Gmail API test message using local OAuth files.

This utility is intentionally separate from the application. It performs one
Gmail send request at most, does not retry failed sends, and never prints OAuth
credential values or API response bodies.
"""

import argparse
import base64
import json
import re
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_API_URL = "https://gmail.googleapis.com/gmail/v1/users/{user_id}/messages/send"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLIENT_FILE = PROJECT_ROOT / "credentials.json"
TOKEN_FILE = PROJECT_ROOT / ".gmail_token.json"
SUBJECT = "VaultTrace Gmail API Test"
TEXT_BODY = "Gmail API integration is working successfully in VaultTrace."
HTML_BODY = "<html><body><p>Gmail API integration is working successfully in VaultTrace.</p></body></html>"


class TestSetupError(Exception):
    """A required local credential file or field is missing or inconsistent."""


@dataclass(frozen=True)
class TestResult:
    oauth_authenticated: bool
    http_status: int | None
    accepted: bool
    message_id: str | None
    error_type: str | None
    error_code: int | None = None
    error_message: str | None = None
    error_reasons: tuple[str, ...] = ()
    error_status: str | None = None


def _read_credentials(client_file: Path, token_file: Path) -> dict[str, str]:
    if not client_file.is_file():
        raise TestSetupError("credentials.json is missing")
    if not token_file.is_file():
        raise TestSetupError(".gmail_token.json is missing")
    try:
        client_data = json.loads(client_file.read_text(encoding="utf-8"))
        token_data = json.loads(token_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise TestSetupError("a credential JSON file is unreadable or invalid") from None

    client = client_data.get("installed") or client_data.get("web")
    if not isinstance(client, dict):
        raise TestSetupError("credentials.json is not a Google OAuth client file")
    required_client_fields = ("client_id", "client_secret")
    required_token_fields = ("client_id", "client_secret", "refresh_token", "token_uri")
    if any(not isinstance(client.get(name), str) or not client[name] for name in required_client_fields):
        raise TestSetupError("credentials.json is missing its client ID or client secret")
    if any(not isinstance(token_data.get(name), str) or not token_data[name] for name in required_token_fields):
        raise TestSetupError(".gmail_token.json is missing a required OAuth field")
    if client["client_id"] != token_data["client_id"] or client["client_secret"] != token_data["client_secret"]:
        raise TestSetupError("the OAuth client and saved token file do not match")
    scopes = token_data.get("scopes")
    if not isinstance(scopes, list) or GMAIL_SEND_SCOPE not in scopes:
        raise TestSetupError(".gmail_token.json does not include the gmail.send scope")
    return {
        "client_id": token_data["client_id"],
        "client_secret": token_data["client_secret"],
        "refresh_token": token_data["refresh_token"],
        "token_uri": token_data["token_uri"],
    }


def _google_auth_components():
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2.credentials import Credentials

    return Credentials, AuthorizedSession, RefreshError


def _safe_error_text(value: object, secrets: tuple[str, ...]) -> str | None:
    """Keep useful Google diagnostics while removing credentials and PII."""
    if not isinstance(value, str):
        return None
    text = value
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", text)
    text = re.sub(r"\bya29\.[A-Za-z0-9._~-]+", "[REDACTED_TOKEN]", text)
    text = re.sub(r"\b1//[A-Za-z0-9._~-]+", "[REDACTED_TOKEN]", text)
    text = re.sub(r"\b\d+-[A-Za-z0-9_-]+\.apps\.googleusercontent\.com\b", "[REDACTED_CLIENT_ID]", text)
    text = re.sub(r"\bGOCSPX-[A-Za-z0-9_-]+", "[REDACTED_CLIENT_SECRET]", text)
    text = re.sub(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]", text)
    text = re.sub(r"(?<!\w)(?:\+?\d[\d ().-]{7,}\d)(?!\w)", "[REDACTED_PHONE]", text)
    text = " ".join(text.split())
    return text[:500] or None


def _gmail_error_diagnostics(response, secrets: tuple[str, ...]) -> tuple[int | None, str | None, tuple[str, ...], str | None]:
    """Extract only the requested fields from a Gmail error response."""
    try:
        payload = response.json()
    except (ValueError, TypeError):
        return None, None, (), None
    if not isinstance(payload, dict) or not isinstance(payload.get("error"), dict):
        return None, None, (), None
    error = payload["error"]
    code = error.get("code")
    safe_code = code if isinstance(code, int) and not isinstance(code, bool) else None
    message = _safe_error_text(error.get("message"), secrets)
    reasons: list[str] = []
    details = error.get("errors")
    if isinstance(details, list):
        for detail in details:
            if isinstance(detail, dict):
                reason = _safe_error_text(detail.get("reason"), secrets)
                if reason:
                    reasons.append(reason)
    status = _safe_error_text(error.get("status"), secrets)
    return safe_code, message, tuple(reasons), status


def send_one_test_email(
    recipient: str,
    *,
    client_file: Path = CLIENT_FILE,
    token_file: Path = TOKEN_FILE,
) -> TestResult:
    """Refresh OAuth if required, then make exactly one Gmail send request."""
    if not recipient or recipient.strip() != recipient or "@" not in recipient:
        raise TestSetupError("provide the authorized Gmail address as the recipient argument")
    oauth = _read_credentials(client_file, token_file)
    Credentials, AuthorizedSession, RefreshError = _google_auth_components()
    credentials = Credentials(
        token=None,
        refresh_token=oauth["refresh_token"],
        token_uri=oauth["token_uri"],
        client_id=oauth["client_id"],
        client_secret=oauth["client_secret"],
        scopes=[GMAIL_SEND_SCOPE],
    )

    message = EmailMessage()
    message["From"] = recipient
    message["To"] = recipient
    message["Subject"] = SUBJECT
    message.set_content(TEXT_BODY)
    message.add_alternative(HTML_BODY, subtype="html")
    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")
    url = GMAIL_API_URL.format(user_id=quote(recipient, safe=""))

    try:
        # max_refresh_attempts=0 prevents a failed send request from being
        # replayed. AuthorizedSession still refreshes a missing/expired token
        # before the single POST.
        with AuthorizedSession(credentials, refresh_timeout=10, max_refresh_attempts=0) as session:
            response = session.post(url, json={"raw": encoded_message}, timeout=(5, 20))
            status_code = response.status_code
            message_id = None
            error_code = None
            error_message = None
            error_reasons: tuple[str, ...] = ()
            error_status = None
            if status_code == 403:
                # Read the bounded, whitelisted diagnostic fields before closing
                # the response. No raw body or response headers are retained.
                sensitive_values = (
                    oauth["client_id"], oauth["client_secret"], oauth["refresh_token"], recipient,
                )
                error_code, error_message, error_reasons, error_status = _gmail_error_diagnostics(
                    response, sensitive_values,
                )
            elif 200 <= status_code < 300:
                try:
                    response_data = response.json()
                    candidate = response_data.get("id") if isinstance(response_data, dict) else None
                    message_id = candidate if isinstance(candidate, str) else None
                except (ValueError, TypeError):
                    pass
            response.close()
            return TestResult(
                oauth_authenticated=bool(credentials.valid),
                http_status=status_code,
                accepted=200 <= status_code < 300,
                message_id=message_id,
                error_type=None if 200 <= status_code < 300 else "GmailAPIResponseError",
                error_code=error_code,
                error_message=error_message,
                error_reasons=error_reasons,
                error_status=error_status,
            )
    except RefreshError as exc:
        return TestResult(False, None, False, None, type(exc).__name__)
    except Exception as exc:
        # Do not stringify transport/auth exceptions: their detail can contain
        # request metadata. The class name is enough for a safe local report.
        return TestResult(bool(credentials.valid), None, False, None, type(exc).__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Send exactly one Gmail API test email to the specified address.")
    parser.add_argument("recipient", help="The same Gmail account that authorized the OAuth refresh token")
    args = parser.parse_args()
    try:
        result = send_one_test_email(args.recipient)
    except TestSetupError as exc:
        raise SystemExit(f"Preflight failed: {exc}") from None
    except ImportError:
        raise SystemExit("Preflight failed: install requirements.txt in this Python environment first.") from None

    print(f"OAuth authentication: {'success' if result.oauth_authenticated else 'failed'}")
    print(f"Gmail API HTTP status: {result.http_status if result.http_status is not None else 'unavailable'}")
    print(f"Accepted by Gmail: {'yes' if result.accepted else 'no'}")
    print(f"Gmail message ID: {result.message_id or 'unavailable'}")
    if result.error_type:
        print(f"Error type: {result.error_type}; raw details suppressed")
    if result.http_status == 403:
        print(f"Gmail error.code: {result.error_code if result.error_code is not None else 'unavailable'}")
        print(f"Gmail error.message: {result.error_message or 'unavailable'}")
        reasons = ", ".join(result.error_reasons) if result.error_reasons else "unavailable"
        print(f"Gmail error.errors[].reason: {reasons}")
        print(f"Gmail error.status: {result.error_status or 'unavailable'}")
    if not result.accepted:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
