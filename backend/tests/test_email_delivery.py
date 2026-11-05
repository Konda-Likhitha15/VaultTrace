"""SMTP transport diagnostics and safe authentication configuration tests."""

import logging
import smtplib

import pytest

from app.core.config import Settings, settings
from app.services import email as email_service
from app.services.email import EmailDeliveryError, send_email


class FakeSMTP:
    """Small SMTP stand-in that records transport calls without networking."""

    def __init__(self, host: str, port: int, timeout: int):
        self.host, self.port, self.timeout = host, port, timeout
        self.tls_started = False
        self.logged_in: tuple[str, str] | None = None
        self.message = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def starttls(self):
        self.tls_started = True

    def login(self, username: str, password: str):
        self.logged_in = (username, password)

    def send_message(self, message):
        self.message = message


def test_email_delivery_uses_starttls_auth_and_configured_sender(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSMTP("smtp.gmail.com", 587, 10)
    monkeypatch.setattr(email_service.smtplib, "SMTP", lambda *args, **kwargs: fake)
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_use_ssl", False)
    monkeypatch.setattr(settings, "smtp_starttls", True)
    monkeypatch.setattr(settings, "smtp_use_tls", None)
    monkeypatch.setattr(settings, "smtp_username", "sender@example.com")
    monkeypatch.setattr(settings, "smtp_password", "not-logged-test-secret")
    monkeypatch.setattr(settings, "smtp_from_email", "sender@example.com")

    send_email("recipient@example.com", "Subject", "Body")

    assert (fake.host, fake.port, fake.timeout) == ("smtp.gmail.com", 587, 10)
    assert fake.tls_started
    assert fake.logged_in == ("sender@example.com", "not-logged-test-secret")
    assert fake.message["From"] == "sender@example.com"
    assert fake.message["To"] == "recipient@example.com"


def test_smtp_authentication_failure_logs_only_safe_diagnostics(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    class AuthFailureSMTP(FakeSMTP):
        def login(self, _username: str, _password: str):
            raise smtplib.SMTPAuthenticationError(535, b"private server diagnostic")

    monkeypatch.setattr(email_service.smtplib, "SMTP", lambda *_args, **_kwargs: AuthFailureSMTP("smtp.gmail.com", 587, 10))
    monkeypatch.setattr(settings, "smtp_use_ssl", False)
    monkeypatch.setattr(settings, "smtp_starttls", True)
    monkeypatch.setattr(settings, "smtp_use_tls", None)
    monkeypatch.setattr(settings, "smtp_username", "sender@example.com")
    monkeypatch.setattr(settings, "smtp_password", "never-log-this-password")
    caplog.set_level(logging.WARNING, logger="vaulttrace.email")

    with pytest.raises(EmailDeliveryError):
        send_email("recipient@example.com", "Subject", "OTP body must not appear")

    assert "SMTPAuthenticationError" in caplog.text
    assert "smtp_code=535" in caplog.text
    assert "SMTP authentication rejected" in caplog.text
    assert "private server diagnostic" not in caplog.text
    assert "never-log-this-password" not in caplog.text
    assert "OTP body must not appear" not in caplog.text
    assert "recipient@example.com" not in caplog.text


def test_smtp_connection_failure_logs_exception_type_without_os_error_text(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    def fail_connection(*_args, **_kwargs):
        raise OSError("secret-looking connection detail")

    monkeypatch.setattr(email_service.smtplib, "SMTP", fail_connection)
    monkeypatch.setattr(settings, "smtp_use_ssl", False)
    caplog.set_level(logging.WARNING, logger="vaulttrace.email")

    with pytest.raises(EmailDeliveryError):
        send_email("recipient@example.com", "Subject", "Body")

    assert "OSError" in caplog.text
    assert "SMTP network operation failed" in caplog.text
    assert "secret-looking connection detail" not in caplog.text


def test_settings_accept_environment_overrides_and_reject_invalid_otp_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTP_MAX_SENDS_PER_HOUR", "10")
    monkeypatch.setenv("OTP_RESEND_COOLDOWN_SECONDS", "60")
    monkeypatch.setenv("OTP_EXPIRATION_MINUTES", "5")
    configured = Settings(
        _env_file=None,
        DATABASE_URL="sqlite+pysqlite:///:memory:",
        JWT_SECRET_KEY="test-only-secret",
    )
    assert configured.otp_max_sends_per_hour == 10
    assert configured.otp_resend_cooldown_seconds == 60
    assert configured.otp_expiration_minutes == 5
    assert configured.email_provider == "mailpit"
    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            DATABASE_URL="sqlite+pysqlite:///:memory:",
            JWT_SECRET_KEY="test-only-secret",
            OTP_MAX_SENDS_PER_HOUR="0",
        )
    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            DATABASE_URL="sqlite+pysqlite:///:memory:",
            JWT_SECRET_KEY="test-only-secret",
            EMAIL_PROVIDER="unknown",
        )
