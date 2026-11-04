"""Route-level checks for ownership, shared download, and immediate revocation."""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from starlette.requests import Request

from app.api.v1 import documents as document_api
from app.db.base import Base
from app.models import Document, DocumentVersion, Organization, Role, User
from app.schemas.documents import DocumentPermissionCreate
from backend.tests.database import TestSession, test_engine


class MemoryStorage:
    """Test-only provider containing private file bytes."""

    provider_name = "local"

    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.downloaded: list[str] = []

    def download_file(self, key, bucket=None):
        self.downloaded.append(key)
        return self.objects[key]

    def close(self):
        pass


def test_private_read_and_download_are_denied_until_grant_then_revoked_immediately():
    Base.metadata.create_all(test_engine)
    content = b"%PDF-1.7\napi test\n%%EOF"
    storage_objects: dict[str, bytes] = {}
    with TestSession.begin() as db:
        organization = Organization(name=f"route-test-{uuid.uuid4()}")
        owner_role = Role(name="Owner")
        viewer_role = Role(name="Viewer")
        db.add_all((owner_role, viewer_role))
        db.add(organization)
        db.flush()
        owner = User(full_name="API Owner", username=f"route-owner-{uuid.uuid4().hex[:8]}", email=f"route-owner-{uuid.uuid4().hex}@example.com", password_hash="unused-test-hash", role=owner_role, organization=organization, is_active=True, email_verified=True, account_status="ACTIVE")
        viewer = User(full_name="API Viewer", username=f"route-viewer-{uuid.uuid4().hex[:8]}", email=f"route-viewer-{uuid.uuid4().hex}@example.com", password_hash="unused-test-hash", role=viewer_role, organization=organization, is_active=True, email_verified=True, account_status="ACTIVE")
        db.add_all((owner, viewer))
        db.flush()
        owner_id, viewer_id = owner.id, viewer.id
        document_id, version_id = uuid.uuid4(), uuid.uuid4()
        key = f"users/{owner_id}/{document_id}.pdf"
        document = Document(id=document_id, storage_provider="local", document_name="Route test file", original_filename="route-test.pdf", owner_id=owner_id, category="test", file_extension="pdf", mime_type="application/pdf", file_size=len(content), storage_bucket="local-private-storage", storage_key=key, checksum=None, visibility="PRIVATE", current_version=1)
        db.add(document)
        db.flush()
        db.add(DocumentVersion(id=version_id, document_id=document_id, version_number=1, storage_provider="local", storage_bucket="local-private-storage", storage_key=key, original_filename="route-test.pdf", file_extension="pdf", mime_type="application/pdf", file_size=len(content), checksum=None, created_by_user_id=owner_id))
        storage_objects[key] = content

    scope = {"type": "http", "method": "GET", "path": "/api/v1/documents", "headers": [], "client": ("127.0.0.1", 43123)}
    request = Request(scope)
    try:
        with TestSession() as db:
            owner = db.get(User, owner_id)
            viewer = db.get(User, viewer_id)
            assert owner is not None and viewer is not None
            with pytest.raises(HTTPException) as hidden:
                document_api.get_document(document_id, viewer, db)
            assert hidden.value.status_code == 404
            with pytest.raises(HTTPException) as hidden_download:
                document_api.get_document_download(document_id, request, viewer, db, lambda _provider: MemoryStorage(storage_objects))
            assert hidden_download.value.status_code == 404
            with pytest.raises(HTTPException) as hidden_versions:
                document_api.get_document_versions(document_id, viewer, db)
            assert hidden_versions.value.status_code == 404
            with pytest.raises(HTTPException) as missing_versions:
                document_api.get_document_versions(uuid.uuid4(), owner, db)
            assert missing_versions.value.status_code == 404

            grant = document_api.post_document_permission(
                document_id,
                DocumentPermissionCreate(recipient_user_id=viewer_id, permission_level="READ"),
                request,
                owner,
                db,
            )
            assert grant.permission_level == "READ"
            versions = document_api.get_document_versions(document_id, viewer, db)
            assert len(versions) == 1
            assert versions[0].version_number == 1
            assert versions[0].original_filename == "route-test.pdf"
            assert versions[0].created_by_full_name == "API Owner"
            assert versions[0].file_size == len(content)
            provider = MemoryStorage(storage_objects)
            authorized = document_api.get_document_download(document_id, request, viewer, db, lambda _provider: provider)
            assert authorized.status_code == 200
            assert provider.downloaded == [key]

            revoked = document_api.delete_document_permission(document_id, grant.id, request, owner, db)
            assert revoked.status_code == 204
            for operation in (
                lambda: document_api.get_document(document_id, viewer, db),
                lambda: document_api.get_document_download(document_id, request, viewer, db, lambda _provider: MemoryStorage(storage_objects)),
                lambda: document_api.preview_document(document_id, request, viewer, db, lambda _provider: MemoryStorage(storage_objects)),
                lambda: document_api.get_document_versions(document_id, viewer, db),
                lambda: document_api.download_document_version(document_id, version_id, request, viewer, db, lambda _provider: MemoryStorage(storage_objects)),
            ):
                with pytest.raises(HTTPException) as denied:
                    operation()
                assert denied.value.status_code == 404
    finally:
        Base.metadata.drop_all(test_engine)
