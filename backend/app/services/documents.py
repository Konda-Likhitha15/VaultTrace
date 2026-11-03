"""Document validation, owner-scoped metadata operations, and storage orchestration."""

import hashlib
import hmac
import logging
import re
from collections.abc import Callable
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import and_, asc, desc, exists, false, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Document, DocumentActivity, DocumentPermission, DocumentVersion, Role, User
from app.services.document_validation import DocumentValidationError, MIME_BY_EXTENSION, validate_upload
from app.services.storage import StorageService

StorageProviderFactory = Callable[[str], StorageService]
_LOCAL_STORAGE_BUCKET = "local-private-storage"


def _close_storage_provider(storage: StorageService) -> None:
    """Release provider resources after a single read or delete operation."""
    storage.close()


logger = logging.getLogger(__name__)


class DocumentPermissionDenied(Exception):
    """Raised when a role cannot perform the requested document action."""


class DocumentNotFound(Exception):
    """Raised without disclosing metadata for a document outside the caller's scope."""


class DocumentPersistenceError(Exception):
    """Raised when metadata persistence fails after a storage operation."""


class DocumentConflict(Exception):
    """Raised when a document action conflicts with its current state."""


def create_storage_key(owner_id: int, document_id: UUID, extension: str) -> str:
    """Use only a database owner ID, a random document UUID, and validated extension."""
    if owner_id <= 0 or extension not in MIME_BY_EXTENSION:
        raise DocumentValidationError("Unable to create a safe storage key.")
    return f"users/{owner_id}/{document_id}{extension}"


def upload_document(
    db: Session,
    storage: StorageService,
    user: User,
    filename: str | None,
    supplied_mime: str | None,
    content: bytes,
    document_name: str,
    category: str,
    description: str | None,
    visibility: str = "PRIVATE",
    request_ip: str | None = None,
    user_agent: str | None = None,
) -> Document:
    """Upload to private storage, persist metadata, and clean up storage on DB failure."""
    if user.role.name != "Owner":
        raise DocumentPermissionDenied
    safe_name = document_name.strip()
    safe_category = category.strip()
    safe_description = description.strip() if description and description.strip() else None
    if not safe_name or len(safe_name) > 200 or any(ord(char) < 32 for char in safe_name):
        raise DocumentValidationError("Document name must contain 1–200 printable characters.")
    if not safe_category or len(safe_category) > 64:
        raise DocumentValidationError("Category must contain 1–64 characters.")
    if safe_description is not None and len(safe_description) > 4000:
        raise DocumentValidationError("Description cannot exceed 4000 characters.")
    if visibility not in {"PRIVATE", "SHARED", "RESTRICTED"}:
        raise DocumentValidationError("Visibility must be PRIVATE, SHARED, or RESTRICTED.")
    validated = validate_upload(filename, supplied_mime, content)
    document_id = uuid4()
    storage_key = create_storage_key(user.id, document_id, validated.extension)
    provider_name = storage.provider_name
    bucket = settings.supabase_storage_bucket if provider_name == "supabase" else _LOCAL_STORAGE_BUCKET
    try:
        storage.upload_file(storage_key, content, validated.mime_type, bucket)
    except Exception:
        raise
    document = Document(
        id=document_id,
        storage_provider=provider_name,
        document_name=safe_name,
        original_filename=validated.original_filename,
        owner_id=user.id,
        category=safe_category,
        description=safe_description,
        file_extension=validated.extension,
        mime_type=validated.mime_type,
        file_size=validated.size,
        storage_bucket=bucket,
        storage_key=storage_key,
        checksum=validated.checksum,
        visibility=visibility,
    )
    try:
        db.add(document)
        db.flush()
        db.add(DocumentVersion(
            document_id=document_id,
            version_number=1,
            storage_provider=provider_name,
            storage_bucket=bucket,
            storage_key=storage_key,
            original_filename=validated.original_filename,
            file_extension=validated.extension,
            mime_type=validated.mime_type,
            file_size=validated.size,
            checksum=validated.checksum,
            created_by_user_id=user.id,
        ))
        db.add(DocumentActivity(
            document_id=document_id,
            actor_user_id=user.id,
            action="DOCUMENT_UPLOADED",
            result="SUCCESS",
            request_ip=request_ip,
            user_agent=user_agent,
            details={"version_number": 1, "visibility": visibility},
        ))
        db.commit()
        db.refresh(document)
    except SQLAlchemyError as exc:
        db.rollback()
        try:
            storage.delete_file(storage_key, bucket)
        except Exception:
            logger.error("Storage cleanup failed after document metadata persistence failure (document_id=%s)", document_id)
        raise DocumentPersistenceError("Document metadata could not be saved; the upload was rolled back where possible.") from exc
    return document


