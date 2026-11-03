"""Document security and persistence tests with isolated PostgreSQL-free fixtures."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.security import hash_password
from app.db.base import Base
from app.models import Document, DocumentActivity, DocumentPermission, DocumentVersion, Organization, Role, User
from app.services.document_collaboration import (
    admin_document_activity,
    admin_document_metadata,
    admin_document_permissions,
    admin_revoke_permission,
    document_activity,
    eligible_share_users,
    grant_permission,
    list_permissions,
    list_versions,
    revoke_permission,
    shared_with_me,
    update_permission,
    upload_document_version,
)
from app.services.documents import (
    DocumentConflict,
    DocumentNotFound,
    DocumentPermissionDenied,
    DocumentValidationError,
    deleted_documents,
    create_storage_key,
    delete_document,
    download_document,
    get_owned_document,
    get_accessible_document,
    list_accessible_documents,
    list_documents,
    restore_document,
    soft_delete_document,
    upload_document,
    validate_upload,
)
from app.services.storage import LocalStorageProvider, StorageConfigurationError, StorageOperationError, SupabaseStorage
from backend.tests.database import TestSession, test_engine


PDF = b"%PDF-1.7\nsynthetic test document\n%%EOF"


class FakeStorage:
    """In-memory storage provider for isolated service tests."""

    provider_name = "local"

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.uploads: list[str] = []
        self.downloads: list[str] = []
        self.deletes: list[str] = []
        self.fail_upload = False

    def upload_file(self, storage_key: str, content: bytes, mime_type: str, bucket: str | None = None) -> None:
        if self.fail_upload:
            raise StorageOperationError("mock storage failure")
        self.objects[storage_key] = content
        self.uploads.append(storage_key)

    def download_file(self, storage_key: str, bucket: str | None = None) -> bytes:
        self.downloads.append(storage_key)
        return self.objects[storage_key]

    def delete_file(self, storage_key: str, bucket: str | None = None) -> None:
        self.deletes.append(storage_key)
        self.objects.pop(storage_key, None)

    def file_exists(self, storage_key: str, bucket: str | None = None) -> bool:
        return storage_key in self.objects

    def generate_signed_url(self, storage_key: str, expires_in: int = 60, bucket: str | None = None) -> str:
        return f"https://storage.example/{storage_key}?expires={expires_in}"

    def close(self) -> None:
        return None


@pytest.fixture()
def identities():
    """Create a fresh SQLite schema and Owner/Viewer test users."""
    Base.metadata.create_all(test_engine)
    with TestSession.begin() as session:
        organization = Organization(name="Test organization")
        owner_role = Role(name="Owner")
        viewer_role = Role(name="Viewer")
        session.add_all((organization, owner_role, viewer_role))
        session.flush()
        owner = User(
            full_name="Test Owner", username="test-owner", email="owner@example.com",
            password_hash=hash_password("test-password"), role=owner_role, is_active=True,
            email_verified=True, account_status="ACTIVE", organization=organization,
        )
        other = User(
            full_name="Other Owner", username="other-owner", email="other@example.com",
            password_hash=hash_password("test-password"), role=owner_role, is_active=True,
            email_verified=True, account_status="ACTIVE", organization=organization,
        )
        viewer = User(
            full_name="Test Viewer", username="test-viewer", email="viewer@example.com",
            password_hash=hash_password("test-password"), role=viewer_role, is_active=True,
            email_verified=True, account_status="ACTIVE", organization=organization,
        )
        session.add_all((owner, other, viewer))
        session.flush()
        user_ids = owner.id, other.id, viewer.id
    try:
        with TestSession() as session:
            yield tuple(session.get(User, user_id) for user_id in user_ids)
    finally:
        Base.metadata.drop_all(test_engine)


def create_pdf(db, storage, owner, name="Quarterly report", category="finance"):
    """Create a valid metadata/file pair using the service boundary."""
    return upload_document(
        db, storage, owner, "report.pdf", "application/pdf", PDF,
        name, category, None,
    )


def test_upload_validates_content_metadata_and_unique_storage_keys(identities) -> None:
    owner, _other, _viewer = identities
    storage = FakeStorage()
    with TestSession() as session:
        first = create_pdf(session, storage, owner)
        second = create_pdf(session, storage, owner, "Annual report", "legal")
        assert first.id != second.id
        assert first.storage_provider == "local"
        assert first.storage_bucket == "local-private-storage"
        assert first.storage_key.startswith(f"users/{owner.id}/")
        assert first.storage_key.endswith(".pdf")
        assert first.checksum and first.file_size == len(PDF)
        assert first.storage_key != second.storage_key
        assert len(storage.uploads) == 2
        assert "storage_key" not in first.__dict__ or first.storage_key
        assert session.scalar(select(Document).where(Document.id == first.id)) is not None


def test_local_provider_is_used_after_shared_document_content_validation(identities, tmp_path) -> None:
    owner, _other, _viewer = identities
    storage = LocalStorageProvider(tmp_path / "private_storage")
    with TestSession() as session:
        document = create_pdf(session, storage, owner)
        disk_path = tmp_path / "private_storage" / document.storage_key
        assert document.storage_provider == "local"
        assert storage.file_exists(document.storage_key)
        assert storage.download_file(document.storage_key) == PDF
        assert disk_path.is_file()

        existing_files = list((tmp_path / "private_storage").glob("**/*"))
        with pytest.raises(DocumentValidationError):
            upload_document(
                session, storage, owner, "fake.pdf", "application/pdf", b"not a PDF",
                "Invalid document", "finance", None,
            )
        assert list((tmp_path / "private_storage").glob("**/*")) == existing_files


@pytest.mark.parametrize(
    ("filename", "content", "mime"),
    [
        ("script.exe", b"MZ dangerous", "application/octet-stream"),
        ("bad.pdf", b"not a PDF", "application/pdf"),
        ("bad.pdf", PDF, "text/plain"),
        ("empty.pdf", b"", "application/pdf"),
    ],
)
def test_upload_rejects_invalid_files_before_storage(identities, filename, content, mime) -> None:
    owner, _other, _viewer = identities
    storage = FakeStorage()
    with TestSession() as session, pytest.raises(DocumentValidationError):
        upload_document(session, storage, owner, filename, mime, content, "Test", "general", None)
    assert storage.uploads == []


def test_upload_rejects_oversized_files(identities, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    owner, _other, _viewer = identities
    monkeypatch.setattr(settings, "document_max_upload_bytes", 5)
    with TestSession() as session, pytest.raises(DocumentValidationError, match="upload limit"):
        validate_upload("file.pdf", "application/pdf", PDF)


def test_storage_failure_leaves_no_document_row(identities) -> None:
    owner, _other, _viewer = identities
    storage = FakeStorage()
    storage.fail_upload = True
    with TestSession() as session:
        with pytest.raises(StorageOperationError):
            create_pdf(session, storage, owner)
        assert session.scalar(select(Document.id)) is None


def test_database_failure_cleans_up_uploaded_object(identities, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.documents import DocumentPersistenceError

    owner, _other, _viewer = identities
    storage = FakeStorage()
    with TestSession() as session:
        def fail_commit() -> None:
            raise SQLAlchemyError("simulated database write failure")

        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(DocumentPersistenceError):
            create_pdf(session, storage, owner)
    assert len(storage.uploads) == 1
    assert storage.deletes == storage.uploads
    assert storage.objects == {}


def test_listing_filters_and_owner_boundary(identities) -> None:
    owner, other, viewer = identities
    storage = FakeStorage()
    with TestSession() as session:
        create_pdf(session, storage, owner)
        create_pdf(session, storage, owner, "Policy", "legal")
        create_pdf(session, storage, other, "Other account", "finance")
        matches = list_documents(session, owner.id, search="Quarterly", category="finance", date_from=None, date_to=None, limit=10, offset=0, sort_by="created_at", sort_order="desc")
        assert [item.document_name for item in matches] == ["Quarterly report"]
        assert list_documents(session, owner.id, search="absent", category=None, date_from=None, date_to=None, limit=10, offset=0, sort_by="created_at", sort_order="desc") == []
        assert list_documents(session, viewer.id, search=None, category=None, date_from=None, date_to=None, limit=10, offset=0, sort_by="created_at", sort_order="desc") == []
        other_document = session.scalar(select(Document).where(Document.owner_id == other.id))
        assert other_document is not None
        with pytest.raises(DocumentNotFound):
            get_owned_document(session, owner.id, other_document.id)


def test_download_integrity_and_delete_require_owned_manageable_user(identities) -> None:
    owner, _other, viewer = identities
    storage = FakeStorage()
    with TestSession() as session:
        document = create_pdf(session, storage, owner)
        selected_providers: list[str] = []

        def select_provider(provider_name: str) -> FakeStorage:
            selected_providers.append(provider_name)
            return storage

        found, content = download_document(session, select_provider, owner.id, document.id)
        assert found.id == document.id and content == PDF
        assert selected_providers == ["local"]
        with pytest.raises(DocumentNotFound):
            download_document(session, lambda _provider: storage, viewer.id, document.id)
        with pytest.raises(DocumentNotFound):
            delete_document(session, lambda _provider: storage, viewer, document.id)
        assert storage.downloads == [document.storage_key]
        delete_document(session, lambda _provider: storage, owner, document.id)
        assert document.storage_key not in storage.deletes
        assert session.get(Document, document.id) is not None
        assert len(deleted_documents(session, owner.id)) == 1
        assert restore_document(session, owner, document.id).deleted_at is None
        assert storage.file_exists(document.storage_key)


def test_viewer_cannot_upload_or_delete(identities) -> None:
    _owner, _other, viewer = identities
    with TestSession() as session, pytest.raises(DocumentPermissionDenied):
        create_pdf(session, FakeStorage(), viewer)


def test_owner_shares_with_registered_user_and_revocation_denies_download(identities) -> None:
    owner, _other, viewer = identities
    storage = FakeStorage()
    with TestSession() as session:
        document = create_pdf(session, storage, owner)
        grant = grant_permission(session, owner.id, document.id, recipient_user_id=viewer.id, recipient_email=None, permission_level="VIEWER", expires_at=None)
        assert document.visibility == "SHARED"
        authorized, access = get_accessible_document(session, viewer.id, document.id)
        assert authorized.id == document.id and access == "VIEWER"
        assert [version.version_number for version in list_versions(session, viewer.id, document.id)] == [1]
        assert len(shared_with_me(session, viewer.id)) == 1
        with pytest.raises(DocumentPermissionDenied):
            update_permission(session, viewer.id, document.id, grant.id, permission_level="EDITOR", expires_at=None, expiration_was_set=False)
        found, content = download_document(session, lambda _provider: storage, viewer.id, document.id)
        assert found.id == document.id and content == PDF

        revoke_permission(session, owner.id, document.id, grant.id)
        with pytest.raises(DocumentNotFound):
            download_document(session, lambda _provider: storage, viewer.id, document.id)
        actions = set(session.scalars(select(DocumentActivity.action).where(DocumentActivity.document_id == document.id)).all())
        assert {"DOCUMENT_UPLOADED", "PERMISSION_GRANTED", "DOCUMENT_DOWNLOADED", "PERMISSION_REVOKED", "DOCUMENT_ACCESS_DENIED"} <= actions


def test_owner_can_update_and_regrant_a_permission_with_expiration(identities) -> None:
    owner, _other, viewer = identities
    with TestSession() as session:
        document = create_pdf(session, FakeStorage(), owner)
        grant = grant_permission(session, owner.id, document.id, recipient_user_id=viewer.id, recipient_email=None, permission_level="VIEWER", expires_at=None)
        changed = update_permission(
            session, owner.id, document.id, grant.id,
            permission_level="EDITOR", expires_at=datetime.now(timezone.utc) + timedelta(hours=1), expiration_was_set=True,
        )
        assert changed.permission_level == "EDITOR" and changed.expires_at is not None
        with pytest.raises(DocumentConflict, match="already has active access"):
            grant_permission(session, owner.id, document.id, recipient_user_id=viewer.id, recipient_email=None, permission_level="VIEWER", expires_at=None)
        revoke_permission(session, owner.id, document.id, changed.id)
        regranted = grant_permission(session, owner.id, document.id, recipient_user_id=viewer.id, recipient_email=None, permission_level="READ", expires_at=None)
        assert regranted.id == grant.id and regranted.permission_level == "VIEWER" and regranted.revoked_at is None
        history = list_permissions(session, owner.id, document.id)
        assert len(history) == 1
        assert {"PERMISSION_UPDATED", "PERMISSION_REVOKED"} <= set(session.scalars(select(DocumentActivity.action).where(DocumentActivity.document_id == document.id)).all())


def test_document_sharing_is_limited_to_same_organization_and_registered_users(identities) -> None:
    owner, _other, viewer = identities
    storage = FakeStorage()
    with TestSession() as session:
        other_org = Organization(name="Different organization")
        session.add(other_org)
        session.flush()
        role = session.scalar(select(Role).where(Role.name == "Viewer"))
        cross_org_user = User(full_name="Outside User", username="outside-user", email="outside@example.com", password_hash=hash_password("test-password"), role=role, organization=other_org, email_verified=True, is_active=True, account_status="ACTIVE")
        session.add(cross_org_user)
        session.flush()
        document = create_pdf(session, storage, owner)
        assert [user.id for user in eligible_share_users(session, owner.id, document.id, "viewer")] == [viewer.id]
        with pytest.raises(DocumentNotFound):
            grant_permission(session, owner.id, document.id, recipient_user_id=cross_org_user.id, recipient_email=None, permission_level="READ", expires_at=None)
        with pytest.raises(DocumentNotFound):
            grant_permission(session, owner.id, document.id, recipient_user_id=None, recipient_email="nobody@example.com", permission_level="READ", expires_at=None)


def test_delegated_legacy_owner_cannot_manage_permissions_or_delete(identities) -> None:
    owner, _other, viewer = identities
    with TestSession() as session:
        document = create_pdf(session, FakeStorage(), owner)
        permission = DocumentPermission(document_id=document.id, granted_by_user_id=owner.id, granted_to_user_id=viewer.id, permission_level="OWNER")
        session.add(permission)
        document.visibility = "SHARED"
        session.commit()
        with pytest.raises(DocumentNotFound):
            list_permissions(session, viewer.id, document.id)
        with pytest.raises(DocumentNotFound):
            soft_delete_document(session, viewer, document.id)


def test_expired_share_is_hidden_and_search_never_exposes_private_documents(identities) -> None:
    owner, other, viewer = identities
    with TestSession() as session:
        visible = create_pdf(session, FakeStorage(), owner, "Shared report", "finance")
        private = create_pdf(session, FakeStorage(), other, "Private report", "legal")
        expired = grant_permission(session, owner.id, visible.id, recipient_user_id=viewer.id, recipient_email=None, permission_level="VIEWER", expires_at=None)
        expired.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.commit()
        assert list_accessible_documents(session, viewer.id, search=str(visible.id)) == []
        assert list_accessible_documents(session, viewer.id, search="Private report") == []
        with pytest.raises(DocumentNotFound):
            get_accessible_document(session, viewer.id, visible.id)
        assert session.get(Document, private.id) is not None


def test_editor_can_upload_version_and_old_file_remains_available(identities) -> None:
    owner, _other, viewer = identities
    storage = FakeStorage()
    pdf_v2 = b"%PDF-1.7\nrevision 2\n%%EOF"
    with TestSession() as session:
        document = create_pdf(session, storage, owner)
        grant_permission(session, owner.id, document.id, recipient_user_id=viewer.id, recipient_email=None, permission_level="EDITOR", expires_at=None)
        version = upload_document_version(session, storage, viewer.id, document.id, "report-v2.pdf", "application/pdf", pdf_v2)
        assert version.version_number == 2
        assert document.current_version == 2 and document.storage_key == version.storage_key
        versions = list_versions(session, viewer.id, document.id)
        assert [item.version_number for item in versions] == [2, 1]
        assert storage.download_file(versions[1].storage_key) == PDF
        assert storage.download_file(versions[0].storage_key) == pdf_v2
        assert "DOCUMENT_VERSION_CREATED" in session.scalars(select(DocumentActivity.action).where(DocumentActivity.document_id == document.id)).all()


def test_soft_delete_revoke_and_restore_preserve_file_but_not_old_permissions(identities) -> None:
    owner, _other, viewer = identities
    storage = FakeStorage()
    with TestSession() as session:
        document = create_pdf(session, storage, owner)
        grant = grant_permission(session, owner.id, document.id, recipient_user_id=viewer.id, recipient_email=None, permission_level="VIEWER", expires_at=None)
        soft_delete_document(session, owner, document.id)
        assert storage.file_exists(document.storage_key)
        assert len(deleted_documents(session, owner.id)) == 1
        restored = restore_document(session, owner, document.id)
        assert restored.deleted_at is None and storage.file_exists(document.storage_key)
        with pytest.raises(DocumentNotFound):
            get_accessible_document(session, viewer.id, document.id)
        assert session.get(DocumentPermission, grant.id).revoked_at is not None


def test_storage_configuration_fails_closed_for_missing_or_public_bucket() -> None:
    with pytest.raises(StorageConfigurationError, match="not configured"):
        SupabaseStorage(None, None, "vaulttrace-documents")

    def public_bucket(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/bucket/vaulttrace-documents"):
            return httpx.Response(200, json={"id": "vaulttrace-documents", "public": True})
        return httpx.Response(200)

    adapter = SupabaseStorage(
        "https://project.supabase.co", "test-service-role-key", "vaulttrace-documents",
        httpx.MockTransport(public_bucket),
    )
    with pytest.raises(StorageConfigurationError, match="private"):
        adapter.file_exists("users/1/document.pdf")
    adapter.close()


def test_storage_key_is_uuid_based_and_rejects_untrusted_path_parts() -> None:
    from uuid import uuid4

    key = create_storage_key(15, uuid4(), ".pdf")
    assert key.startswith("users/15/") and ".." not in key
    with pytest.raises(DocumentValidationError):
        create_storage_key(15, uuid4(), "../../file.pdf")


def test_administrator_document_review_is_metadata_only_and_revoke_is_audited(identities) -> None:
    owner, _other, viewer = identities
    storage = FakeStorage()
    with TestSession() as session:
        administrator_role = Role(name="Administrator")
        session.add(administrator_role)
        session.flush()
        administrator_actor = User(
            full_name="Test Administrator", username="test-administrator", email="admin@example.com",
            password_hash=hash_password("test-password"), role=administrator_role, is_active=True,
            email_verified=True, account_status="ACTIVE",
        )
        session.add(administrator_actor)
        session.flush()
        document = create_pdf(session, storage, owner)
        permission = grant_permission(session, owner.id, document.id, recipient_user_id=viewer.id, recipient_email=None, permission_level="VIEWER", expires_at=None)
        assert [item.id for item in admin_document_metadata(session, search="Quarterly", limit=10, offset=0)] == [document.id]
        assert [item.id for item in admin_document_permissions(session, document_id=document.id, limit=10, offset=0)] == [permission.id]
        admin_revoke_permission(session, administrator_actor.id, permission.id)
        with pytest.raises(DocumentNotFound):
            get_accessible_document(session, viewer.id, document.id)
        events = admin_document_activity(session, document_id=document.id, limit=20, offset=0)
        revoke_event = next(item for item in events if item.action == "PERMISSION_REVOKED")
        assert revoke_event.actor_user_id == administrator_actor.id
        assert revoke_event.details["administrative_action"] is True


def test_viewer_cannot_edit_metadata_or_upload_versions(identities) -> None:
    owner, _other, viewer = identities
    storage = FakeStorage()
    with TestSession() as session:
        document = create_pdf(session, storage, owner)
        grant_permission(session, owner.id, document.id, recipient_user_id=viewer.id, recipient_email=None, permission_level="VIEWER", expires_at=None)
        from app.services.document_collaboration import update_document_metadata

        with pytest.raises(DocumentPermissionDenied):
            update_document_metadata(session, viewer.id, document.id, {"document_name": "attempted change"})
        with pytest.raises(DocumentPermissionDenied):
            upload_document_version(session, storage, viewer.id, document.id, "report.pdf", "application/pdf", PDF)

