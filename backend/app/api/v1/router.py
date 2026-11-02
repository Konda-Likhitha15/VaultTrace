"""Version one API route aggregation and authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import get_current_user, get_token_claims, require_roles
from app.api.v1.admin import router as admin_router
from app.db.session import get_db
from app.models import User
from app.schemas.auth import Credentials, OtpRequest, OtpResponse, OtpVerificationRequest, PasswordResetRequest, PasswordResetOtpVerificationRequest, ResetAuthorizationResponse, RegistrationRequest, RegistrationResponse, TokenResponse, UserResponse
from app.services.auth import InvalidCredentials, revoke_access_token, authenticate_user
from app.services.email import EmailDeliveryError
from app.services.otp import OtpCooldown, OtpExpired, OtpInvalid, OtpNotVerified, OtpRateLimited, request_otp, verify_otp
from app.services.registrations import RegistrationConflict, create_registration_application
from app.services.email_verifications import VerificationCooldown, VerificationExpired, VerificationInvalid, VerificationRateLimited, create_reset_authorization, reset_password, send_verification_otp, verify_verification_otp
from app.core.config import settings

auth_router = APIRouter(prefix="/auth", tags=["authentication"])
api_router = APIRouter()


def public_user(user: User) -> UserResponse:
    """Convert a model to the public account response shape."""
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name, username=user.username, role=user.role.name, account_status=user.account_status)


@auth_router.post("/otp/request", response_model=OtpResponse)
@auth_router.post("/otp/resend", response_model=OtpResponse)
def send_email_otp(payload: OtpRequest, db: Session = Depends(get_db)) -> OtpResponse:
    """Send or replace an email OTP without returning the code to the client."""
    try:
        request_otp(db, str(payload.email))
    except OtpCooldown as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Please wait before requesting another code", headers={"Retry-After": str(max(1, exc.retry_after))}) from exc
    except OtpRateLimited as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many codes requested; try again later") from exc
    except EmailDeliveryError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Email delivery is temporarily unavailable") from exc
    return OtpResponse(message="If this address can be registered, a verification code has been sent.")


@auth_router.post("/signup/send-otp", response_model=OtpResponse, status_code=status.HTTP_202_ACCEPTED)
def send_signup_otp(payload: OtpRequest, db: Session = Depends(get_db)) -> OtpResponse:
    """Send a purpose-bound signup verification code."""
    try:
        send_verification_otp(db, str(payload.email), "SIGNUP")
    except VerificationCooldown as exc:
        raise HTTPException(status_code=429, detail="Please wait before requesting another code", headers={"Retry-After": str(exc.retry_after)}) from exc
    except VerificationRateLimited as exc:
        raise HTTPException(status_code=429, detail="Too many codes requested; try again later") from exc
    except EmailDeliveryError as exc:
        raise HTTPException(status_code=503, detail="Email delivery is temporarily unavailable") from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Email verification is temporarily unavailable. Check the database connection and migrations.") from exc
    return OtpResponse(message="If this address can be registered, a verification code has been sent.")


@auth_router.post("/signup/verify-otp", response_model=OtpResponse)
def verify_signup_otp(payload: OtpVerificationRequest, db: Session = Depends(get_db)) -> OtpResponse:
    """Verify and consume a signup OTP, retaining one-time proof for registration."""
    try:
        verify_verification_otp(db, str(payload.email), payload.otp, "SIGNUP")
    except VerificationExpired as exc:
        raise HTTPException(status_code=400, detail="Verification code expired") from exc
    except VerificationInvalid as exc:
        raise HTTPException(status_code=400, detail="Verification code is invalid or already used") from exc
    return OtpResponse(message="Email verified. You may submit your registration.")


@auth_router.post("/forgot-password", response_model=OtpResponse, status_code=status.HTTP_202_ACCEPTED)
def forgot_password(payload: OtpRequest, db: Session = Depends(get_db)) -> OtpResponse:
    """Send a reset code when eligible; response remains generic to prevent enumeration."""
    try:
        send_verification_otp(db, str(payload.email), "PASSWORD_RESET")
    except (VerificationCooldown, VerificationRateLimited, EmailDeliveryError):
        pass
    return OtpResponse(message="If an account matches this address, a password reset code has been sent.")


@auth_router.post("/verify-reset-otp", response_model=ResetAuthorizationResponse)
def verify_reset_otp(payload: PasswordResetOtpVerificationRequest, db: Session = Depends(get_db)) -> ResetAuthorizationResponse:
    """Verify a reset code and issue a short-lived, single-use authorization."""
    try:
        challenge = verify_verification_otp(db, str(payload.email), payload.otp, "PASSWORD_RESET")
        if challenge.user_id is None:
            raise VerificationInvalid
        token = create_reset_authorization(db, challenge.user_id)
    except VerificationExpired as exc:
        raise HTTPException(status_code=400, detail="Verification code expired") from exc
    except VerificationInvalid as exc:
        raise HTTPException(status_code=400, detail="Verification code is invalid or already used") from exc
    return ResetAuthorizationResponse(authorization_token=token, expires_in_seconds=settings.password_reset_token_expire_minutes * 60)


@auth_router.post("/reset-password", response_model=OtpResponse)
def finish_password_reset(payload: PasswordResetRequest, db: Session = Depends(get_db)) -> OtpResponse:
    """Change a password only with a valid single-use reset authorization."""
    try:
        reset_password(db, payload.authorization_token, payload.password.get_secret_value())
    except VerificationExpired as exc:
        raise HTTPException(status_code=400, detail="Password reset authorization expired") from exc
    except VerificationInvalid as exc:
        raise HTTPException(status_code=400, detail="Password reset authorization is invalid or already used") from exc
    return OtpResponse(message="Password reset successfully. Please sign in again.")


@auth_router.post("/otp/verify", response_model=OtpResponse)
def verify_email_otp(payload: OtpVerificationRequest, db: Session = Depends(get_db)) -> OtpResponse:
    """Verify a six-digit email code exactly once."""
    try:
        verify_otp(db, str(payload.email), payload.otp)
    except OtpExpired as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code expired") from exc
    except OtpInvalid as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code is invalid or already used") from exc
    return OtpResponse(message="Email verified. You may submit your registration.")


@auth_router.post("/register", response_model=RegistrationResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegistrationRequest, db: Session = Depends(get_db)) -> RegistrationResponse:
    """Create a pending application using verified email proof."""
    try:
        application = create_registration_application(db, payload)
    except OtpExpired as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification expired; request a new code") from exc
    except RegistrationConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email or username is already registered") from exc
    except OtpNotVerified as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verify your email before submitting") from exc
    return RegistrationResponse(message="Registration submitted for administrator review.", application_id=application.id, approval_status=application.approval_status)


@auth_router.post("/login", response_model=TokenResponse)
def login(payload: Credentials, db: Session = Depends(get_db)) -> TokenResponse:
    """Authenticate a user and issue a short-lived bearer token."""
    try:
        user, token, expiry = authenticate_user(db, payload)
    except InvalidCredentials as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password", headers={"WWW-Authenticate": "Bearer"}) from exc
    return TokenResponse(access_token=token, expires_at=expiry, user=public_user(user))


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(claims: dict = Depends(get_token_claims), db: Session = Depends(get_db)) -> Response:
    """Revoke the current bearer token."""
    revoke_access_token(db, claims)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


api_router.include_router(auth_router)


@api_router.get("/users/me", response_model=UserResponse, tags=["users"])
def read_current_user(user: User = Depends(get_current_user)) -> UserResponse:
    """Return the authenticated user's public profile."""
    return public_user(user)


@api_router.get("/admin", tags=["authorization"])
def administrator_dashboard(user: User = Depends(require_roles("Administrator"))) -> dict[str, str]:
    """Example route protected for administrators."""
    return {"message": f"Administrator access granted to {user.email}"}


@api_router.get("/owner", tags=["authorization"])
def owner_dashboard(user: User = Depends(require_roles("Administrator", "Owner"))) -> dict[str, str]:
    """Example route available to owners and administrators."""
    return {"message": f"Owner access granted to {user.email}"}


api_router.include_router(admin_router)