def list_documents(
    db: Session,
    owner_id: int,
    *,
    search: str | None,
    category: str | None,
    date_from: date | None,
    date_to: date | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_order: str,
) -> list[Document]:
    """Query only the caller's documents, applying supported filters and pagination."""
    query = select(Document).where(Document.owner_id == owner_id, Document.deleted_at.is_(None))
    if search and search.strip():
        escaped = re.sub(r"([%_\\])", r"\\\1", search.strip())
        query = query.where(or_(Document.document_name.ilike(f"%{escaped}%", escape="\\"), Document.original_filename.ilike(f"%{escaped}%", escape="\\")))
    if category and category.strip():
        query = query.where(Document.category == category.strip())
    if date_from:
        start = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
        query = query.where(Document.created_at >= start)
    if date_to:
        end_exclusive = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
        query = query.where(Document.created_at < end_exclusive)
    sort_columns = {
        "created_at": Document.created_at,
        "document_name": Document.document_name,
        "file_size": Document.file_size,
    }
    column = sort_columns[sort_by]
    query = query.order_by((desc if sort_order == "desc" else asc)(column), Document.id.asc()).limit(limit).offset(offset)
    return list(db.scalars(query).all())


def get_owned_document(db: Session, owner_id: int, document_id: UUID, *, include_deleted: bool = False) -> Document:
    """Return a document only when it belongs to the caller; conceal cross-owner IDs."""
    query = select(Document).where(Document.id == document_id, Document.owner_id == owner_id)
    if not include_deleted:
        query = query.where(Document.deleted_at.is_(None))
    document = db.scalar(query)
    if document is None:
        raise DocumentNotFound
    return document


