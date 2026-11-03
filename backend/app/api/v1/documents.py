"""Authenticated, owner-scoped document upload, query, download, and delete APIs."""

from collections.abc import Generator
from datetime import date, datetime, timezone
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models import DocumentActivity, DocumentPermission, User
from app.schemas.documents import (
    DocumentActivityResponse,
    DocumentMetadataUpdate,
    DocumentPermissionCreate,
    DocumentPermissionResponse,
    EligibleShareUserResponse,
    DocumentPermissionUpdate,
    DocumentResponse,
    DocumentSearchResponse,
    DocumentVersionResponse,
    SharedByMeResponse,
    SharedDocumentResponse,
)
from app.services.document_collaboration import (
    document_activity,
    download_version,
    accessible_categories,
    grant_permission,
    list_permissions,
    eligible_share_users,
    list_versions,
    revoke_permission,
    shared_by_me,
    shared_with_me,
    update_document_metadata,
    update_permission,
    upload_document_version,
)
from app.services.documents import (
    DocumentNotFound,
    DocumentPermissionDenied,
    DocumentConflict,
    DocumentPersistenceError,
    DocumentValidationError,
    StorageProviderFactory,
    deleted_documents,
    download_document,
    get_accessible_document,
    require_document_permission,
    get_owned_document,
    get_authorized_documents,
    list_documents,
    restore_document,
    soft_delete_document,
    upload_document,
)
from app.services.storage import (
    StorageConfigurationError,
    StorageOperationError,
    StorageService,
    create_storage_provider,
)
from app.core.config import settings

router = APIRouter(prefix="/documents", tags=["documents"])


def get_storage_service() -> Generator[StorageService, None, None]:
    """Initialize the explicitly selected provider; never fall back to another backend."""
    try:
        storage = create_storage_provider()
    except StorageConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        yield storage
    finally:
        storage.close()


def get_storage_provider_factory() -> StorageProviderFactory:
    """Provide provider construction for a document's persisted storage location."""
    return create_storage_provider


def _storage_error(exc: Exception) -> HTTPException:
    if isinstance(exc, StorageConfigurationError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, StorageOperationError):
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=503, detail="Document storage is temporarily unavailable.")


def _request_metadata(request: Request) -> tuple[str | None, str | None]:
    """Extract bounded, non-secret audit metadata from the incoming request."""
    client_ip = request.client.host if request.client else None
    return client_ip, request.headers.get("user-agent", "")[:512] or None


def _permission_response(permission) -> DocumentPermissionResponse:
    recipient = permission.granted_to
    return DocumentPermissionResponse(
        id=permission.id,
        granted_to_user_id=recipient.id,
        recipient_username=recipient.username,
        recipient_name=recipient.full_name,
        recipient_email=recipient.email,
        permission_level={"VIEWER": "READ", "EDITOR": "EDIT", "OWNER": "EDIT"}.get(permission.permission_level, permission.permission_level),
        created_at=permission.created_at,
        expires_at=permission.expires_at,
        revoked_at=permission.revoked_at,
    )


def _activity_response(event: DocumentActivity) -> DocumentActivityResponse:
    return DocumentActivityResponse(
        id=event.id,
        document_id=event.document_id,
        actor_user_id=event.actor_user_id,
        actor_username=event.actor.username,
        action=event.action,
        result=event.result,
        details=event.details,
        created_at=event.created_at,
    )


