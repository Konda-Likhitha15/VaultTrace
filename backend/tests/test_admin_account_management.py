"""Service-level tests for safe administrator account and role updates."""

import asyncio
import json

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import Request

from app.api.dependencies import get_current_user, require_roles
from app.api.v1 import admin as admin_api
from app.db.base import Base
from app.main import database_error_handler
from app.models import AuditLog, Organization, RegistrationApplication, Role, User
from app.schemas.admin import AccountStatusUpdateRequest, OrganizationAssignmentRequest, OrganizationCreateRequest
from app.services.admin import (
    AdminActionConflict,
    ProtectedAdministrator,
    change_user_role,
    change_user_status,
)
from backend.tests.database import TestSession, test_engine


@pytest.fixture()
def account_db():
    """Create a fresh isolated SQLite database for each service test."""
    Base.metadata.create_all(test_engine)
    with TestSession.begin() as session:
        admin_role = Role(name="Administrator")
        owner_role = Role(name="Owner")
        viewer_role = Role(name="Viewer")
        session.add_all([admin_role, owner_role, viewer_role])
        session.flush()
        admin = User(
            full_name="Test Admin", username="testadmin", email="admin@example.com",
            password_hash="test-hash", role=admin_role, is_active=True,
            email_verified=True, account_status="ACTIVE", token_version=0,
        )
        target = User(
            full_name="Test User", username="testuser", email="user@example.com",
            password_hash="test-hash", role=viewer_role, is_active=False,
            email_verified=True, account_status="INACTIVE", token_version=0,
        )
        session.add_all([admin, target])
        session.flush()
        application = RegistrationApplication(
            user_id=target.id, email_verified=True, approval_status="APPROVED",
            assigned_role_id=viewer_role.id,
        )
        session.add(application)
        session.flush()
        ids = (admin.id, target.id, application.id)

    db = TestSession()
    try:
        yield db, ids
    finally:
        db.close()
        Base.metadata.drop_all(test_engine)


def test_activate_deactivate_and_reactivate_persist_audited_status_and_revoke_tokens(account_db) -> None:
    db, (admin_id, user_id, _) = account_db
    user = change_user_status(db, user_id, admin_id, "ACTIVE")
    assert user.account_status == "ACTIVE" and user.is_active and user.token_version == 1

    user = change_user_status(db, user_id, admin_id, "INACTIVE")
    assert user.account_status == "INACTIVE" and not user.is_active and user.token_version == 2

    user = change_user_status(db, user_id, admin_id, "ACTIVE")
    assert user.account_status == "ACTIVE" and user.is_active and user.token_version == 3
    assert db.query(AuditLog.action).filter(AuditLog.target_user_id == user_id).all() == [
        ("ACCOUNT_ACTIVATED",), ("ACCOUNT_DEACTIVATED",), ("ACCOUNT_ACTIVATED",)
    ]
    audit = db.query(AuditLog).filter_by(target_user_id=user_id).first()
    assert audit is not None and audit.actor_id == admin_id and audit.details["result"] == "success"


def test_pending_activation_requires_an_approved_application(account_db) -> None:
    db, (admin_id, user_id, application_id) = account_db
    user = db.get(User, user_id)
    application = db.get(RegistrationApplication, application_id)
    assert user is not None and application is not None
    user.account_status = "PENDING"
    application.approval_status = "PENDING"
    db.commit()

    with pytest.raises(AdminActionConflict, match="verified and approved"):
        change_user_status(db, user_id, admin_id, "ACTIVE")
    assert db.get(User, user_id).account_status == "PENDING"


def test_rejected_account_cannot_be_reactivated(account_db) -> None:
    db, (admin_id, user_id, _) = account_db
    user = db.get(User, user_id)
    assert user is not None
    user.account_status = "REJECTED"
    user.is_active = False
    db.commit()
    with pytest.raises(AdminActionConflict, match="Rejected accounts"):
        change_user_status(db, user_id, admin_id, "ACTIVE")


