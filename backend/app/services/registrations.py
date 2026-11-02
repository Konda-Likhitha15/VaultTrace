"""Business logic for converting verified email into a pending application."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import EmailVerification, OtpChallenge, RegistrationApplication, Role, User
from app.schemas.auth import RegistrationRequest
from app.services.otp import OtpExpired, OtpNotVerified
from app.services.email_verifications import SignupProofRequired, _aware


class RegistrationConflict(Exception):
    """Raised when the requested email or username is already in use."""


def create_registration_application(db: Session, request: RegistrationRequest) -> RegistrationApplication:
    """Consume verified OTP proof and create an inactive pending account."""
    email = str(request.email).strip().lower()
    username = request.username.strip().lower()
    now = datetime.now(timezone.utc)
    try:
        with db.begin():
            proof = db.scalar(select(EmailVerification).where(
                EmailVerification.email == email,
                EmailVerification.purpose == "SIGNUP",
                EmailVerification.is_verified.is_(True),
                EmailVerification.is_used.is_(True),
                EmailVerification.user_id.is_(None),
            ).order_by(EmailVerification.created_at.desc()).limit(1).with_for_update())
            challenge = None
            if proof is None:
                challenge = db.scalar(select(OtpChallenge).where(OtpChallenge.email == email).with_for_update())
                if challenge is None or challenge.verified_at is None or challenge.consumed_at is not None:
                    raise OtpNotVerified
                if _aware(challenge.expires_at) <= now:
                    raise OtpExpired
            elif _aware(proof.expires_at) <= now:
                raise OtpExpired
            if db.scalar(select(User.id).where((User.email == email) | (User.username == username))) is not None:
                raise RegistrationConflict
            viewer = db.scalar(select(Role).where(Role.name == "Viewer"))
            if viewer is None:
                raise RuntimeError("Built-in Viewer role is missing; apply database migrations first")
            user = User(
                full_name=request.full_name.strip(),
                username=username,
                email=email,
                phone_number=request.phone_number.strip() if request.phone_number else None,
                password_hash=hash_password(request.password.get_secret_value()),
                role=viewer,
                is_active=False,
                email_verified=True,
                account_status="PENDING",
            )
            db.add(user)
            db.flush()
            application = RegistrationApplication(user_id=user.id, email_verified=True, approval_status="PENDING")
            db.add(application)
            if proof is not None:
                proof.user_id = user.id
            elif challenge is not None:
                challenge.consumed_at = now
            db.flush()
    except IntegrityError as exc:
        raise RegistrationConflict from exc
    return application
