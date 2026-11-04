"""Audit service filtering, safe projections, and administrator-only API tests."""

import csv
from io import StringIO
import uuid
from uuid import uuid4

import pytest
from sqlalchemy import select

from fastapi import HTTPException
from starlette.requests import Request
from app.api.dependencies import unauthorized
from app.api.v1 import admin as admin_api
from app.api.v1 import router as auth_api
from app.db.base import Base
from app.models import AuditLog, Organization, Role, User
from app.schemas.audit import AuditExportQuery, AuditQuery
from app.schemas.auth import Credentials
from app.services.audit import list_audit_events, record_audit_event, summarize_audit_events
from backend.tests.database import TestSession, test_engine


@pytest.fixture()
def audit_identities():
    Base.metadata.create_all(test_engine)
    with TestSession.begin() as db:
        organization = Organization(name=f"audit-service-{uuid.uuid4()}")
        owner_role = Role(name="Owner")
        db.add_all((organization, owner_role))
        db.flush()
        owner = User(full_name="Audit Owner", username=f"audit-owner-{uuid.uuid4().hex[:8]}", email=f"{uuid.uuid4().hex}@example.test", password_hash="unused", role=owner_role, organization=organization, is_active=True, email_verified=True, account_status="ACTIVE")
        other = User(full_name="Audit Other", username=f"audit-other-{uuid.uuid4().hex[:8]}", email=f"{uuid.uuid4().hex}@example.test", password_hash="unused", role=owner_role, organization=organization, is_active=True, email_verified=True, account_status="ACTIVE")
        db.add_all((owner, other))
        db.flush()
        ids = owner.id, other.id
    try:
        yield ids
    finally:
        Base.metadata.drop_all(test_engine)


def test_audit_service_filters_paginates_and_removes_sensitive_metadata(audit_identities) -> None:
    owner_id, other_id = audit_identities
    with TestSession() as db:
        owner = db.get(User, owner_id)
        other = db.get(User, other_id)
        assert owner is not None and other is not None
        record_audit_event(db, "DOCUMENT_UPLOADED", actor=owner, resource_type="Document", resource_id=uuid4(), details={"file_size": 42, "password": "must-not-persist", "otp": "123456", "safe": "ok"})
        record_audit_event(db, "DOCUMENT_DOWNLOAD_FAILED", actor=other, outcome="FAILURE", resource_type="Document", resource_id="doc-2")
        db.commit()

        rows, count = list_audit_events(db, limit=1, offset=0, user_id=owner_id, action="DOCUMENT_UPLOADED")
        assert count == 1 and len(rows) == 1
        assert rows[0].details == {"file_size": 42, "safe": "ok"}
        assert summarize_audit_events(db) == {
            "total_events": 2,
            "successful_operations": 1,
            "failed_operations": 1,
            "active_users": 2,
        }


def test_failed_login_is_recorded_without_password_or_token(audit_identities) -> None:
    _owner_id, _other_id = audit_identities
    request = Request({"type": "http", "method": "POST", "path": "/api/v1/auth/login", "headers": [(b"user-agent", b"audit-test")], "client": ("127.0.0.1", 50200)})
    with TestSession() as db:
        with pytest.raises(HTTPException) as failure:
            auth_api.login(Credentials(email="missing@example.com", password="not-the-password"), request, db)
        assert failure.value.status_code == 401
        event = db.scalar(select(AuditLog).where(AuditLog.action == "AUTH_LOGIN_FAILED"))
        assert event is not None and event.outcome == "FAILURE" and event.actor_email == "missing@example.com"
        assert "not-the-password" not in str(event.details)


def test_admin_audit_routes_enforce_roles_filters_pagination_and_csv() -> None:
    Base.metadata.create_all(test_engine)
    try:
        with TestSession.begin() as db:
            roles = {role.name: role for role in db.scalars(select(Role)).all()}
            new_roles = [Role(name=name) for name in ("Administrator", "Owner", "Viewer", "Editor") if name not in roles]
            db.add_all(new_roles)
            db.flush()
            roles.update({role.name: role for role in new_roles})
            org = Organization(name=f"audit-test-{uuid4()}")
            outside_org = Organization(name=f"audit-other-{uuid4()}")
            db.add_all((org, outside_org))
            db.flush()
            users = {}
            for role_name in ("Administrator", "Owner", "Editor", "Viewer"):
                role = roles[role_name]
                user = User(
                    full_name=f"Audit {role_name}", username=f"audit-{role_name.lower()}-{uuid4().hex[:6]}",
                    email=f"audit-{uuid4().hex}@example.test", password_hash="not-used",
                    role=role, organization=org, is_active=True, email_verified=True,
                    account_status="ACTIVE", token_version=0,
                )
                db.add(user)
                db.flush()
                users[role_name] = user.id
            record_audit_event(db, "AUDIT_TEST_EVENT", actor=db.get(User, users["Owner"]), resource_type="Document", resource_id="doc-123", details={"safe": "value", "access_token": "never-return"})
            record_audit_event(db, "AUDIT_TEST_EVENT_2", actor=db.get(User, users["Owner"]), resource_type="Document", resource_id="doc-123", details={"safe": "second"})
            record_audit_event(db, "OTHER_ORG_EVENT", actor=db.get(User, users["Owner"]), organization_id=outside_org.id, resource_type="Document", resource_id="outside-doc")
            ids = users
        with TestSession() as db:
            guard = admin_api.router.dependencies[0].dependency
            with pytest.raises(HTTPException) as unauth:
                raise unauthorized()
            assert unauth.value.status_code == 401
            for name in ("Owner", "Editor", "Viewer"):
                with pytest.raises(HTTPException) as denied:
                    guard(user=db.get(User, ids[name]))
                assert denied.value.status_code == 403
            admin = db.get(User, ids["Administrator"])
            assert admin is not None
            page = admin_api.get_audit_logs(query=AuditQuery(resource_id="doc-123"), limit=1, offset=0, sort_order="desc", db=db)
            assert page.total == 2 and len(page.items) == 1
            next_page = admin_api.get_audit_logs(query=AuditQuery(resource_id="doc-123"), limit=1, offset=1, sort_order="desc", db=db)
            assert next_page.total == 2 and len(next_page.items) == 1
            assert next_page.items[0].id != page.items[0].id
            assert page.items[0].details in ({"safe": "value"}, {"safe": "second"})
            org_page = admin_api.get_audit_logs(query=AuditQuery(organization_id=org.id), limit=10, offset=0, sort_order="desc", db=db)
            assert org_page.total == 2 and all(item.organization_id == org.id for item in org_page.items)
            summary = admin_api.get_audit_summary(AuditQuery(outcome="SUCCESS"), db)
            assert summary.total_events >= 1
            detail = admin_api.get_audit_log_detail(page.items[0].id, db)
            assert detail.id == page.items[0].id
            exported = admin_api.export_audit_logs(AuditExportQuery(resource_id="doc-123"), db)
            assert exported.status_code == 200 and "text/csv" in exported.media_type
            parsed = list(csv.DictReader(StringIO(exported.body.decode("utf-8-sig"))))
            assert len(parsed) == 2 and all(row["action"].startswith("AUDIT_TEST_EVENT") for row in parsed)
            assert "never-return" not in exported.body.decode("utf-8")
            assert not any(route.path.startswith("/audit-logs") and {"PATCH", "DELETE"} & route.methods for route in admin_api.router.routes)
    finally:
        Base.metadata.drop_all(test_engine)
