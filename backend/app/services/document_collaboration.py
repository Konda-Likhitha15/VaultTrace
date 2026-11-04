"""Document permissions, versions, metadata, and activity workflows."""

import hashlib
import hmac
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import desc, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models import Document, DocumentActivity, DocumentPermission, DocumentVersion, User
from app.services.document_validation import DocumentValidationError, validate_upload
from app.services.audit import record_audit_event
from app.services.documents import (
    DocumentConflict,
    DocumentNotFound,
    DocumentPermissionDenied,
    DocumentPersistenceError,
    StorageProviderFactory,
    _close_storage_provider,
    create_storage_key,
    get_accessible_document,
    require_document_permission,
    validate_document_ownership,
)
from app.services.storage import StorageService


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _valid_expiration(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    if value <= _now():
        raise DocumentConflict("Permission expiration must be in the future.")
    return value


def _require_owner(db: Session, user_id: int, document_id: UUID) -> None:
    """Require the actual document owner, never a delegated legacy OWNER grant."""
    validate_document_ownership(db, user_id, document_id, operation="MANAGE_PERMISSIONS")


def list_permissions(db: Session, user_id: int, document_id: UUID) -> list[DocumentPermission]:
    """List current and revoked grants for an actual or delegated document owner."""
    _document, _ = require_document_permission(db, user_id, document_id, "MANAGE_PERMISSIONS")
    _require_owner(db, user_id, document_id)
    return list(db.scalars(
        select(DocumentPermission)
        .options(joinedload(DocumentPermission.granted_to))
        .where(DocumentPermission.document_id == document_id)
        .order_by(DocumentPermission.created_at.desc(), DocumentPermission.id.desc())
    ).unique())


def eligible_share_users(db: Session, user_id: int, document_id: UUID, search: str) -> list[User]:
    """Search active, verified accounts only inside the owner's organization."""
    document = validate_document_ownership(db, user_id, document_id, operation="READ")
    owner = db.get(User, document.owner_id)
    if owner is None or owner.organization_id is None:
        return []
    query = select(User).where(
        User.organization_id == owner.organization_id,
        User.id != user_id,
        User.is_active.is_(True),
        User.account_status == "ACTIVE",
        User.email_verified.is_(True),
    )
    term = search.strip()
    if term:
        query = query.where(User.email.ilike(f"%{term}%") | User.username.ilike(f"%{term}%"))
        if term.isdigit():
            query = query.where(or_(User.id == int(term), User.email.ilike(f"%{term}%"), User.username.ilike(f"%{term}%")))
    return list(db.scalars(query.order_by(User.username).limit(20)).all())


def grant_permission(
    db: Session,
    user_id: int,
    document_id: UUID,
    *,
    recipient_user_id: int | None,
    recipient_email: str | None,
    permission_level: str,
    expires_at: datetime | None,
    request_ip: str | None = None,
    user_agent: str | None = None,
) -> DocumentPermission:
    """Grant/regrant registered-user access without transferring document ownership."""
    document, _ = require_document_permission(db, user_id, document_id, "MANAGE_PERMISSIONS")
    _require_owner(db, user_id, document_id)
    permission_level = {"READ": "VIEWER", "EDIT": "EDITOR"}.get(permission_level, permission_level)
    if permission_level not in {"VIEWER", "EDITOR"}:
        raise DocumentConflict("Unsupported document permission level.")
    expiration = _valid_expiration(expires_at)
    if recipient_user_id is not None:
        recipient = db.scalar(select(User).where(User.id == recipient_user_id))
    else:
        recipient = db.scalar(select(User).where(User.email == str(recipient_email).strip().lower()))
    owner = db.get(User, document.owner_id)
    if (recipient is None or not recipient.is_active or recipient.account_status != "ACTIVE"
            or not recipient.email_verified or recipient.organization_id is None
            or owner is None or owner.organization_id is None
            or owner.organization_id != recipient.organization_id):
        raise DocumentNotFound
    if recipient.id == user_id:
        raise DocumentConflict("A document cannot be shared with the acting user.")
    permission = db.scalar(select(DocumentPermission).where(
        DocumentPermission.document_id == document_id,
        DocumentPermission.granted_to_user_id == recipient.id,
    ).with_for_update())
    now = _now()
    if permission is not None and permission.revoked_at is None and (_aware(permission.expires_at) is None or _aware(permission.expires_at) > now):
        raise DocumentConflict("This user already has active access.")
    old_level = permission.permission_level if permission is not None else None
    if permission is None:
        permission = DocumentPermission(
            document_id=document_id,
            granted_by_user_id=user_id,
            granted_to_user_id=recipient.id,
            permission_level=permission_level,
            expires_at=expiration,
        )
        db.add(permission)
    else:
        permission.granted_by_user_id = user_id
        permission.permission_level = permission_level
        permission.expires_at = expiration
        permission.revoked_at = None
        permission.revoked_by_user_id = None
        permission.updated_at = now
    try:
        db.flush()
        if document.visibility == "PRIVATE":
            document.visibility = "SHARED"
        db.add(DocumentActivity(
            document_id=document_id,
            actor_user_id=user_id,
            action="PERMISSION_GRANTED",
            result="SUCCESS",
            request_ip=request_ip,
            user_agent=user_agent,
            details={"permission_id": permission.id, "recipient_user_id": recipient.id, "previous_permission": old_level, "new_permission": permission_level, "expires_at": expiration.isoformat() if expiration else None},
        ))
        record_audit_event(db, "PERMISSION_GRANTED", actor=db.get(User, user_id), target_user_id=recipient.id, resource_type="Document", resource_id=document_id, organization_id=owner.organization_id, request_ip=request_ip, user_agent=user_agent, details={"permission_id": permission.id, "permission_level": permission_level, "expires_at": expiration.isoformat() if expiration else None}, previous_state={"permission_level": old_level} if old_level else None, new_state={"permission_level": permission_level})
        db.commit()
        db.refresh(permission)
        return permission
    except IntegrityError as exc:
        db.rollback()
        raise DocumentConflict("This user already has an access record for the document.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise DocumentPersistenceError("Document access could not be saved.") from exc


def update_permission(
    db: Session,
    user_id: int,
    document_id: UUID,
    permission_id: int,
    *,
    permission_level: str | None,
    expires_at: datetime | None,
    expiration_was_set: bool,
    request_ip: str | None = None,
    user_agent: str | None = None,
) -> DocumentPermission:
    """Change an active grant while recording its before/after permission state."""
    _document, _ = require_document_permission(db, user_id, document_id, "MANAGE_PERMISSIONS")
    _require_owner(db, user_id, document_id)
    permission = db.scalar(select(DocumentPermission).where(
        DocumentPermission.id == permission_id,
        DocumentPermission.document_id == document_id,
    ).with_for_update())
    if permission is None or permission.revoked_at is not None:
        raise DocumentNotFound
    old_level, old_expiration = permission.permission_level, permission.expires_at
    if permission_level is not None:
        permission_level = {"READ": "VIEWER", "EDIT": "EDITOR"}.get(permission_level, permission_level)
        if permission_level not in {"VIEWER", "EDITOR"}:
            raise DocumentConflict("Unsupported document permission level.")
        permission.permission_level = permission_level
    if expiration_was_set:
        permission.expires_at = _valid_expiration(expires_at)
    permission.updated_at = _now()
    db.add(DocumentActivity(
        document_id=document_id,
        actor_user_id=user_id,
        action="PERMISSION_UPDATED",
        result="SUCCESS",
        request_ip=request_ip,
        user_agent=user_agent,
        details={"recipient_user_id": permission.granted_to_user_id, "previous_permission": old_level, "new_permission": permission.permission_level, "previous_expiration": old_expiration.isoformat() if old_expiration else None, "new_expiration": permission.expires_at.isoformat() if permission.expires_at else None},
    ))
    record_audit_event(db, "PERMISSION_MODIFIED", actor=db.get(User, user_id), target_user_id=permission.granted_to_user_id, resource_type="Document", resource_id=document_id, organization_id=db.get(Document, document_id).owner.organization_id, request_ip=request_ip, user_agent=user_agent, details={"permission_id": permission.id}, previous_state={"permission_level": old_level, "expires_at": old_expiration.isoformat() if old_expiration else None}, new_state={"permission_level": permission.permission_level, "expires_at": permission.expires_at.isoformat() if permission.expires_at else None})
    db.commit()
    db.refresh(permission)
    return permission


def revoke_permission(db: Session, user_id: int, document_id: UUID, permission_id: int, *, request_ip: str | None = None, user_agent: str | None = None) -> None:
    """Immediately revoke an active grant and append a durable audit event."""
    require_document_permission(db, user_id, document_id, "MANAGE_PERMISSIONS")
    _require_owner(db, user_id, document_id)
    permission = db.scalar(select(DocumentPermission).where(
        DocumentPermission.id == permission_id,
        DocumentPermission.document_id == document_id,
    ).with_for_update())
    if permission is None or permission.revoked_at is not None:
        raise DocumentNotFound
    permission.revoked_at = _now()
    permission.revoked_by_user_id = user_id
    permission.updated_at = permission.revoked_at
    db.add(DocumentActivity(
        document_id=document_id,
        actor_user_id=user_id,
        action="PERMISSION_REVOKED",
        result="SUCCESS",
        request_ip=request_ip,
        user_agent=user_agent,
        details={"permission_id": permission.id, "recipient_user_id": permission.granted_to_user_id, "permission_level": permission.permission_level},
    ))
    document = db.get(Document, document_id)
    record_audit_event(db, "PERMISSION_REVOKED", actor=db.get(User, user_id), target_user_id=permission.granted_to_user_id, resource_type="Document", resource_id=document_id, organization_id=document.owner.organization_id if document else None, request_ip=request_ip, user_agent=user_agent, details={"permission_id": permission.id, "permission_level": permission.permission_level})
    db.commit()


def update_document_metadata(db: Session, user_id: int, document_id: UUID, changes: dict[str, object], *, request_ip: str | None = None, user_agent: str | None = None) -> Document:
    """Edit document metadata for Editors; only Owners may change visibility."""
    document, level = require_document_permission(db, user_id, document_id, "EDIT")
    allowed = {key: value for key, value in changes.items() if key in {"document_name", "category", "description", "visibility"}}
    if not allowed:
        raise DocumentConflict("No editable document fields were provided.")
    if "visibility" in allowed:
        _require_owner(db, user_id, document_id)
        visibility = allowed["visibility"]
        if visibility not in {"PRIVATE", "SHARED", "RESTRICTED"}:
            raise DocumentConflict("Unsupported visibility value.")
        if visibility == "PRIVATE":
            now = _now()
            active = db.scalars(select(DocumentPermission).where(DocumentPermission.document_id == document_id, DocumentPermission.revoked_at.is_(None))).all()
            for grant in active:
                grant.revoked_at = now
                grant.revoked_by_user_id = user_id
                grant.updated_at = now
                db.add(DocumentActivity(document_id=document_id, actor_user_id=user_id, action="PERMISSION_REVOKED", result="SUCCESS", request_ip=request_ip, user_agent=user_agent, details={"permission_id": grant.id, "recipient_user_id": grant.granted_to_user_id, "reason": "visibility_private"}))
    previous = {field: getattr(document, field) for field in allowed}
    for field, value in allowed.items():
        if isinstance(value, str):
            value = value.strip()
        if field in {"document_name", "category"} and not value:
            raise DocumentConflict(f"{field} cannot be empty.")
        setattr(document, field, value)
    document.updated_at = _now()
    db.add(DocumentActivity(document_id=document_id, actor_user_id=user_id, action="DOCUMENT_METADATA_UPDATED", result="SUCCESS", request_ip=request_ip, user_agent=user_agent, details={"previous": previous, "new": allowed}))
    record_audit_event(db, "DOCUMENT_METADATA_UPDATED", actor=db.get(User, user_id), target_user_id=document.owner_id, resource_type="Document", resource_id=document_id, organization_id=document.owner.organization_id, request_ip=request_ip, user_agent=user_agent, details={"changed_fields": sorted(allowed)}, previous_state={"fields": sorted(previous)}, new_state={"fields": sorted(allowed)})
    db.commit()
    db.refresh(document)
    return document


def upload_document_version(
    db: Session,
    storage: StorageService,
    user_id: int,
    document_id: UUID,
    filename: str | None,
    supplied_mime: str | None,
    content: bytes,
    *,
    request_ip: str | None = None,
    user_agent: str | None = None,
) -> DocumentVersion:
    """Store a validated new version while retaining every earlier file object."""
    document, level = require_document_permission(db, user_id, document_id, "EDIT")
    document = db.scalar(select(Document).where(Document.id == document_id).with_for_update())
    if document is None or document.deleted_at is not None:
        raise DocumentNotFound
    validated = validate_upload(filename, supplied_mime, content)
    version_number = document.current_version + 1
    version_id = uuid4()
    storage_key = create_storage_key(document.owner_id, version_id, validated.extension)
    provider = storage.provider_name
    bucket = settings.supabase_storage_bucket if provider == "supabase" else "local-private-storage"
    storage.upload_file(storage_key, content, validated.mime_type, bucket)
    version = DocumentVersion(
        id=version_id,
        document_id=document_id,
        version_number=version_number,
        storage_provider=provider,
        storage_bucket=bucket,
        storage_key=storage_key,
        original_filename=validated.original_filename,
        file_extension=validated.extension,
        mime_type=validated.mime_type,
        file_size=validated.size,
        checksum=validated.checksum,
        created_by_user_id=user_id,
    )
    document.current_version = version_number
    document.storage_provider = provider
    document.storage_bucket = bucket
    document.storage_key = storage_key
    document.original_filename = validated.original_filename
    document.file_extension = validated.extension
    document.mime_type = validated.mime_type
    document.file_size = validated.size
    document.checksum = validated.checksum
    document.updated_at = _now()
    db.add(version)
    db.add(DocumentActivity(document_id=document_id, actor_user_id=user_id, action="DOCUMENT_VERSION_CREATED", result="SUCCESS", request_ip=request_ip, user_agent=user_agent, details={"version_number": version_number, "checksum": validated.checksum}))
    record_audit_event(db, "DOCUMENT_VERSION_UPLOADED", actor=db.get(User, user_id), target_user_id=document.owner_id, resource_type="Document", resource_id=document_id, organization_id=document.owner.organization_id, request_ip=request_ip, user_agent=user_agent, details={"version_number": version_number, "file_size": validated.size})
    try:
        db.commit()
        db.refresh(version)
        return version
    except SQLAlchemyError as exc:
        db.rollback()
        try:
            storage.delete_file(storage_key, bucket)
        except Exception:
            pass
        raise DocumentPersistenceError("New file version could not be saved; storage cleanup was attempted.") from exc


def list_versions(db: Session, user_id: int, document_id: UUID) -> list[DocumentVersion]:
    """Return a document's version metadata after an access check."""
    require_document_permission(db, user_id, document_id, "READ")
    return list(db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document_id).order_by(desc(DocumentVersion.version_number))).all())


