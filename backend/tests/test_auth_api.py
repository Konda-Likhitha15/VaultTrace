"""Registration, OTP, admin workflow, and access-control integration tests."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.security import hash_password, verify_password
from app.api.v1.router import change_current_password, update_current_user
from app.core.config import settings
from app.models import AuditLog, OtpChallenge, RegistrationApplication, Role, User
from app.schemas.auth import PasswordChangeRequest, ProfileUpdateRequest
from app.bootstrap_admin import bootstrap_admin
from app.services.admin import dashboard_overview
from backend.tests.client import InProcessClient
from backend.tests.database import TestSession


def issue_otp(client: InProcessClient, monkeypatch: pytest.MonkeyPatch, email: str) -> tuple[str, list[str]]:
    """Request a code while capturing delivery through the mocked mailer."""
    codes: list[str] = []
    monkeypatch.setattr("app.services.otp.send_otp_email", lambda _recipient, code: codes.append(code))
    response = client.post("/api/v1/auth/otp/request", json={"email": email})
    assert response.status_code == 200
    assert "otp" not in response.text.lower()
    assert codes
    return codes[-1], codes


def submit_signup(client: InProcessClient, email: str, otp: str, username: str | None = None):
    """Complete email verification then submit the pending application."""
    verification = client.post("/api/v1/auth/otp/verify", json={"email": email, "otp": otp})
    assert verification.status_code == 200
    return client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "New VaultTrace User",
            "username": username or email.split("@")[0],
            "email": email,
            "phone_number": "+1-555-0100",
            "password": "Long-enough-secret1A!",
            "confirm_password": "Long-enough-secret1A!",
        },
    )


def create_admin() -> tuple[int, str, str]:
    """Create a test administrator with a properly hashed password."""
    email = "admin.integration@example.com"
    password = "Admin-test-password1!"
    with TestSession.begin() as session:
        role = session.scalar(select(Role).where(Role.name == "Administrator"))
        assert role is not None
        admin = User(
            full_name="Integration Administrator",
            username="integration-admin",
            email=email,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
            email_verified=True,
            account_status="ACTIVE",
        )
        session.add(admin)
        session.flush()
        admin_id = admin.id
    return admin_id, email, password


def create_active_user() -> tuple[str, str]:
    """Create an active Viewer used to test role-denied routes."""
    email, password = "active.viewer@example.com", "Viewer-test-password1!"
    with TestSession.begin() as session:
        role = session.scalar(select(Role).where(Role.name == "Viewer"))
        assert role is not None
        session.add(User(full_name="Active Viewer", username="active-viewer", email=email, password_hash=hash_password(password), role=role, is_active=True, email_verified=True, account_status="ACTIVE"))
    return email, password


def admin_headers(client: InProcessClient, email: str, password: str) -> dict[str, str]:
    """Authenticate an administrator through the public login endpoint."""
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_profile_update_and_password_change_require_current_password(client: InProcessClient) -> None:
    """Only the signed-in user can update editable fields and change their password."""
    _admin_id, email, old_password = create_admin()
    with TestSession() as session:
        user = session.get(User, _admin_id)
        assert user is not None
        profile = update_current_user(ProfileUpdateRequest(full_name="Updated Admin", username="updated-admin", phone_number="+1 555 0101"), None, user, session)
        assert profile.full_name == "Updated Admin" and profile.username == "updated-admin"
        assert profile.email == email and profile.role == "Administrator"
    with TestSession() as session:
        user = session.get(User, _admin_id)
        assert user is not None
        bad_current = PasswordChangeRequest(current_password="wrong-current-password", password="New-admin-password1!", confirm_password="New-admin-password1!")
        with pytest.raises(HTTPException) as rejected:
            change_current_password(bad_current, None, user, session)
        assert rejected.value.status_code == 400
        with pytest.raises(ValueError):
            PasswordChangeRequest(current_password=old_password, password="weakpassword", confirm_password="weakpassword")
        change = PasswordChangeRequest(current_password=old_password, password="New-admin-password1!", confirm_password="New-admin-password1!")
        response = change_current_password(change, None, user, session)
        assert response.status_code == 204
        assert user.token_version == 1
        assert verify_password("New-admin-password1!", user.password_hash)
        assert not verify_password(old_password, user.password_hash)


def test_profile_update_rejects_duplicate_username(client: InProcessClient) -> None:
    _admin_id, email, password = create_admin()
    create_active_user()
    del email, password
    with TestSession() as session:
        user = session.get(User, _admin_id)
        assert user is not None
        with pytest.raises(HTTPException) as response:
            update_current_user(ProfileUpdateRequest(full_name="Integration Administrator", username="active-viewer", phone_number=None), None, user, session)
        assert response.value.status_code == 409


def test_admin_dashboard_aggregates_existing_document_tables(client: InProcessClient) -> None:
    with TestSession() as session:
        overview = dashboard_overview(session)
    assert overview["total_documents"] == 0
    assert overview["active_document_shares"] == 0


def test_admin_bootstrap_creates_once_and_never_resets_existing_account(client: InProcessClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Bootstrap uses configured credentials and does not rewrite an existing admin."""
    monkeypatch.setattr("app.bootstrap_admin.SessionLocal", TestSession)
    monkeypatch.setattr(settings, "admin_bootstrap_email", "bootstrap@example.com")
    monkeypatch.setattr(settings, "admin_bootstrap_username", "bootstrap-admin")
    monkeypatch.setattr(settings, "admin_bootstrap_password", "Initial-admin-password1!")
    monkeypatch.setattr(settings, "admin_bootstrap_full_name", "Bootstrap Admin")
    assert bootstrap_admin() is True
    with TestSession() as session:
        admin = session.scalar(select(User).where(User.email == "bootstrap@example.com"))
        assert admin is not None and admin.role.name == "Administrator"
        bootstrap_event = session.scalar(select(AuditLog).where(AuditLog.action == "ADMIN_BOOTSTRAPPED", AuditLog.target_user_id == admin.id))
        assert bootstrap_event is not None and bootstrap_event.actor_id is None and bootstrap_event.outcome == "SUCCESS"
        original_hash = admin.password_hash
        assert admin.email_verified and admin.account_status == "ACTIVE"
    # A rerun remains a no-op when the account exists; no new password is used.
    monkeypatch.setattr(settings, "admin_bootstrap_password", "weak-legacy-password")
    assert bootstrap_admin() is False
    with TestSession() as session:
        admin = session.scalar(select(User).where(User.email == "bootstrap@example.com"))
        assert admin is not None and admin.password_hash == original_hash