def _search_response(document, user: User, db: Session) -> DocumentSearchResponse:
    if document.owner_id == user.id:
        access_level = "OWNER"
    else:
        permission = db.scalar(select(DocumentPermission).where(
            DocumentPermission.document_id == document.id,
            DocumentPermission.granted_to_user_id == user.id,
            DocumentPermission.revoked_at.is_(None),
            (DocumentPermission.expires_at.is_(None)) | (DocumentPermission.expires_at > datetime.now(timezone.utc)),
        ))
        access_level = {"VIEWER": "READ", "EDITOR": "EDIT", "OWNER": "EDIT"}.get(permission.permission_level, "READ") if permission else "READ"
    response = DocumentResponse.model_validate(document).model_dump()
    return DocumentSearchResponse(
        **response,
        owner_name=document.owner.full_name,
        owner_username=document.owner.username,
        access_level=access_level,
    )


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def upload(
    request: Request,
    file: UploadFile = File(...),
    document_name: str = Form(..., min_length=1, max_length=200),
    category: str = Form(..., min_length=1, max_length=64),
    description: str | None = Form(default=None, max_length=4000),
    visibility: Literal["PRIVATE", "SHARED", "RESTRICTED"] = Form(default="PRIVATE"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
) -> DocumentResponse:
    """Validate file bytes before storing them privately and persisting metadata."""
    try:
        content = file.file.read(settings.document_max_upload_bytes + 1)
        client_ip, user_agent = _request_metadata(request)
        document = upload_document(
            db,
            storage,
            user,
            file.filename,
            file.content_type,
            content,
            document_name,
            category,
            description,
            visibility,
            client_ip,
            user_agent,
        )
        return DocumentResponse.model_validate(document)
    except DocumentValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DocumentPermissionDenied as exc:
        raise HTTPException(status_code=403, detail="This role cannot upload documents.") from exc
    except DocumentPersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (StorageConfigurationError, StorageOperationError) as exc:
        raise _storage_error(exc) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Document metadata could not be saved.") from exc
    finally:
        file.file.close()


@router.get("/", response_model=list[DocumentResponse])
def get_documents(
    search: str | None = Query(default=None, max_length=200),
    owner_id: int | None = Query(default=None, ge=1),
    category: str | None = Query(default=None, max_length=64),
    date_from: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: Literal["created_at", "document_name", "file_size"] = Query(default="created_at"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DocumentResponse]:
    """List only the caller's documents with search/filter/sort/pagination."""
    if owner_id is not None and owner_id != user.id:
        raise HTTPException(status_code=404, detail="No documents found.")
    try:
        from datetime import date

        from_date = date.fromisoformat(date_from) if date_from else None
        to_date = date.fromisoformat(date_to) if date_to else None
        if from_date and to_date and from_date > to_date:
            raise HTTPException(status_code=422, detail="date_from must not be later than date_to.")
        documents = list_documents(
            db,
            user.id,
            search=search,
            category=category,
            date_from=from_date,
            date_to=to_date,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return [DocumentResponse.model_validate(item) for item in documents]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Date filters must use YYYY-MM-DD.") from exc


@router.get("/search", response_model=list[DocumentSearchResponse])
def search_documents(
    search: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=64),
    file_type: str | None = Query(default=None, max_length=16),
    owner_id: int | None = Query(default=None, ge=1),
    visibility: Literal["PRIVATE", "SHARED", "RESTRICTED"] | None = None,
    access_status: Literal["OWNED", "SHARED"] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: Literal["created_at", "document_name", "file_size"] = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DocumentSearchResponse]:
    """Search by UUID, display name, or source filename within authorized scope."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must not be later than date_to.")
    documents = get_authorized_documents(
        db, user.id, search=search, category=category, file_type=file_type,
        owner_id=owner_id, visibility=visibility, access_status=access_status,
        date_from=date_from, date_to=date_to, limit=limit, offset=offset,
        sort_by=sort_by, sort_order=sort_order,
    )
    return [_search_response(document, user, db) for document in documents]


@router.get("/categories", response_model=list[str])
def get_document_categories(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[str]:
    """Return category values from documents this user can discover."""
    return accessible_categories(db, user.id)


@router.get("/shared-with-me", response_model=list[SharedDocumentResponse])
def get_shared_with_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[SharedDocumentResponse]:
    """List documents with active grants to the authenticated recipient."""
    result = []
    for document, permission in shared_with_me(db, user.id):
        result.append(SharedDocumentResponse(
            document=DocumentResponse.model_validate(document),
            owner_name=document.owner.full_name,
            owner_username=document.owner.username,
            shared_at=permission.created_at,
            permission_level={"VIEWER": "READ", "EDITOR": "EDIT", "OWNER": "EDIT"}.get(permission.permission_level, "READ"),
            expires_at=permission.expires_at,
        ))
    return result


@router.get("/shared-by-me", response_model=list[SharedByMeResponse])
def get_shared_by_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[SharedByMeResponse]:
    """List grants created by or belonging to a document owned by this user."""
    return [SharedByMeResponse(
        document_id=permission.document_id,
        permission_id=permission.id,
        document_name=permission.document.document_name,
        recipient_user_id=permission.granted_to_user_id,
        recipient_name=permission.granted_to.full_name,
        recipient_username=permission.granted_to.username,
        permission_level={"VIEWER": "READ", "EDITOR": "EDIT", "OWNER": "EDIT"}.get(permission.permission_level, "READ"),
        shared_at=permission.created_at,
        expires_at=permission.expires_at,
        revoked_at=permission.revoked_at,
    ) for permission in shared_by_me(db, user.id)]


@router.get("/deleted", response_model=list[DocumentResponse])
def get_deleted_documents(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[DocumentResponse]:
    """List recoverable deleted documents owned by the authenticated user."""
    return [DocumentResponse.model_validate(item) for item in deleted_documents(db, user.id)]


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    """Return metadata only when the caller owns or has explicit access to it."""
    try:
        document, _level = require_document_permission(db, user.id, document_id, "READ")
        return DocumentResponse.model_validate(document)
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc


@router.get("/{document_id}/download")
def get_document_download(
    document_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage_factory: StorageProviderFactory = Depends(get_storage_provider_factory),
) -> StreamingResponse:
    """Authorize the active grant before retrieving private bytes through the backend."""
    try:
        client_ip, user_agent = _request_metadata(request)
        document, content = download_document(db, storage_factory, user.id, document_id, request_ip=client_ip, user_agent=user_agent)
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except DocumentPersistenceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (StorageConfigurationError, StorageOperationError) as exc:
        raise _storage_error(exc) from exc
    filename = quote(document.original_filename, safe="")
    return StreamingResponse(
        iter((content,)),
        media_type=document.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "Content-Length": str(len(content)),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{document_id}/preview")
def preview_document(
    document_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage_factory: StorageProviderFactory = Depends(get_storage_provider_factory),
) -> StreamingResponse:
    """Preview safe browser-renderable files through an authorized no-store stream."""
    try:
        document, _level = require_document_permission(db, user.id, document_id, "READ")
        if document.mime_type not in {"application/pdf", "image/png", "image/jpeg", "text/plain"}:
            raise HTTPException(status_code=415, detail="Preview is not supported for this file type; use download instead.")
        client_ip, user_agent = _request_metadata(request)
        document, content = download_document(db, storage_factory, user.id, document_id, action="DOCUMENT_PREVIEWED", request_ip=client_ip, user_agent=user_agent)
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except (StorageConfigurationError, StorageOperationError) as exc:
        raise _storage_error(exc) from exc
    filename = quote(document.original_filename, safe="")
    return StreamingResponse(iter((content,)), media_type=document.mime_type, headers={
        "Content-Disposition": f"inline; filename*=UTF-8''{filename}",
        "Content-Length": str(len(content)),
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox; default-src 'none';",
    })


@router.patch("/{document_id}", response_model=DocumentResponse)
def patch_document(
    document_id: UUID,
    payload: DocumentMetadataUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    """Edit authorized metadata; changing visibility revokes existing grants when made private."""
    try:
        changes = payload.model_dump(exclude_unset=True)
        client_ip, user_agent = _request_metadata(request)
        return DocumentResponse.model_validate(update_document_metadata(db, user.id, document_id, changes, request_ip=client_ip, user_agent=user_agent))
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except DocumentPermissionDenied as exc:
        raise HTTPException(status_code=403, detail="You do not have permission to edit this document.") from exc
    except DocumentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{document_id}/versions", response_model=list[DocumentVersionResponse])
def get_document_versions(document_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[DocumentVersionResponse]:
    """List immutable version metadata to anyone with document access."""
    try:
        return [DocumentVersionResponse.model_validate(item) for item in list_versions(db, user.id, document_id)]
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc


@router.post("/{document_id}/versions", response_model=DocumentVersionResponse, status_code=status.HTTP_201_CREATED)
def post_document_version(
    document_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
) -> DocumentVersionResponse:
    """Create a validated new version without removing previous file objects."""
    try:
        content = file.file.read(settings.document_max_upload_bytes + 1)
        client_ip, user_agent = _request_metadata(request)
        version = upload_document_version(db, storage, user.id, document_id, file.filename, file.content_type, content, request_ip=client_ip, user_agent=user_agent)
        return DocumentVersionResponse.model_validate(version)
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except DocumentPermissionDenied as exc:
        raise HTTPException(status_code=403, detail="You do not have permission to upload a version.") from exc
    except DocumentValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DocumentPersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (StorageConfigurationError, StorageOperationError) as exc:
        raise _storage_error(exc) from exc
    finally:
        file.file.close()


@router.get("/{document_id}/versions/{version_id}/download")
def download_document_version(
    document_id: UUID,
    version_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage_factory: StorageProviderFactory = Depends(get_storage_provider_factory),
) -> StreamingResponse:
    """Download one historical version after checking current access rights."""
    try:
        client_ip, user_agent = _request_metadata(request)
        version, content = download_version(db, storage_factory, user.id, document_id, version_id, request_ip=client_ip, user_agent=user_agent)
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except (StorageConfigurationError, StorageOperationError) as exc:
        raise _storage_error(exc) from exc
    filename = quote(version.original_filename, safe="")
    return StreamingResponse(iter((content,)), media_type=version.mime_type, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}", "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/{document_id}/activity", response_model=list[DocumentActivityResponse])
def get_document_activity(document_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db), limit: int = Query(default=100, ge=1, le=200), offset: int = Query(default=0, ge=0)) -> list[DocumentActivityResponse]:
    """Show activity only to the actual or delegated document owner."""
    try:
        return [_activity_response(event) for event in document_activity(db, user.id, document_id, limit, offset)]
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except DocumentPermissionDenied as exc:
        raise HTTPException(status_code=403, detail="Only document owners may review its activity.") from exc


@router.get("/{document_id}/permissions", response_model=list[DocumentPermissionResponse])
def get_document_permissions(document_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[DocumentPermissionResponse]:
    """List current and historical access grants for an owner/delegate."""
    try:
        return [_permission_response(item) for item in list_permissions(db, user.id, document_id)]
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except DocumentPermissionDenied as exc:
        raise HTTPException(status_code=403, detail="Only document owners may manage access.") from exc


@router.get("/{document_id}/eligible-users", response_model=list[EligibleShareUserResponse])
def get_eligible_share_users(document_id: UUID, q: str = Query(default="", max_length=160), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[EligibleShareUserResponse]:
    """Find active, verified recipients in the owner's organization only."""
    try:
        users = eligible_share_users(db, user.id, document_id, q)
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    return [EligibleShareUserResponse(id=item.id, full_name=item.full_name, username=item.username, email=item.email) for item in users]


@router.post("/{document_id}/permissions", response_model=DocumentPermissionResponse, status_code=status.HTTP_201_CREATED)
def post_document_permission(document_id: UUID, payload: DocumentPermissionCreate, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> DocumentPermissionResponse:
    """Grant explicit access to a registered account by ID or email."""
    try:
        client_ip, user_agent = _request_metadata(request)
        permission = grant_permission(db, user.id, document_id, recipient_user_id=payload.recipient_user_id, recipient_email=str(payload.recipient_email) if payload.recipient_email else None, permission_level=payload.permission_level, expires_at=payload.expires_at, request_ip=client_ip, user_agent=user_agent)
        return _permission_response(permission)
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Document or recipient was not found.") from exc
    except DocumentPermissionDenied as exc:
        raise HTTPException(status_code=403, detail="Only document owners may grant access.") from exc
    except DocumentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DocumentPersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.patch("/{document_id}/permissions/{permission_id}", response_model=DocumentPermissionResponse)
def patch_document_permission(document_id: UUID, permission_id: int, payload: DocumentPermissionUpdate, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> DocumentPermissionResponse:
    """Change permission level or expiry without transferring document ownership."""
    try:
        client_ip, user_agent = _request_metadata(request)
        permission = update_permission(db, user.id, document_id, permission_id, permission_level=payload.permission_level, expires_at=payload.expires_at, expiration_was_set="expires_at" in payload.model_fields_set, request_ip=client_ip, user_agent=user_agent)
        return _permission_response(permission)
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Permission record was not found.") from exc
    except DocumentPermissionDenied as exc:
        raise HTTPException(status_code=403, detail="Only document owners may manage access.") from exc
    except DocumentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{document_id}/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document_permission(document_id: UUID, permission_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    """Revoke access immediately while preserving the permission history."""
    try:
        client_ip, user_agent = _request_metadata(request)
        revoke_permission(db, user.id, document_id, permission_id, request_ip=client_ip, user_agent=user_agent)
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Permission record was not found.") from exc
    except DocumentPermissionDenied as exc:
        raise HTTPException(status_code=403, detail="Only document owners may revoke access.") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{document_id}/restore", response_model=DocumentResponse)
def post_restore_document(document_id: UUID, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> DocumentResponse:
    """Restore a deleted owned document; previously revoked shares remain revoked."""
    try:
        client_ip, user_agent = _request_metadata(request)
        return DocumentResponse.model_validate(restore_document(db, user, document_id, request_ip=client_ip, user_agent=user_agent))
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Deleted document not found.") from exc
    except DocumentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_document(
    document_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Soft-delete an owned/delegated-owner document; bytes stay recoverable in private storage."""
    try:
        client_ip, user_agent = _request_metadata(request)
        soft_delete_document(db, user, document_id, request_ip=client_ip, user_agent=user_agent)
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Document not found.") from exc
    except DocumentPermissionDenied as exc:
        raise HTTPException(status_code=403, detail="Only document owners may delete documents.") from exc
    except DocumentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DocumentPersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (StorageConfigurationError, StorageOperationError) as exc:
        raise _storage_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