def download_version(db: Session, storage_factory: StorageProviderFactory, user_id: int, document_id: UUID, version_id: UUID, *, action: str = "DOCUMENT_DOWNLOADED", request_ip: str | None = None, user_agent: str | None = None) -> tuple[DocumentVersion, bytes]:
    """Authorize access and stream one historical version through its recorded provider."""
    require_document_permission(db, user_id, document_id, "READ")
    version = db.scalar(select(DocumentVersion).where(DocumentVersion.id == version_id, DocumentVersion.document_id == document_id))
    if version is None:
        raise DocumentNotFound
    storage = storage_factory(version.storage_provider)
    try:
        content = storage.download_file(version.storage_key, version.storage_bucket)
        if version.checksum and not hmac.compare_digest(hashlib.sha256(content).hexdigest(), version.checksum):
            raise DocumentPersistenceError("Stored document integrity check failed.")
        db.add(DocumentActivity(document_id=document_id, actor_user_id=user_id, action=action, result="SUCCESS", request_ip=request_ip, user_agent=user_agent, details={"version_number": version.version_number}))
        document = db.get(Document, document_id)
        record_audit_event(db, action, actor=db.get(User, user_id), target_user_id=document.owner_id if document else None, resource_type="Document", resource_id=document_id, organization_id=document.owner.organization_id if document else None, request_ip=request_ip, user_agent=user_agent, details={"version_number": version.version_number, "file_size": version.file_size})
        db.commit()
        return version, content
    finally:
        _close_storage_provider(storage)


