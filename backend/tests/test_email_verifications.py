"""Signup OTP, reset OTP, SMTP failure, and session revocation tests."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import EmailVerification, PasswordResetAuthorization, Role, User
from app.services.email import EmailDeliveryError
from backend.tests.client import InProcessClient
from backend.tests.database import TestSession


def signup_request(email: str, username: str) -> dict[str, str]:
    """Return a valid signup request payload."""
    return {"full_name": "Test Applicant", "username": username, "email": email, "password": "safe-password-123", "confirm_password": "safe-password-123"}


def send_signup_code(client: InProcessClient, monkeypatch: pytest.MonkeyPatch, email: str) -> str:
    """Capture an OTP from the mocked SMTP integration."""
    issued: list[str] = []
    monkeypatch.setattr("app.services.email_verifications.send_otp_email", lambda _email, code: issued.append(code))
    response = client.post("/api/v1/auth/signup/send-otp", json={"email": email})
    assert response.status_code == 202
    assert issued and "otp" not in response.text.lower()
    return issued[0]


def create_reset_user() -> tuple[str, str]:
    """Create a verified, active account in the isolated test database."""
    email, password = "reset.user@example.com", "previous-password-123"
    with TestSession.begin() as db:
        viewer = db.scalar(select(Role).where(Role.name == "Viewer"))
        assert viewer is not None
        db.add(User(full_name="Reset User", username="reset-user", email=email, password_hash=hash_password(password), role=viewer, is_active=True, email_verified=True, account_status="ACTIVE"))
    return email, password


def test_signup_otp_verification_registration_and_replay_rejection(client: InProcessClient, monkeypatch: pytest.MonkeyPatch) -> None:
    email, code = "verified.signup@example.com", send_signup_code(client, monkeypatch, "verified.signup@example.com")
    with TestSession() as db:
        record = db.scalar(select(EmailVerification).where(EmailVerification.email == email))
        assert record is not None and record.otp_hash != code and record.purpose == "SIGNUP" and record.is_delivered
    assert client.post("/api/v1/auth/register", json=signup_request(email, "signup-user")).status_code == 400
    assert client.post("/api/v1/auth/signup/verify-otp", json={"email": email, "otp": "111111"}).status_code == 400
    assert client.post("/api/v1/auth/signup/verify-otp", json={"email": email, "otp": code}).status_code == 200
    assert client.post("/api/v1/auth/signup/verify-otp", json={"email": email, "otp": code}).status_code == 400
    registered = client.post("/api/v1/auth/register", json=signup_request(email, "signup-user"))
    assert registered.status_code == 201
    assert client.post("/api/v1/auth/register", json=signup_request(email, "another-name")).status_code == 400
    with TestSession() as db:
        user = db.scalar(select(User).where(User.email == email))
        proof = db.scalar(select(EmailVerification).where(EmailVerification.email == email))
        assert user is not None and not user.is_active and user.account_status == "PENDING" and user.email_verified
        assert proof is not None and proof.user_id == user.id


def test_signup_expiration_attempt_limit_and_resend_cooldown(client: InProcessClient, monkeypatch: pytest.MonkeyPatch) -> None:
    email, code = "otp.limits@example.com", send_signup_code(client, monkeypatch, "otp.limits@example.com")
    limited = client.post("/api/v1/auth/signup/send-otp", json={"email": email})
    assert limited.status_code == 429
    assert limited.headers.get("retry-after")
    for _ in range(5):
        assert client.post("/api/v1/auth/signup/verify-otp", json={"email": email, "otp": "000000"}).status_code == 400
    assert client.post("/api/v1/auth/signup/verify-otp", json={"email": email, "otp": code}).status_code == 400
    expired_email = "otp.expired@example.com"
    expired_code = send_signup_code(client, monkeypatch, expired_email)
    with TestSession.begin() as db:
        challenge = db.scalar(select(EmailVerification).where(EmailVerification.email == expired_email))
        assert challenge is not None
        challenge.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert client.post("/api/v1/auth/signup/verify-otp", json={"email": expired_email, "otp": expired_code}).status_code == 400


def test_resend_invalidates_an_already_verified_signup_proof(client: InProcessClient, monkeypatch: pytest.MonkeyPatch) -> None:
    email = "proof.resend@example.com"
    codes = iter(("123456", "654321"))
    issued: list[str] = []
    monkeypatch.setattr("app.services.email_verifications.secrets.randbelow", lambda _max: int(next(codes)))
    monkeypatch.setattr("app.services.email_verifications.send_otp_email", lambda _recipient, code: issued.append(code))
    assert client.post("/api/v1/auth/signup/send-otp", json={"email": email}).status_code == 202
    assert client.post("/api/v1/auth/signup/verify-otp", json={"email": email, "otp": issued[-1]}).status_code == 200
    with TestSession.begin() as db:
        challenge = db.scalar(select(EmailVerification).where(EmailVerification.email == email))
        assert challenge is not None
        challenge.last_sent_at = datetime.now(timezone.utc) - timedelta(seconds=61)
        challenge.created_at = datetime.now(timezone.utc) - timedelta(seconds=61)
    assert client.post("/api/v1/auth/signup/send-otp", json={"email": email}).status_code == 202
    assert client.post("/api/v1/auth/register", json=signup_request(email, "proof-resend")).status_code == 400
    assert client.post("/api/v1/auth/signup/verify-otp", json={"email": email, "otp": issued[-1]}).status_code == 200
    assert client.post("/api/v1/auth/register", json=signup_request(email, "proof-resend")).status_code == 201


def test_otp_purpose_is_separated_and_smtp_failure_is_not_delivered(client: InProcessClient, monkeypatch: pytest.MonkeyPatch) -> None:
    email, code = "purpose@example.com", send_signup_code(client, monkeypatch, "purpose@example.com")
    assert client.post("/api/v1/auth/verify-reset-otp", json={"email": email, "otp": code}).status_code == 400
    monkeypatch.setattr("app.services.email_verifications.send_otp_email", lambda *_args: (_ for _ in ()).throw(EmailDeliveryError("smtp unavailable")))
    failed_email = "smtp.failure@example.com"
    assert client.post("/api/v1/auth/signup/send-otp", json={"email": failed_email}).status_code == 503
    with TestSession() as db:
        challenge = db.scalar(select(EmailVerification).where(EmailVerification.email == failed_email))
        assert challenge is not None and not challenge.is_delivered and challenge.is_used


def test_failed_delivery_does_not_block_email_beyond_rate_window(client: InProcessClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.email_verifications import send_verification_otp

    failed_email = "retry.after.failure@example.com"
    monkeypatch.setattr(
        "app.services.email_verifications.send_otp_email",
        lambda *_args: (_ for _ in ()).throw(EmailDeliveryError("smtp unavailable")),
    )
    with TestSession() as db, pytest.raises(EmailDeliveryError):
        send_verification_otp(db, failed_email, "SIGNUP")
    with TestSession.begin() as db:
        challenge = db.scalar(select(EmailVerification).where(EmailVerification.email == failed_email))
        assert challenge is not None and challenge.is_used and not challenge.is_delivered
        challenge.last_sent_at = datetime.now(timezone.utc) - timedelta(hours=1, seconds=1)
        challenge.send_window_started_at = datetime.now(timezone.utc) - timedelta(hours=1, seconds=1)
        challenge.created_at = datetime.now(timezone.utc) - timedelta(hours=1, seconds=1)
    delivered: list[str] = []
    monkeypatch.setattr("app.services.email_verifications.send_otp_email", lambda _recipient, code: delivered.append(code))
    with TestSession() as db:
        assert send_verification_otp(db, failed_email, "SIGNUP")
    assert delivered


def test_database_error_returns_safe_503_and_logs_only_exception_type(client: InProcessClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    from fastapi import HTTPException
    from sqlalchemy.exc import OperationalError
    from app.api.v1.router import send_signup_otp
    from app.schemas.auth import OtpRequest

    def fail_database(*_args, **_kwargs):
        raise OperationalError("query", {}, Exception("sensitive database text"))

    monkeypatch.setattr("app.api.v1.router.send_verification_otp", fail_database)
    with TestSession() as db, pytest.raises(HTTPException) as caught:
        send_signup_otp(OtpRequest(email="db.failure@example.com"), db)
    assert caught.value.status_code == 503
    assert caught.value.detail != "sensitive database text"
    assert "OperationalError" in caplog.text
    assert "sensitive database text" not in caplog.text


def test_signup_otp_persists_delivered_digest_and_enforces_database_backed_limits(client: InProcessClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings
    from app.services.email_verifications import (
        VerificationCooldown,
        VerificationExpired,
        VerificationRateLimited,
        send_verification_otp,
        verify_verification_otp,
    )

    email = "persisted.limits@example.com"
    issued: list[str] = []
    monkeypatch.setattr(settings, "otp_max_sends_per_hour", 2)
    monkeypatch.setattr(settings, "otp_resend_cooldown_seconds", 60)
    monkeypatch.setattr("app.services.email_verifications.send_otp_email", lambda _to, code: issued.append(code))
    with TestSession() as db:
        assert send_verification_otp(db, email, "SIGNUP")
    with TestSession() as db:
        challenge = db.scalar(select(EmailVerification).where(EmailVerification.email == email))
        assert challenge is not None and challenge.is_delivered and challenge.otp_hash != issued[-1]
    with TestSession() as db:
        with pytest.raises(VerificationCooldown):
            send_verification_otp(db, email, "SIGNUP")
    with TestSession.begin() as db:
        challenge = db.scalar(select(EmailVerification).where(EmailVerification.email == email))
        assert challenge is not None
        challenge.last_sent_at = datetime.now(timezone.utc) - timedelta(seconds=61)
    with TestSession() as db:
        assert send_verification_otp(db, email, "SIGNUP")
    with TestSession.begin() as db:
        challenge = db.scalar(select(EmailVerification).where(EmailVerification.email == email).order_by(EmailVerification.created_at.desc()))
        assert challenge is not None
        challenge.last_sent_at = datetime.now(timezone.utc) - timedelta(seconds=61)
        challenge.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with TestSession() as db:
        with pytest.raises(VerificationRateLimited) as limited:
            send_verification_otp(db, email, "SIGNUP")
        assert 1 <= limited.value.retry_after <= 3600
    with TestSession() as db:
        with pytest.raises(VerificationExpired):
            verify_verification_otp(db, email, issued[-1], "SIGNUP")


def test_forgot_password_is_generic_and_reset_invalidates_old_password_and_session(client: InProcessClient, monkeypatch: pytest.MonkeyPatch) -> None:
    unknown = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
    assert unknown.status_code == 202
    email, old_password = create_reset_user()
    session_token = client.post("/api/v1/auth/login", json={"email": email, "password": old_password}).json()["access_token"]
    sent: list[str] = []
    monkeypatch.setattr("app.services.email_verifications.send_otp_email", lambda _recipient, code: sent.append(code))
    response = client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert response.status_code == 202 and sent
    reset = client.post("/api/v1/auth/verify-reset-otp", json={"email": email, "otp": sent[-1]})
    assert reset.status_code == 200
    auth = reset.json()["authorization_token"]
    assert client.post("/api/v1/auth/reset-password", json={"authorization_token": auth, "password": "new-safe-password-456", "confirm_password": "new-safe-password-456"}).status_code == 200
    assert client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {session_token}"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": email, "password": old_password}).status_code == 401
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "new-safe-password-456"})
    assert login.status_code == 200
    assert client.post("/api/v1/auth/reset-password", json={"authorization_token": auth, "password": "other-safe-password-789", "confirm_password": "other-safe-password-789"}).status_code == 400
    with TestSession() as db:
        authorization = db.scalar(select(PasswordResetAuthorization))
        assert authorization is not None and authorization.is_used


def test_reset_authorization_expiration_and_invalid_otp(client: InProcessClient, monkeypatch: pytest.MonkeyPatch) -> None:
    email, _old_password = create_reset_user()
    codes: list[str] = []
    monkeypatch.setattr("app.services.email_verifications.send_otp_email", lambda _recipient, code: codes.append(code))
    client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert client.post("/api/v1/auth/verify-reset-otp", json={"email": email, "otp": "000000"}).status_code == 400
    valid = client.post("/api/v1/auth/verify-reset-otp", json={"email": email, "otp": codes[-1]})
    assert valid.status_code == 200
    token = valid.json()["authorization_token"]
    with TestSession.begin() as db:
        authorization = db.scalar(select(PasswordResetAuthorization))
        assert authorization is not None
        authorization.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    response = client.post("/api/v1/auth/reset-password", json={"authorization_token": token, "password": "new-safe-password-456", "confirm_password": "new-safe-password-456"})
    assert response.status_code == 400
