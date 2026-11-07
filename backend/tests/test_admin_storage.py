"""Aggregation tests for administrator storage analytics and customer details."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.db.base import Base
from app.models import Document, DocumentActivity, DocumentPermission, DocumentVersion, Organization, Role, User
from app.schemas.admin import AdminAnalytics, AdminStoragePage
from app.services.admin_storage import admin_analytics, admin_storage_detail, admin_storage_page, recorded_storage_bytes
from backend.tests.database import TestSession, test_engine


def test_admin_storage_aggregates_current_and_retained_versions() -> None:
    Base.metadata.create_all(test_engine)
    now = datetime.now(timezone.utc)
    with TestSession.begin() as db:
        owner_role = Role(name="Owner")
        viewer_role = Role(name="Viewer")
        db.add_all((owner_role, viewer_role))
        organization = Organization(name="Storage Test Org")
        db.add(organization)
        db.flush()
        owner = User(full_name="Storage Owner", username="storage-owner", email="storage-owner@example.com", password_hash="not-used", role=owner_role, organization=organization, is_active=True, email_verified=True, account_status="ACTIVE")
        viewer = User(full_name="Storage Viewer", username="storage-viewer", email="storage-viewer@example.com", password_hash="not-used", role=viewer_role, organization=organization, is_active=True, email_verified=True, account_status="ACTIVE")
        db.add_all((owner, viewer))
        db.flush()
        document_id = uuid4()
        current_key = str(uuid4())
        document = Document(
            id=document_id, storage_provider="local", document_name="Quarterly report", original_filename="report.pdf",
            owner_id=owner.id, category="Reports", file_extension="pdf", mime_type="application/pdf", file_size=200,
            storage_bucket="test", storage_key=current_key, visibility="SHARED", current_version=2,
            created_at=now - timedelta(days=20), updated_at=now - timedelta(days=1),
        )
        deleted = Document(
            id=uuid4(), storage_provider="local", document_name="Old sheet", original_filename="old.csv",
            owner_id=owner.id, category="Archive", file_extension="csv", mime_type="text/csv", file_size=50,
            storage_bucket="test", storage_key=str(uuid4()), visibility="PRIVATE", current_version=1,
            created_at=now - timedelta(days=40), updated_at=now - timedelta(days=40), deleted_at=now - timedelta(days=5),
        )
        db.add_all((document, deleted))
        db.flush()
        db.add_all((
            DocumentVersion(id=uuid4(), document_id=document.id, version_number=1, storage_provider="local", storage_bucket="test", storage_key=str(uuid4()), original_filename="report-v1.pdf", file_extension="pdf", mime_type="application/pdf", file_size=100, created_by_user_id=owner.id, created_at=now - timedelta(days=10)),
            DocumentVersion(id=uuid4(), document_id=document.id, version_number=2, storage_provider="local", storage_bucket="test", storage_key=current_key, original_filename="report.pdf", file_extension="pdf", mime_type="application/pdf", file_size=200, created_by_user_id=owner.id, created_at=now - timedelta(days=1)),
            DocumentPermission(document_id=document.id, granted_by_user_id=owner.id, granted_to_user_id=viewer.id, permission_level="VIEWER", created_at=now - timedelta(days=2)),
            DocumentActivity(document_id=document.id, actor_user_id=owner.id, action="DOCUMENT_VERSION_CREATED", result="SUCCESS", created_at=now - timedelta(days=1)),
        ))

    try:
        with TestSession() as db:
            items, total = admin_storage_page(db, search="storage-owner", organization_id=None, sort_by="storage_bytes", limit=10, offset=0)
            assert total == 1
            assert items[0]["document_count"] == 2
            assert items[0]["storage_bytes"] == 350
            assert items[0]["largest_file_bytes"] == 200
            assert recorded_storage_bytes(db, items[0]["user_id"]) == 350

            detail = admin_storage_detail(db, items[0]["user_id"], document_limit=10, document_offset=0)
            assert detail is not None
            assert detail["user"]["storage_bytes"] == 350
            current = next(row for row in detail["documents"] if row["document_name"] == "Quarterly report")
            assert current["current_file_bytes"] == 200
            assert current["total_stored_bytes"] == 300
            assert current["version_count"] == 2
            assert len(detail["recent_activity"]) == 1

            analytics = admin_analytics(db, "30d")
            assert analytics["total_documents"] == 2
            assert analytics["total_storage_bytes"] == 350
            assert analytics["total_shared_documents"] == 1
            assert analytics["storage_growth_available"] is False
            assert analytics["registration_trends"]
            assert analytics["upload_trends"]
            assert AdminAnalytics(**analytics).total_storage_bytes == 350
            assert AdminStoragePage(items=items, total=total, limit=10, offset=0).items[0].storage_bytes == 350
    finally:
        Base.metadata.drop_all(test_engine)