def document_activity(db: Session, user_id: int, document_id: UUID, limit: int = 100, offset: int = 0) -> list[DocumentActivity]:
    """Return activity only to owners and delegated OWNER recipients."""
    require_document_permission(db, user_id, document_id, "READ_AUDIT")
    _require_owner(db, user_id, document_id)
    return list(db.scalars(select(DocumentActivity).where(DocumentActivity.document_id == document_id).order_by(desc(DocumentActivity.created_at)).limit(limit).offset(offset)).all())


def shared_with_me(db: Session, user_id: int, limit: int = 50, offset: int = 0) -> list[tuple[Document, DocumentPermission]]:
    """List discoverable documents with an unexpired, unrevoked grant to this user."""
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.account_status != "ACTIVE" or user.organization_id is None:
        return []
    now = _now()
    return [(document, permission) for document, permission in db.execute(select(Document, DocumentPermission).join(DocumentPermission).where(
        DocumentPermission.granted_to_user_id == user_id,
        DocumentPermission.revoked_at.is_(None),
        (DocumentPermission.expires_at.is_(None) | (DocumentPermission.expires_at > now)),
        Document.deleted_at.is_(None),
        Document.visibility != "PRIVATE",
        Document.owner.has(User.organization_id == user.organization_id),
    ).order_by(desc(DocumentPermission.created_at)).limit(limit).offset(offset)).unique().all()]