def download_document(
    db: Session,
    storage_factory: StorageProviderFactory,
    owner_id: int,
    document_id: UUID,
    *,
    action: str = "DOCUMENT_DOWNLOADED",
    request_ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[Document, bytes]:
    """Authorize owner or active recipient before reading private storage bytes."""
    document, _level = require_document_permission(db, owner_id, document_id, "READ")
    storage = storage_factory(document.storage_provider)
    try:
        content = storage.download_file(document.storage_key, document.storage_bucket)
        if document.checksum and not hmac.compare_digest(hashlib.sha256(content).hexdigest(), document.checksum):
            raise DocumentPersistenceError("Stored document integrity check failed.")
        db.add(DocumentActivity(document_id=document.id, actor_user_id=owner_id, action=action, result="SUCCESS", request_ip=request_ip, user_agent=user_agent, details={"version_number": document.current_version}))
        db.commit()
        return document, content
    finally:
        _close_storage_provider(storage)


def get_accessible_document(db: Session, user_id: int, document_id: UUID, *, include_deleted: bool = False) -> tuple[Document, str]:
    """Resolve current owner/grant state from PostgreSQL on every protected request."""
    user = db.get(User, user_id)
    document = db.get(Document, document_id)
    if user is None or not user.is_active or user.account_status != "ACTIVE":
        if user is not None:
            _record_access_denied(db, user_id, document_id, document)
        raise DocumentNotFound
    if document is None or (document.deleted_at is not None and not include_deleted):
        _record_access_denied(db, user_id, document_id, document)
        raise DocumentNotFound
    if document.owner_id == user_id:
        return document, "OWNER"
    now = datetime.now(timezone.utc)
    grant = db.scalar(select(DocumentPermission).where(
        DocumentPermission.document_id == document_id,
        DocumentPermission.granted_to_user_id == user_id,
        DocumentPermission.revoked_at.is_(None),
        or_(DocumentPermission.expires_at.is_(None), DocumentPermission.expires_at > now),
    ))
    owner = db.get(User, document.owner_id)
    same_organization = (
        user.organization_id is not None
        and owner is not None
        and owner.organization_id == user.organization_id
    )
    if document.visibility != "PRIVATE" and grant is not None and same_organization:
        return document, grant.permission_level
    _record_access_denied(db, user_id, document_id, document)
    raise DocumentNotFound


def require_document_permission(
    db: Session,
    user_id: int,
    document_id: UUID,
    operation: str,
    *,
    include_deleted: bool = False,
) -> tuple[Document, str]:
    """Central authorization decision for protected document operations.

    READ maps to legacy VIEWER, EDIT maps to EDITOR, while OWNER remains a
    delegated full-control permission for backward compatibility. Only OWNER
    can delete, restore, manage grants, or view the per-document audit history.
    """
    document, access_level = get_accessible_document(db, user_id, document_id, include_deleted=include_deleted)
    allowed = {
        "READ": {"OWNER", "VIEWER", "EDITOR", "READ", "EDIT"},
        "EDIT": {"EDITOR", "OWNER", "EDIT"},
        "DELETE": {"OWNER"},
        "RESTORE": {"OWNER"},
        "MANAGE_PERMISSIONS": {"OWNER"},
        "READ_AUDIT": {"OWNER"},
    }.get(operation)
    if allowed is None:
        raise ValueError(f"Unknown document operation: {operation}")
    if access_level not in allowed:
        _record_access_denied(db, user_id, document_id, document)
        db.add(DocumentActivity(document_id=document_id, actor_user_id=user_id, action=f"DOCUMENT_{operation}_DENIED", result="DENIED", details={"operation": operation}))
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
        raise DocumentPermissionDenied
    if operation in {"DELETE", "RESTORE", "MANAGE_PERMISSIONS", "READ_AUDIT"}:
        validate_document_ownership(db, user_id, document_id, include_deleted=include_deleted)
    audit_action = {"READ": "DOCUMENT_READ_ALLOWED", "EDIT": "DOCUMENT_EDIT_ALLOWED", "DELETE": "DOCUMENT_DELETE_ALLOWED"}.get(operation)
    if audit_action:
        db.add(DocumentActivity(document_id=document_id, actor_user_id=user_id, action=audit_action, result="SUCCESS", details={"operation": operation}))
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
    return document, access_level


def validate_document_ownership(
    db: Session,
    user_id: int,
    document_id: UUID,
    *,
    include_deleted: bool = False,
) -> Document:
    """Require actual ownership; delegated permissions never transfer ownership."""
    document = db.get(Document, document_id)
    if document is None or document.owner_id != user_id or (document.deleted_at is not None and not include_deleted):
        _record_access_denied(db, user_id, document_id, document)
        raise DocumentNotFound
    return document


def can_read_document(db: Session, user_id: int, document_id: UUID) -> bool:
    """Return whether the active user currently has READ access."""
    try:
        require_document_permission(db, user_id, document_id, "READ")
        return True
    except (DocumentNotFound, DocumentPermissionDenied):
        return False


def can_edit_document(db: Session, user_id: int, document_id: UUID) -> bool:
    """Return whether the active user currently has EDIT access."""
    try:
        require_document_permission(db, user_id, document_id, "EDIT")
        return True
    except (DocumentNotFound, DocumentPermissionDenied):
        return False


def can_delete_document(db: Session, user_id: int, document_id: UUID) -> bool:
    """Return whether the active user currently has document-owner delete access."""
    try:
        require_document_permission(db, user_id, document_id, "DELETE")
        return True
    except (DocumentNotFound, DocumentPermissionDenied):
        return False


def can_manage_permissions(db: Session, user_id: int, document_id: UUID) -> bool:
    """Return whether the active user may administer grants on this document."""
    try:
        require_document_permission(db, user_id, document_id, "MANAGE_PERMISSIONS")
        return True
    except (DocumentNotFound, DocumentPermissionDenied):
        return False


def _record_access_denied(db: Session, user_id: int, document_id: UUID, document: Document | None) -> None:
    """Record denial without disclosing document existence to the caller."""
    db.add(DocumentActivity(
        document_id=document.id if document is not None else None,
        actor_user_id=user_id,
        action="DOCUMENT_ACCESS_DENIED",
        result="DENIED",
        details={"requested_document_id": str(document_id)},
    ))
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.warning("Could not persist a document access-denied event.")


def get_authorized_documents(db: Session, user_id: int, *, search: str | None = None, category: str | None = None, file_type: str | None = None, owner_id: int | None = None, visibility: str | None = None, access_status: str | None = None, date_from: date | None = None, date_to: date | None = None, limit: int = 50, offset: int = 0, sort_by: str = "created_at", sort_order: str = "desc") -> list[Document]:
    """Search only active documents owned by or explicitly shared with a user."""
    now = datetime.now(timezone.utc)
    current_user = db.get(User, user_id)
    if current_user is None or not current_user.is_active or current_user.account_status != "ACTIVE":
        return []
    shared = exists(select(DocumentPermission.id).where(
        DocumentPermission.document_id == Document.id,
        DocumentPermission.granted_to_user_id == user_id,
        DocumentPermission.revoked_at.is_(None),
        or_(DocumentPermission.expires_at.is_(None), DocumentPermission.expires_at > now),
    ))
    shared_scope = false() if current_user.organization_id is None else and_(
        Document.visibility != "PRIVATE",
        shared,
        Document.owner.has(User.organization_id == current_user.organization_id),
    )
    query = select(Document).where(
        Document.deleted_at.is_(None),
        or_(Document.owner_id == user_id, shared_scope),
    )
    if search and search.strip():
        term = search.strip()
        escaped = re.sub(r"([%_\\])", r"\\\1", term)
        text_match = or_(Document.document_name.ilike(f"%{escaped}%", escape="\\"), Document.original_filename.ilike(f"%{escaped}%", escape="\\"))
        try:
            text_match = or_(text_match, Document.id == UUID(term))
        except ValueError:
            pass
        query = query.where(text_match)
    if category:
        query = query.where(Document.category == category)
    if file_type:
        query = query.where(Document.file_extension == file_type.lower().removeprefix("."))
    if owner_id:
        query = query.where(Document.owner_id == owner_id)
    if access_status == "OWNED":
        query = query.where(Document.owner_id == user_id)
    elif access_status == "SHARED":
        query = query.where(Document.owner_id != user_id)
    if visibility:
        query = query.where(Document.visibility == visibility)
    if date_from:
        query = query.where(Document.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        query = query.where(Document.created_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc))
    columns = {"created_at": Document.created_at, "document_name": Document.document_name, "file_size": Document.file_size}
    column = columns.get(sort_by, Document.created_at)
    return list(db.scalars(query.order_by((desc if sort_order == "desc" else asc)(column), Document.id.asc()).limit(limit).offset(offset)).all())


# Backward-compatible name retained for existing callers/tests.
list_accessible_documents = get_authorized_documents


def soft_delete_document(db: Session, user: User, document_id: UUID, *, request_ip: str | None = None, user_agent: str | None = None) -> None:
    """Soft-delete an owned or delegated-owner document without deleting file bytes."""
    document, _ = require_document_permission(db, user.id, document_id, "DELETE")
    document.deleted_at = datetime.now(timezone.utc)
    for grant in db.scalars(select(DocumentPermission).where(DocumentPermission.document_id == document_id, DocumentPermission.revoked_at.is_(None))):
        grant.revoked_at = document.deleted_at
        grant.revoked_by_user_id = user.id
    db.add(DocumentActivity(document_id=document.id, actor_user_id=user.id, action="DOCUMENT_DELETED", result="SUCCESS", request_ip=request_ip, user_agent=user_agent, details={}))
    db.commit()


def restore_document(db: Session, user: User, document_id: UUID, *, request_ip: str | None = None, user_agent: str | None = None) -> Document:
    """Restore a soft-deleted owned document; prior permission grants stay revoked."""
    document, _ = require_document_permission(db, user.id, document_id, "RESTORE", include_deleted=True)
    if document.deleted_at is None:
        raise DocumentConflict("Document is not deleted.")
    document.deleted_at = None
    db.add(DocumentActivity(document_id=document.id, actor_user_id=user.id, action="DOCUMENT_RESTORED", result="SUCCESS", request_ip=request_ip, user_agent=user_agent, details={}))
    db.commit()
    return document


def deleted_documents(db: Session, owner_id: int, limit: int = 50, offset: int = 0) -> list[Document]:
    """Return only soft-deleted documents owned by this user."""
    return list(db.scalars(select(Document).where(Document.owner_id == owner_id, Document.deleted_at.is_not(None)).order_by(desc(Document.deleted_at)).limit(limit).offset(offset)).all())


def delete_document(db: Session, storage_factory: StorageProviderFactory, user: User, document_id: UUID) -> None:
    """Compatibility wrapper: delete now means recoverable soft deletion."""
    del storage_factory
    soft_delete_document(db, user, document_id)