def test_admin_bootstrap_rejects_passwords_that_miss_creation_policy(client: InProcessClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.bootstrap_admin.SessionLocal", TestSession)
    monkeypatch.setattr(settings, "admin_bootstrap_email", "bootstrap@example.com")
    monkeypatch.setattr(settings, "admin_bootstrap_username", "bootstrap-admin")
    monkeypatch.setattr(settings, "admin_bootstrap_password", "weak-password-only")
    monkeypatch.setattr(settings, "admin_bootstrap_full_name", "Bootstrap Admin")
    with pytest.raises(ValueError, match="does not meet the password policy"):
        bootstrap_admin()


def test_otp_signup_pending_then_admin_approval_and_login(client: InProcessClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise OTP signup through approval and active user login."""
    code, _codes = issue_otp(client, monkeypatch, "applicant@example.com")
    assert len(code) == 6 and code.isdigit()
    with TestSession() as session:
        challenge = session.get(OtpChallenge, "applicant@example.com")
        assert challenge is not None and challenge.otp_digest != code

    submitted = submit_signup(client, "applicant@example.com", code)
    assert submitted.status_code == 201
    application_id = submitted.json()["application_id"]
    with TestSession() as session:
        application = session.get(RegistrationApplication, application_id)
        user = session.scalar(select(User).where(User.email == "applicant@example.com"))
        assert application is not None and application.approval_status == "PENDING"
        assert application.email_verified is True
        assert user is not None and user.email_verified is True and not user.is_active
        assert user.account_status == "PENDING"
        assert user.password_hash != "long-enough-secret"
    assert client.post("/api/v1/auth/login", json={"email": "applicant@example.com", "password": "Long-enough-secret1A!"}).status_code == 401

    admin_id, admin_email, admin_password = create_admin()
    headers = admin_headers(client, admin_email, admin_password)
    listing = client.get("/api/v1/admin/applications", headers=headers)
    assert listing.status_code == 200
    assert any(item["id"] == application_id for item in listing.json())
    detail = client.get(f"/api/v1/admin/applications/{application_id}", headers=headers)
    assert detail.status_code == 200 and detail.json()["username"] == "applicant"
    users = client.get("/api/v1/admin/users", headers=headers)
    applicant = next(item for item in users.json() if item["email"] == "applicant@example.com")
    assert applicant["full_name"] == "New VaultTrace User" and applicant["email_verified"] is True
    decisions: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr("app.api.v1.admin.send_application_decision", lambda address, approved, **kwargs: decisions.append((address, {"approved": str(approved)})))
    approved = client.post(f"/api/v1/admin/applications/{application_id}/approve", headers=headers, json={"role": "Owner"})
    assert approved.status_code == 200 and approved.json()["notification_sent"] is True
    assert decisions[-1][0] == "applicant@example.com"

    login = client.post("/api/v1/auth/login", json={"email": "applicant@example.com", "password": "Long-enough-secret1A!"})
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "Owner"
    assert client.get("/api/v1/owner", headers={"Authorization": f"Bearer {login.json()['access_token']}"}).status_code == 200
    overview = client.get("/api/v1/admin/dashboard", headers=headers).json()
    assert overview == {
        "total_registered_users": 2,
        "total_active_users": 2,
        "total_pending_applications": 0,
        "total_approved_users": 1,
        "total_rejected_applications": 0,
        "total_owners": 1,
        "total_viewers": 0,
        "total_documents": 0,
        "active_document_shares": 0,
    }
    with TestSession() as session:
        application = session.get(RegistrationApplication, application_id)
        user = session.scalar(select(User).where(User.email == "applicant@example.com"))
        logs = list(session.scalars(select(AuditLog).where(AuditLog.target_user_id == user.id)))
        assert application is not None and application.reviewed_by_id == admin_id
        assert application.approval_status == "APPROVED" and application.assigned_role.name == "Owner"
        assert user is not None and user.is_active and user.account_status == "ACTIVE"
        assert {log.action for log in logs} >= {"APPLICATION_APPROVED", "ROLE_ASSIGNED"}
        assert all(log.actor_id == admin_id for log in logs)


def test_otp_invalid_expiry_reuse_and_resend(client: InProcessClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject bad/expired/reused codes and invalidate a prior code on resend."""
    otp_values = iter((135790, 246801, 987654))
    monkeypatch.setattr("app.services.otp.secrets.randbelow", lambda _limit: next(otp_values))
    code, codes = issue_otp(client, monkeypatch, "codes@example.com")
    assert client.post("/api/v1/auth/otp/resend", json={"email": "codes@example.com"}).status_code == 429
    wrong = client.post("/api/v1/auth/otp/verify", json={"email": "codes@example.com", "otp": "000000"})
    assert wrong.status_code == 400

    with TestSession.begin() as session:
        challenge = session.get(OtpChallenge, "codes@example.com")
        assert challenge is not None
        challenge.last_sent_at = datetime.now(timezone.utc) - timedelta(seconds=120)
    resend = client.post("/api/v1/auth/otp/resend", json={"email": "codes@example.com"})
    assert resend.status_code == 200 and codes[-1] == "246801"
    assert client.post("/api/v1/auth/otp/verify", json={"email": "codes@example.com", "otp": code}).status_code == 400
    assert client.post("/api/v1/auth/otp/verify", json={"email": "codes@example.com", "otp": codes[-1]}).status_code == 200
    assert client.post("/api/v1/auth/otp/verify", json={"email": "codes@example.com", "otp": codes[-1]}).status_code == 400

    expired_code, _ = issue_otp(client, monkeypatch, "expired@example.com")
    with TestSession.begin() as session:
        challenge = session.get(OtpChallenge, "expired@example.com")
        assert challenge is not None
        challenge.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert client.post("/api/v1/auth/otp/verify", json={"email": "expired@example.com", "otp": expired_code}).status_code == 400


def test_otp_attempt_limit_locks_challenge(client: InProcessClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated invalid guesses lock a challenge before the correct OTP is used."""
    code, _ = issue_otp(client, monkeypatch, "locked@example.com")
    for _attempt in range(5):
        assert client.post("/api/v1/auth/otp/verify", json={"email": "locked@example.com", "otp": "000000"}).status_code == 400
    assert client.post("/api/v1/auth/otp/verify", json={"email": "locked@example.com", "otp": code}).status_code == 400


def test_otp_resend_hourly_rate_limit(client: InProcessClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Resend cooldown cannot be bypassed to exceed the hourly send quota."""
    monkeypatch.setattr(settings, "otp_max_sends_per_hour", 2)
    issue_otp(client, monkeypatch, "limited@example.com")
    for _ in range(2):
        with TestSession.begin() as session:
            challenge = session.get(OtpChallenge, "limited@example.com")
            assert challenge is not None
            challenge.last_sent_at = datetime.now(timezone.utc) - timedelta(seconds=120)
        response = client.post("/api/v1/auth/otp/resend", json={"email": "limited@example.com"})
        if challenge.send_count == 1:
            assert response.status_code == 200
        else:
            assert response.status_code == 429


def test_signup_requires_verified_email_and_validates_password_confirmation(client: InProcessClient) -> None:
    """Signup cannot bypass OTP or mismatch the submitted password."""
    body = {
        "full_name": "Unverified User",
        "username": "unverified",
        "email": "unverified@example.com",
        "password": "Long-enough-secret1A!",
        "confirm_password": "A-different-password1!",
    }
    assert client.post("/api/v1/auth/register", json=body).status_code == 422
    body["confirm_password"] = body["password"]
    assert client.post("/api/v1/auth/register", json=body).status_code == 400


def test_admin_apis_require_administrator_and_rejection_is_audited(client: InProcessClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Viewer cannot access admin routes; rejected applicants are notified/audited."""
    assert client.get("/api/v1/admin/dashboard").status_code == 401
    viewer_email, viewer_password = create_active_user()
    viewer_headers = admin_headers(client, viewer_email, viewer_password)
    assert client.get("/api/v1/admin/dashboard", headers=viewer_headers).status_code == 403
    otp, _ = issue_otp(client, monkeypatch, "reject@example.com")
    registration = submit_signup(client, "reject@example.com", otp)
    application_id = registration.json()["application_id"]
    admin_id, email, password = create_admin()
    headers = admin_headers(client, email, password)
    monkeypatch.setattr("app.api.v1.admin.send_application_decision", lambda *_args, **_kwargs: None)
    rejected = client.post(
        f"/api/v1/admin/applications/{application_id}/reject",
        headers=headers,
        json={"reason": "Unable to validate the submitted information"},
    )
    assert rejected.status_code == 200 and rejected.json()["notification_sent"] is True
    assert client.post("/api/v1/auth/login", json={"email": "reject@example.com", "password": "Long-enough-secret1A!"}).status_code == 401
    dashboard = client.get("/api/v1/admin/dashboard", headers=headers)
    assert dashboard.status_code == 200 and dashboard.json()["total_rejected_applications"] == 1
    with TestSession() as session:
        application = session.get(RegistrationApplication, application_id)
        user = session.scalar(select(User).where(User.email == "reject@example.com"))
        audit = session.scalar(select(AuditLog).where(AuditLog.target_user_id == user.id, AuditLog.action == "APPLICATION_REJECTED"))
        assert application is not None and application.reviewed_by_id == admin_id
        assert application.rejection_reason == "Unable to validate the submitted information"
        assert user is not None and user.account_status == "REJECTED" and not user.is_active
        assert audit is not None and audit.actor_id == admin_id


def test_role_and_account_management_is_audited_and_protects_admin(client: InProcessClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Role/status updates record audit events and cannot demote admin accounts."""
    otp, _ = issue_otp(client, monkeypatch, "managed@example.com")
    application_id = submit_signup(client, "managed@example.com", otp).json()["application_id"]
    admin_id, email, password = create_admin()
    headers = admin_headers(client, email, password)
    monkeypatch.setattr("app.api.v1.admin.send_application_decision", lambda *_args, **_kwargs: None)
    assert client.post(f"/api/v1/admin/applications/{application_id}/approve", headers=headers, json={"role": "Viewer"}).status_code == 200
    with TestSession() as session:
        managed_user = session.scalar(select(User).where(User.email == "managed@example.com"))
        admin_user = session.get(User, admin_id)
        assert managed_user is not None and admin_user is not None
        managed_id, admin_user_id = managed_user.id, admin_user.id

    role_result = client.patch(f"/api/v1/admin/users/{managed_id}/role", headers=headers, json={"role": "Owner"})
    assert role_result.status_code == 200 and role_result.json()["role"] == "Owner"
    assert client.patch(f"/api/v1/admin/users/{admin_user_id}/role", headers=headers, json={"role": "Viewer"}).status_code == 403
    assert client.patch(f"/api/v1/admin/users/{admin_user_id}/status", headers=headers, json={"status": "SUSPENDED"}).status_code == 403
    assert client.patch(f"/api/v1/admin/users/{managed_id}/status", headers=headers, json={"status": "SUSPENDED"}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": "managed@example.com", "password": "Long-enough-secret1A!"}).status_code == 401
    assert client.patch(f"/api/v1/admin/users/{managed_id}/status", headers=headers, json={"status": "ACTIVE"}).status_code == 200
    assert client.patch(f"/api/v1/admin/users/{managed_id}/status", headers=headers, json={"status": "INACTIVE"}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": "managed@example.com", "password": "Long-enough-secret1A!"}).status_code == 401
    with TestSession() as session:
        actions = set(session.scalars(select(AuditLog.action).where(AuditLog.actor_id == admin_id, AuditLog.target_user_id == managed_id)).all())
        assert {"USER_ROLE_CHANGED", "ACCOUNT_SUSPENDED", "ACCOUNT_ACTIVATED", "ACCOUNT_DEACTIVATED"} <= actions
    assert client.get("/api/v1/admin/users").status_code == 401