def shared_by_me(db: Session, user_id: int, limit: int = 100, offset: int = 0) -> list[DocumentPermission]:
    """List grants created by this user or attached to their own documents."""
    return list(db.scalars(select(DocumentPermission).options(
        joinedload(DocumentPermission.document), joinedload(DocumentPermission.granted_to)
    ).join(Document).where(
        DocumentPermission.document_id == Document.id,
        Document.deleted_at.is_(None),
        (Document.owner_id == user_id) | (DocumentPermission.granted_by_user_id == user_id),
    ).order_by(desc(DocumentPermission.created_at)).limit(limit).offset(offset)).unique())


def accessible_categories(db: Session, user_id: int) -> list[str]:
    """List only categories on documents visible to the caller."""
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.account_status != "ACTIVE":
        return []
    now = _now()
    shared = select(DocumentPermission.id).where(
        DocumentPermission.document_id == Document.id,
        DocumentPermission.granted_to_user_id == user_id,
        DocumentPermission.revoked_at.is_(None),
        (DocumentPermission.expires_at.is_(None)) | (DocumentPermission.expires_at > now),
    ).exists()
    shared_scope = False if user.organization_id is None else ((Document.visibility != "PRIVATE") & shared & Document.owner.has(User.organization_id == user.organization_id))
    return list(db.scalars(select(Document.category).where(
        Document.deleted_at.is_(None),
        (Document.owner_id == user_id) | shared_scope,
    ).distinct().order_by(Document.category)).all())


