"""Gmail API transport tests using only mocked OAuth and HTTPS clients."""

import base64
import logging
from email import message_from_bytes
from email import policy

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import Role, User
from app.services import email as email_service
from app.services import gmail_api
from app.services.email import EmailDeliveryError
from backend.tests.database import TestSession


class FakeGoogleAuthError(Exception):
    pass


class FakeRefreshError(FakeGoogleAuthError):
    pass


class FakeRequestException(Exception):
    pass


class FakeCredentials:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.token = None


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.closed = False

    def close(self):
        self.closed = True


class FakeAuthorizedSession:
    response_status = 200
    post_error: Exception | None = None
    calls: list[tuple[str, dict, object, tuple[int, int]]] = []
    refresh_performed = False

    def __init__(self, credentials: FakeCredentials, refresh_timeout: int):
        self.credentials = credentials
        self.refresh_timeout = refresh_timeout
        if credentials.token is None:
            # Represents google-auth refreshing its access token before the
            # first authorized HTTPS request when only a refresh token exists.
            credentials.token = "mock-short-lived-access-token"
            type(self).refresh_performed = True

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, url: str, *, json: dict, timeout: tuple[int, int]):
        type(self).calls.append((url, json, self.credentials, timeout))
        if type(self).post_error is not None:
            raise type(self).post_error
        return FakeResponse(type(self).response_status)


def install_fake_google_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeAuthorizedSession.calls = []
    FakeAuthorizedSession.response_status = 200
    FakeAuthorizedSession.post_error = None
    FakeAuthorizedSession.refresh_performed = False
    monkeypatch.setattr(
        gmail_api,
        "_google_auth_components",
        lambda: (
            FakeCredentials,
            FakeAuthorizedSession,
            FakeGoogleAuthError,
            FakeRefreshError,
            FakeRequestException,
        ),
    )


def configure_gmail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "gmail_client_id", "client-id-test")
    monkeypatch.setattr(settings, "gmail_client_secret", "client-secret-test")
    monkeypatch.setattr(settings, "gmail_refresh_token", "refresh-token-test")
    monkeypatch.setattr(settings, "gmail_sender_email", "sender@example.com")


def decode_raw(raw: str):
    padded = raw + "=" * (-len(raw) % 4)
    return message_from_bytes(base64.urlsafe_b64decode(padded), policy=policy.default)


