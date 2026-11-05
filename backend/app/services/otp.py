"""Secure email one-time-password lifecycle and throttling."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import OtpChallenge, User
from app.services.email import EmailDeliveryError, send_otp_email


class OtpError(Exception):
    """Base class for OTP workflow errors."""


class OtpCooldown(OtpError):
    """Raised when another code is requested before cooldown expires."""

    def __init__(self, retry_after: int):
        self.retry_after = retry_after


class OtpRateLimited(OtpError):
    """Raised after the per-email send limit is reached."""

    def __init__(self, retry_after: int):
        self.retry_after = retry_after


class OtpInvalid(OtpError):
    """Raised for an unknown, incorrect, locked, or already used OTP."""


class OtpExpired(OtpError):
    """Raised when a verification code has expired."""


class OtpNotVerified(OtpError):
    """Raised when signup is attempted without verified email proof."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: datetime) -> datetime:
    """Normalize SQLite's naive test datetimes to UTC-aware values."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _digest(email: str, otp: str) -> str:
    """Create a keyed SHA-256 digest so six-digit values cannot be precomputed offline."""
    key = (settings.otp_hash_secret or settings.jwt_secret_key).encode("utf-8")
    return hmac.new(key, f"{email}:{otp}".encode("utf-8"), hashlib.sha256).hexdigest()


def request_otp(db: Session, email: str) -> bool:
    """Create or replace a code; return false for already registered addresses."""
    email = email.strip().lower()
    now = _now()
    with db.begin():
        registered_user = db.scalar(select(User).where(User.email == email))
        if registered_user is not None and registered_user.email_verified:
            return False
        challenge = db.scalar(select(OtpChallenge).where(OtpChallenge.email == email).with_for_update())
        if challenge and challenge.verified_at is not None and challenge.consumed_at is None and _utc(challenge.expires_at) > now:
            return True
        if challenge:
            seconds_since_send = (now - _utc(challenge.last_sent_at)).total_seconds()
            if seconds_since_send < settings.otp_resend_cooldown_seconds:
                raise OtpCooldown(settings.otp_resend_cooldown_seconds - int(seconds_since_send))
            window_started = _utc(challenge.send_window_started_at)
            if now - window_started >= timedelta(hours=1):
                challenge.send_count = 0
                challenge.send_window_started_at = now
            if challenge.send_count >= settings.otp_max_sends_per_hour:
                retry_after = max(1, int((window_started + timedelta(hours=1) - now).total_seconds()) + 1)
                raise OtpRateLimited(retry_after)

        otp = f"{secrets.randbelow(1_000_000):06d}"
        if challenge is None:
            challenge = OtpChallenge(
                email=email,
                otp_digest=_digest(email, otp),
                expires_at=now + timedelta(minutes=settings.otp_expiration_minutes),
                created_at=now,
                last_sent_at=now,
                send_window_started_at=now,
                send_count=1,
            )
            db.add(challenge)
        else:
            challenge.otp_digest = _digest(email, otp)
            challenge.expires_at = now + timedelta(minutes=settings.otp_expiration_minutes)
            challenge.created_at = now
            challenge.last_sent_at = now
            challenge.send_count += 1
            challenge.attempt_count = 0
            challenge.verified_at = None
            challenge.consumed_at = None
            challenge.locked_at = None
    try:
        send_otp_email(email, otp)
    except EmailDeliveryError:
        # Clear the just-issued code while preserving cooldown/rate-limit state.
        with db.begin():
            failed_challenge = db.scalar(select(OtpChallenge).where(OtpChallenge.email == email).with_for_update())
            if failed_challenge and hmac.compare_digest(failed_challenge.otp_digest, _digest(email, otp)):
                failed_challenge.otp_digest = _digest(email, "invalidated")
                failed_challenge.expires_at = now
        raise
    return True


def verify_otp(db: Session, email: str, otp: str) -> None:
    """Verify one code, enforcing expiry, use-once semantics, and attempt limits."""
    email = email.strip().lower()
    now = _now()
    invalid = False
    locked = False
    with db.begin():
        challenge = db.scalar(select(OtpChallenge).where(OtpChallenge.email == email).with_for_update())
        if challenge is None or challenge.consumed_at is not None or challenge.verified_at is not None:
            raise OtpInvalid
        if _utc(challenge.expires_at) <= now:
            raise OtpExpired
        if challenge.locked_at is not None or challenge.attempt_count >= settings.otp_max_attempts:
            raise OtpInvalid
        if not hmac.compare_digest(challenge.otp_digest, _digest(email, otp)):
            challenge.attempt_count += 1
            if challenge.attempt_count >= settings.otp_max_attempts:
                challenge.locked_at = now
                locked = True
            invalid = True
        else:
            challenge.verified_at = now
            existing_user = db.scalar(select(User).where(User.email == email))
            if existing_user is not None:
                existing_user.email_verified = True
    if invalid:
        if locked:
            raise OtpInvalid("Too many verification attempts")
        raise OtpInvalid