def admin_document_metadata(db: Session, *, search: str | None, limit: int, offset: int) -> list[Document]:
    """Search all document metadata for authorized administrators only."""
    query = select(Document)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.where(Document.document_name.ilike(term) | Document.original_filename.ilike(term))
    return list(db.scalars(query.order_by(desc(Document.created_at)).limit(limit).offset(offset)).all())


def admin_document_permissions(db: Session, *, document_id: UUID | None, limit: int, offset: int) -> list[DocumentPermission]:
    """List current and historical access grants for administrator review."""
    query = select(DocumentPermission).options(
        joinedload(DocumentPermission.document),
        joinedload(DocumentPermission.granted_to),
    ).order_by(desc(DocumentPermission.created_at))
    if document_id is not None:
        query = query.where(DocumentPermission.document_id == document_id)
    return list(db.scalars(query.limit(limit).offset(offset)).unique())


def admin_document_activity(db: Session, *, document_id: UUID | None, limit: int, offset: int) -> list[DocumentActivity]:
    """List security events for document metadata investigation, never content."""
    query = select(DocumentActivity).options(joinedload(DocumentActivity.actor)).order_by(desc(DocumentActivity.created_at))
    if document_id is not None:
        query = query.where(DocumentActivity.document_id == document_id)
    return list(db.scalars(query.limit(limit).offset(offset)).unique())


def admin_revoke_permission(db: Session, actor_id: int, permission_id: int, *, request_ip: str | None = None, user_agent: str | None = None) -> None:
    """Allow an administrator to revoke a grant without granting content access."""
    permission = db.scalar(select(DocumentPermission).where(DocumentPermission.id == permission_id).with_for_update())
    if permission is None or permission.revoked_at is not None:
        raise DocumentNotFound
    permission.revoked_at = _now()
    permission.revoked_by_user_id = actor_id
    permission.updated_at = permission.revoked_at
    db.add(DocumentActivity(
        document_id=permission.document_id,
        actor_user_id=actor_id,
        action="PERMISSION_REVOKED",
        result="SUCCESS",
        request_ip=request_ip,
        user_agent=user_agent,
        details={"permission_id": permission.id, "recipient_user_id": permission.granted_to_user_id, "permission_level": permission.permission_level, "administrative_action": True},
    ))
    document = db.get(Document, permission.document_id)
    record_audit_event(db, "PERMISSION_REVOKED", actor=db.get(User, actor_id), target_user_id=permission.granted_to_user_id, resource_type="Document", resource_id=permission.document_id, organization_id=document.owner.organization_id if document else None, request_ip=request_ip, user_agent=user_agent, details={"permission_id": permission.id, "administrative_action": True})
    db.commit()
