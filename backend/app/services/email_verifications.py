"""Purpose-aware OTP delivery, verification, and password reset operations."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models import EmailVerification, PasswordResetAuthorization, User
from app.services.email import EmailDeliveryError, send_otp_email


class VerificationError(Exception):
    """Base exception for email verification workflows."""


class VerificationInvalid(VerificationError):
    """OTP or reset authorization is invalid, consumed, or exhausted."""


class VerificationExpired(VerificationError):
    """OTP or reset authorization has expired."""


class VerificationCooldown(VerificationError):
    """An OTP was requested before the resend cooldown elapsed."""

    def __init__(self, retry_after: int):
        self.retry_after = retry_after


class VerificationRateLimited(VerificationError):
    """The per-address hourly send limit was reached."""


class SignupProofRequired(VerificationError):
    """No unused verified signup proof exists for the requested email."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _otp_hash(email: str, purpose: str, otp: str) -> str:
    """Return a keyed digest so database disclosure does not enable OTP guessing."""
    key = (settings.otp_hash_secret or settings.jwt_secret_key).encode()
    return hmac.new(key, f"{purpose}:{email}:{otp}".encode(), hashlib.sha256).hexdigest()


def send_verification_otp(db: Session, email: str, purpose: str) -> bool:
    """Issue and email an OTP; false means a signup address is already registered or reset email is unknown."""
    if purpose not in {"SIGNUP", "PASSWORD_RESET"}:
        raise ValueError("Unsupported verification purpose")
    address = email.strip().lower()
    now = _now()
    code = f"{secrets.randbelow(1_000_000):06d}"
    verification_id = None
    with db.begin():
        user = db.scalar(select(User).where(User.email == address).with_for_update(of=User))
        if purpose == "SIGNUP" and user is not None:
            return False
        if purpose == "PASSWORD_RESET" and user is None:
            return False
        previous = db.scalar(
            select(EmailVerification)
            .where(EmailVerification.email == address, EmailVerification.purpose == purpose)
            .order_by(EmailVerification.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        if previous is not None:
            elapsed = (now - _aware(previous.last_sent_at)).total_seconds()
            if elapsed < settings.otp_resend_cooldown_seconds:
                raise VerificationCooldown(max(1, settings.otp_resend_cooldown_seconds - int(elapsed)))
            window_start = _aware(previous.send_window_started_at)
            count = previous.send_count
            if now - window_start >= timedelta(hours=1):
                window_start, count = now, 0
            if count >= settings.otp_max_sends_per_hour:
                raise VerificationRateLimited
            previous.send_count = count + 1
            previous.send_window_started_at = window_start
        # All prior records are invalidated, including verified signup proofs.
        db.query(EmailVerification).filter(
            EmailVerification.email == address,
            EmailVerification.purpose == purpose,
        ).update(
            {EmailVerification.is_used: True, EmailVerification.is_verified: False},
            synchronize_session=False,
        )
        challenge = EmailVerification(
            user_id=user.id if purpose == "PASSWORD_RESET" and user else None,
            email=address,
            otp_hash=_otp_hash(address, purpose, code),
            purpose=purpose,
            expires_at=now + timedelta(minutes=settings.otp_expiration_minutes),
            attempts=0,
            is_verified=False,
            is_used=False,
            is_delivered=False,
            last_sent_at=now,
            send_window_started_at=now if previous is None else previous.send_window_started_at,
            send_count=1 if previous is None else previous.send_count,
            created_at=now,
        )
        db.add(challenge)
        db.flush()
        verification_id = challenge.id
    try:
        send_otp_email(address, code)
    except EmailDeliveryError:
        # It remains unusable: never mark the email as delivered on SMTP failure.
        with db.begin():
            failed = db.scalar(select(EmailVerification).where(EmailVerification.id == verification_id).with_for_update())
            if failed is not None:
                failed.is_used = True
                failed.otp_hash = _otp_hash(address, purpose, "delivery-failed")
        raise
    with db.begin():
        delivered = db.scalar(select(EmailVerification).where(EmailVerification.id == verification_id).with_for_update())
        if delivered is None or delivered.is_used:
            raise VerificationInvalid
        delivered.is_delivered = True
    return True


def verify_verification_otp(db: Session, email: str, otp: str, purpose: str) -> EmailVerification:
    """Atomically verify and consume the latest delivered code for its purpose."""
    address, now = email.strip().lower(), _now()
    wrong = False
    expired = False
    with db.begin():
        challenge = db.scalar(
            select(EmailVerification)
            .where(EmailVerification.email == address, EmailVerification.purpose == purpose)
            .order_by(EmailVerification.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        if challenge is None or not challenge.is_delivered or challenge.is_used or challenge.is_verified:
            raise VerificationInvalid
        if _aware(challenge.expires_at) <= now:
            challenge.is_used = True
            expired = True
        elif challenge.attempts >= settings.otp_max_attempts:
            challenge.is_used = True
            raise VerificationInvalid("Maximum verification attempts exceeded")
        elif not hmac.compare_digest(challenge.otp_hash, _otp_hash(address, purpose, otp)):
            challenge.attempts += 1
            if challenge.attempts >= settings.otp_max_attempts:
                challenge.is_used = True
            wrong = True
        else:
            challenge.is_verified = True
            challenge.is_used = True
            challenge.verified_at = now
    if expired:
        raise VerificationExpired
    if wrong:
        raise VerificationInvalid
    return challenge


def consume_signup_proof(db: Session, email: str) -> EmailVerification:
    """Lock an unused verified signup proof so registration can bind it to one user."""
    address = email.strip().lower()
    with db.begin():
        proof = db.scalar(
            select(EmailVerification)
            .where(
                EmailVerification.email == address,
                EmailVerification.purpose == "SIGNUP",
                EmailVerification.is_verified.is_(True),
                EmailVerification.is_used.is_(True),
                EmailVerification.user_id.is_(None),
            )
            .order_by(EmailVerification.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        if proof is None or _aware(proof.expires_at) <= _now():
            raise SignupProofRequired
        return proof


def create_reset_authorization(db: Session, user_id: int) -> str:
    """Persist only the digest of a high-entropy single-use authorization token."""
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()
    now = _now()
    with db.begin():
        db.add(PasswordResetAuthorization(
            user_id=user_id,
            token_hash=digest,
            expires_at=now + timedelta(minutes=settings.password_reset_token_expire_minutes),
            is_used=False,
            created_at=now,
        ))
    return token


def reset_password(db: Session, authorization: str, password: str) -> None:
    """Consume reset authorization, update the Argon2 hash, and revoke all JWT sessions."""
    digest, now = hashlib.sha256(authorization.encode()).hexdigest(), _now()
    expired = False
    with db.begin():
        reset = db.scalar(select(PasswordResetAuthorization).where(PasswordResetAuthorization.token_hash == digest).with_for_update())
        if reset is None or reset.is_used:
            raise VerificationInvalid
        if _aware(reset.expires_at) <= now:
            reset.is_used = True
            expired = True
        else:
            user = db.scalar(select(User).where(User.id == reset.user_id).with_for_update(of=User))
            if user is None:
                raise VerificationInvalid
            user.password_hash = hash_password(password)
            user.token_version += 1
            reset.is_used = True
            reset.used_at = now
            db.query(EmailVerification).filter(
                EmailVerification.user_id == user.id,
                EmailVerification.purpose == "PASSWORD_RESET",
                EmailVerification.is_used.is_(False),
            ).update({EmailVerification.is_used: True}, synchronize_session=False)
    if expired:
        raise VerificationExpired