def test_role_changes_update_relationship_application_audit_and_token_version(account_db) -> None:
    db, (admin_id, user_id, application_id) = account_db
    user = change_user_role(db, user_id, admin_id, "Owner")
    assert user.role.name == "Owner" and user.token_version == 1
    assert db.get(RegistrationApplication, application_id).assigned_role_id == user.role_id
    event = db.query(AuditLog).filter_by(target_user_id=user_id, action="USER_ROLE_CHANGED").one()
    assert event.actor_id == admin_id
    assert event.details == {"previous_value": "Viewer", "new_value": "Owner", "result": "success"}


def test_admin_target_and_self_management_are_protected(account_db) -> None:
    db, (admin_id, user_id, _) = account_db
    with pytest.raises(ProtectedAdministrator):
        change_user_status(db, admin_id, admin_id, "INACTIVE")
    with pytest.raises(ProtectedAdministrator):
        change_user_role(db, admin_id, admin_id, "Viewer")
    with pytest.raises(ProtectedAdministrator):
        change_user_status(db, user_id, user_id, "ACTIVE")


def test_stale_access_token_is_rejected_after_role_update(account_db) -> None:
    db, (admin_id, user_id, _) = account_db
    old_claims = {"sub": str(user_id), "ver": 0}
    change_user_role(db, user_id, admin_id, "Owner")
    with pytest.raises(HTTPException) as error:
        get_current_user(claims=old_claims, db=db)
    assert error.value.status_code == 401


def test_non_admin_role_is_rejected_by_admin_authorization_dependency(account_db) -> None:
    db, (_, user_id, _) = account_db
    user = db.get(User, user_id)
    assert user is not None
    guard = require_roles("Administrator")
    with pytest.raises(HTTPException) as error:
        guard(user=user)
    assert error.value.status_code == 403


def test_invalid_status_is_rejected(account_db) -> None:
    db, (admin_id, user_id, _) = account_db
    with pytest.raises(AdminActionConflict, match="Unsupported account status"):
        change_user_status(db, user_id, admin_id, "DELETED")


def test_status_update_endpoint_maps_database_failure_to_safe_503(account_db, monkeypatch: pytest.MonkeyPatch) -> None:
    db, (admin_id, user_id, _) = account_db
    actor = db.get(User, admin_id)
    assert actor is not None

    def fail(*_args, **_kwargs):
        raise SQLAlchemyError("internal database detail")

    monkeypatch.setattr(admin_api, "change_user_status", fail)
    with pytest.raises(HTTPException) as error:
        admin_api.patch_user_status(
            user_id=user_id,
            payload=AccountStatusUpdateRequest(status="ACTIVE"),
            actor=actor,
            db=db,
        )
    assert error.value.status_code == 503
    assert "internal database detail" not in error.value.detail


def test_admin_can_create_organization_and_assign_existing_user(account_db) -> None:
    db, (admin_id, user_id, _) = account_db
    actor = db.get(User, admin_id)
    assert actor is not None
    organization = admin_api.post_organization(OrganizationCreateRequest(name="Acme Research"), actor, db)
    updated = admin_api.patch_user_organization(user_id, OrganizationAssignmentRequest(organization_id=organization.id), actor, db)
    assert db.get(Organization, organization.id) is not None
    assert updated.organization_id == organization.id
    events = db.query(AuditLog).filter(AuditLog.target_user_id == user_id).all()
    assert any(event.action == "USER_ORGANIZATION_CHANGED" and event.actor_id == admin_id for event in events)


def test_database_dependency_failure_has_safe_actionable_http_response() -> None:
    request = Request({"type": "http", "method": "GET", "path": "/api/v1/admin/users", "headers": []})
    response = asyncio.run(database_error_handler(request, SQLAlchemyError("sensitive connection data")))
    assert response.status_code == 503
    assert json.loads(response.body) == {
        "detail": "Database operation failed. Check PostgreSQL connectivity and retry."
    }