def test_mailpit_provider_and_existing_smtp_path_remain_available(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            self.sent = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def send_message(self, _message):
            self.sent = True

    monkeypatch.setattr(settings, "email_provider", "mailpit")
    monkeypatch.setattr(settings, "smtp_use_ssl", False)
    monkeypatch.setattr(settings, "smtp_starttls", False)
    monkeypatch.setattr(settings, "smtp_use_tls", None)
    monkeypatch.setattr(settings, "smtp_username", None)
    monkeypatch.setattr(settings, "smtp_password", None)
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    email_service.send_email("recipient@example.com", "Local", "Captured by SMTP")


def test_provider_selection_calls_gmail_api_additively(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple] = []
    monkeypatch.setattr(settings, "email_provider", "gmail_api")
    monkeypatch.setattr(gmail_api, "send_gmail_api_email", lambda *args: sent.append(args))
    email_service.send_email("recipient@example.com", "Subject", "Text", "<p>HTML</p>")
    assert sent == [("recipient@example.com", "Subject", "Text", "<p>HTML</p>")]


def test_gmail_api_sends_base64url_mime_and_refreshes_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    configure_gmail(monkeypatch)
    install_fake_google_auth(monkeypatch)
    gmail_api.send_gmail_api_email("recipient@example.com", "Subject", "Plain body", "<p>HTML body</p>")

    url, payload, credentials, timeout = FakeAuthorizedSession.calls[0]
    assert url == gmail_api.GMAIL_SEND_URL.format(user_id="sender%40example.com")
    assert timeout == (5, 20)
    assert FakeAuthorizedSession.refresh_performed
    assert credentials.kwargs["token"] is None
    assert credentials.kwargs["refresh_token"] == "refresh-token-test"
    assert credentials.kwargs["scopes"] == [gmail_api.GMAIL_SEND_SCOPE]
    message = decode_raw(payload["raw"])
    assert message["From"] == "sender@example.com"
    assert message["To"] == "recipient@example.com"
    assert message["Subject"] == "Subject"
    assert message.get_body(preferencelist=("plain",)).get_content().strip() == "Plain body"
    assert message.get_body(preferencelist=("html",)).get_content().strip() == "<p>HTML body</p>"


def test_missing_gmail_configuration_fails_without_exposing_settings(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    for field in ("gmail_client_id", "gmail_client_secret", "gmail_refresh_token", "gmail_sender_email"):
        monkeypatch.setattr(settings, field, None)
    caplog.set_level(logging.WARNING, logger="vaulttrace.email")
    with pytest.raises(EmailDeliveryError):
        gmail_api.send_gmail_api_email("private-recipient@example.com", "Subject", "Private OTP body")
    assert "GmailConfigurationError" in caplog.text
    assert "private-recipient@example.com" not in caplog.text
    assert "Private OTP body" not in caplog.text


def test_invalid_refresh_token_is_sanitized(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    configure_gmail(monkeypatch)
    install_fake_google_auth(monkeypatch)
    FakeAuthorizedSession.post_error = FakeRefreshError("refresh-token-test must not be logged")
    caplog.set_level(logging.WARNING, logger="vaulttrace.email")
    with pytest.raises(EmailDeliveryError):
        gmail_api.send_gmail_api_email("private-recipient@example.com", "Subject", "OTP body")
    assert "FakeRefreshError" in caplog.text
    assert "Gmail OAuth refresh failed" in caplog.text
    assert "refresh-token-test" not in caplog.text
    assert "private-recipient@example.com" not in caplog.text
    assert "OTP body" not in caplog.text


@pytest.mark.parametrize(
    ("status_code", "diagnostic"),
    [(403, "Gmail API denied the send request"), (429, "Gmail API rate limited the send request"), (503, "Gmail API is temporarily unavailable")],
)
def test_gmail_api_http_errors_are_sanitized(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, status_code: int, diagnostic: str) -> None:
    configure_gmail(monkeypatch)
    install_fake_google_auth(monkeypatch)
    FakeAuthorizedSession.response_status = status_code
    caplog.set_level(logging.WARNING, logger="vaulttrace.email")
    with pytest.raises(EmailDeliveryError):
        gmail_api.send_gmail_api_email("private-recipient@example.com", "Subject", "Secret message")
    assert f"http_status={status_code}" in caplog.text
    assert diagnostic in caplog.text
    assert "private-recipient@example.com" not in caplog.text
    assert "Secret message" not in caplog.text


@pytest.mark.parametrize("error", [TimeoutError("private timeout detail"), FakeRequestException("private network detail")])
def test_gmail_api_timeout_and_network_errors_do_not_log_messages(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, error: Exception) -> None:
    configure_gmail(monkeypatch)
    install_fake_google_auth(monkeypatch)
    FakeAuthorizedSession.post_error = error
    caplog.set_level(logging.WARNING, logger="vaulttrace.email")
    with pytest.raises(EmailDeliveryError):
        gmail_api.send_gmail_api_email("private-recipient@example.com", "Subject", "Secret message")
    assert type(error).__name__ in caplog.text
    assert str(error) not in caplog.text
    assert "private-recipient@example.com" not in caplog.text
    assert "Secret message" not in caplog.text


def test_signup_and_password_reset_otps_use_selected_gmail_transport(client, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.email_verifications import send_verification_otp

    configure_gmail(monkeypatch)
    install_fake_google_auth(monkeypatch)
    monkeypatch.setattr(settings, "email_provider", "gmail_api")
    signup_email = "gmail.signup@example.com"
    reset_email = "gmail.reset@example.com"

    with TestSession() as db:
        assert send_verification_otp(db, signup_email, "SIGNUP")
    with TestSession.begin() as db:
        viewer = db.scalar(select(Role).where(Role.name == "Viewer"))
        assert viewer is not None
        db.add(User(
            full_name="Gmail Reset User",
            username="gmail-reset-user",
            email=reset_email,
            password_hash="test-only-hash",
            role=viewer,
            is_active=True,
            email_verified=True,
            account_status="ACTIVE",
        ))
    with TestSession() as db:
        assert send_verification_otp(db, reset_email, "PASSWORD_RESET")

    assert len(FakeAuthorizedSession.calls) == 2
    signup_message = decode_raw(FakeAuthorizedSession.calls[0][1]["raw"])
    reset_message = decode_raw(FakeAuthorizedSession.calls[1][1]["raw"])
    assert signup_message["Subject"] == "VaultTrace email verification"
    assert reset_message["Subject"] == "VaultTrace email verification"
    assert signup_message["To"] == signup_email
    assert reset_message["To"] == reset_email
