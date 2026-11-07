"""Administrator-only dashboard, review, role, and account APIs."""

import csv
import json
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_roles
from app.db.session import get_db
from app.models import DocumentActivity, Organization, RegistrationApplication, User
from app.schemas.documents import AdminDocumentPermissionResponse, AdminDocumentResponse, DocumentActivityResponse
from app.schemas.admin import (
    AdminAnalytics,
    AdminStorageDetail,
    AdminStoragePage,
    AccountStatusUpdateRequest,
    AdminActionResponse,
    AdminApplication,
    AdminOverview,
    AdminUser,
    ApproveApplicationRequest,
    RejectApplicationRequest,
    RoleUpdateRequest,
    OrganizationCreateRequest,
    OrganizationResponse,
    OrganizationAssignmentRequest,
)
from app.schemas.audit import AuditLogPage, AuditLogResponse, AuditQuery, AuditExportQuery, AuditSummary
from app.services.admin import (
    AdminActionConflict,
    AdminResourceNotFound,
    ProtectedAdministrator,
    approve_application,
    change_user_role,
    change_user_status,
    dashboard_overview,
    get_application,
    list_applications,
    list_users,
    reject_application,
)
from app.services.email import EmailDeliveryError, send_application_decision
from app.services.document_collaboration import admin_document_activity, admin_document_metadata, admin_document_permissions, admin_revoke_permission
from app.services.documents import DocumentNotFound
from app.services.audit import get_audit_event, list_audit_events, record_audit_event, summarize_audit_events
from app.services.admin_storage import admin_analytics, admin_storage_detail, admin_storage_page

router = APIRouter(prefix="/admin", tags=["administration"], dependencies=[Depends(require_roles("Administrator"))])


def _user_response(user: User) -> AdminUser:
    """Build the administrator-safe user projection."""
    return AdminUser(
        id=user.id,
        full_name=user.full_name,
        username=user.username,
        email=user.email,
        phone_number=user.phone_number,
        role=user.role.name,
        email_verified=user.email_verified,
        account_status=user.account_status,
        registration_date=user.created_at,
        updated_at=user.updated_at,
        organization_id=user.organization_id,
    )


def _application_response(application: RegistrationApplication) -> AdminApplication:
    """Build the administrator-safe signup application projection."""
    return AdminApplication(
        id=application.id,
        user_id=application.user_id,
        full_name=application.user.full_name,
        username=application.user.username,
        email=application.user.email,
        phone_number=application.user.phone_number,
        email_verified=application.email_verified,
        approval_status=application.approval_status,
        submitted_at=application.submitted_at,
        reviewed_by_id=application.reviewed_by_id,
        reviewed_at=application.reviewed_at,
        assigned_role=application.assigned_role.name if application.assigned_role else None,
        rejection_reason=application.rejection_reason,
    )


def _audit_response(event) -> AuditLogResponse:
    """Build an administrator-safe audit projection from stored snapshots."""
    actor = event.actor_user
    return AuditLogResponse(
        id=event.id,
        actor_id=event.actor_id,
        actor_email=event.actor_email or (actor.email if actor else None),
        actor_username=event.actor_username or (actor.username if actor else None),
        action=event.action,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        organization_id=event.organization_id,
        organization_name=event.organization.name if event.organization else None,
        occurred_at=event.occurred_at,
        outcome=event.outcome,
        request_ip=event.request_ip,
        user_agent=event.user_agent,
        details=event.details,
        previous_state=event.previous_state,
        new_state=event.new_state,
    )


def _audit_filter_values(query: AuditQuery) -> dict[str, object]:
    return query.model_dump(exclude_none=True)


def _csv_cell(value: object) -> object:
    """Neutralize spreadsheet formula prefixes in untrusted string fields."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requested user or application was not found")


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc) or "Action conflicts with current account state")


@router.get("/dashboard", response_model=AdminOverview)
def get_dashboard(db: Session = Depends(get_db)) -> AdminOverview:
    """Return live aggregate counts queried from PostgreSQL."""
    return AdminOverview(**dashboard_overview(db))


@router.get("/analytics", response_model=AdminAnalytics)
def get_analytics(period: str = Query(default="30d", pattern="^(7d|30d|90d|all)$"), db: Session = Depends(get_db)) -> AdminAnalytics:
    """Return aggregate-only workspace analytics from existing records."""
    return AdminAnalytics(**admin_analytics(db, period))


@router.get("/storage", response_model=AdminStoragePage)
def get_storage_users(
    search: str | None = Query(default=None, max_length=160),
    organization_id: int | None = Query(default=None, ge=1),
    sort_by: str = Query(default="storage_bytes", pattern="^(storage_bytes|document_count)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> AdminStoragePage:
    """Return paginated recorded storage consumption for registered users."""
    items, total = admin_storage_page(db, search=search, organization_id=organization_id, sort_by=sort_by, limit=limit, offset=offset)
    return AdminStoragePage(items=items, total=total, limit=limit, offset=offset)


@router.get("/storage/users/{user_id}", response_model=AdminStorageDetail)
def get_user_storage_detail(
    user_id: int,
    document_limit: int = Query(default=50, ge=1, le=100),
    document_offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> AdminStorageDetail:
    """Return a bounded storage detail page for one customer account."""
    detail = admin_storage_detail(db, user_id, document_limit=document_limit, document_offset=document_offset)
    if detail is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return AdminStorageDetail(**detail)


@router.get("/users", response_model=list[AdminUser])
def get_users(db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)) -> list[AdminUser]:
    """List registered accounts with their assigned roles and states."""
    return [_user_response(user) for user in list_users(db, limit, offset)]


@router.get("/organizations", response_model=list[OrganizationResponse])
def get_organizations(db: Session = Depends(get_db)) -> list[OrganizationResponse]:
    """List organization boundaries and current membership counts."""
    rows = db.execute(select(Organization, func.count(User.id)).outerjoin(User).group_by(Organization.id).order_by(Organization.name)).all()
    return [OrganizationResponse(id=organization.id, name=organization.name, member_count=count) for organization, count in rows]


@router.post("/organizations", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
def post_organization(payload: OrganizationCreateRequest, actor: User = Depends(get_current_user), db: Session = Depends(get_db)) -> OrganizationResponse:
    """Create a tenant boundary; membership is assigned separately and explicitly."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Organization name cannot be blank.")
    organization = Organization(name=name)
    try:
        db.add(organization)
        db.flush()
        record_audit_event(db, "ORGANIZATION_CREATED", actor=actor, target_user_id=actor.id, resource_type="Organization", resource_id=organization.id, organization_id=organization.id, details={"name": name})
        db.commit()
        db.refresh(organization)
        return OrganizationResponse(id=organization.id, name=organization.name, member_count=0)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An organization with that name already exists.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Organization could not be saved.") from exc


@router.patch("/users/{user_id}/organization", response_model=AdminUser)
def patch_user_organization(user_id: int, payload: OrganizationAssignmentRequest, actor: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AdminUser:
    """Assign/unassign membership while preserving user and document records."""
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    organization = db.get(Organization, payload.organization_id) if payload.organization_id is not None else None
    if payload.organization_id is not None and organization is None:
        raise HTTPException(status_code=404, detail="Organization not found.")
    old_id = user.organization_id
    user.organization_id = payload.organization_id
    user.updated_at = datetime.now(timezone.utc)
    record_audit_event(db, "USER_ORGANIZATION_CHANGED", actor=actor, target_user_id=user.id, resource_type="User", resource_id=user.id, organization_id=user.organization_id or old_id, details={"previous_organization_id": old_id, "new_organization_id": user.organization_id}, previous_state={"organization_id": old_id}, new_state={"organization_id": user.organization_id})
    try:
        db.commit()
        db.refresh(user)
        return _user_response(user)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Organization membership could not be saved.") from exc


@router.get("/applications", response_model=list[AdminApplication])
def get_applications(
    db: Session = Depends(get_db),
    approval_status: str | None = Query(default="PENDING", pattern="^(PENDING|APPROVED|REJECTED)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[AdminApplication]:
    """List pending applications by default, with optional status filter."""
    return [_application_response(item) for item in list_applications(db, approval_status, limit, offset)]


@router.get("/applications/{application_id}", response_model=AdminApplication)
def get_application_detail(application_id: int, db: Session = Depends(get_db)) -> AdminApplication:
    """View the full registration details for one applicant."""
    try:
        return _application_response(get_application(db, application_id))
    except AdminResourceNotFound as exc:
        raise _not_found(exc) from exc


@router.post("/applications/{application_id}/approve", response_model=AdminActionResponse)
def approve(
    application_id: int,
    payload: ApproveApplicationRequest,
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AdminActionResponse:
    """Approve a verified signup, activate it, assign a role, and audit."""
    try:
        application = approve_application(db, application_id, actor.id, payload.role)
    except AdminResourceNotFound as exc:
        raise _not_found(exc) from exc
    except AdminActionConflict as exc:
        raise _conflict(exc) from exc
    try:
        send_application_decision(application.user.email, approved=True)
        notified = True
    except EmailDeliveryError:
        notified = False
    return AdminActionResponse(message="Application approved.", notification_sent=notified)


@router.post("/applications/{application_id}/reject", response_model=AdminActionResponse)
def reject(
    application_id: int,
    payload: RejectApplicationRequest,
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AdminActionResponse:
    """Reject a signup, save the reason/reviewer, and audit the decision."""
    try:
        application = reject_application(db, application_id, actor.id, payload.reason)
    except AdminResourceNotFound as exc:
        raise _not_found(exc) from exc
    except AdminActionConflict as exc:
        raise _conflict(exc) from exc
    try:
        send_application_decision(application.user.email, approved=False, reason=application.rejection_reason)
        notified = True
    except EmailDeliveryError:
        notified = False
    return AdminActionResponse(message="Application rejected.", notification_sent=notified)


@router.patch("/users/{user_id}/role", response_model=AdminUser)
def patch_user_role(
    user_id: int,
    payload: RoleUpdateRequest,
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AdminUser:
    """Assign Owner/Viewer to an eligible account and record the change."""
    try:
        return _user_response(change_user_role(db, user_id, actor.id, payload.role))
    except AdminResourceNotFound as exc:
        raise _not_found(exc) from exc
    except ProtectedAdministrator as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator accounts are protected") from exc
    except AdminActionConflict as exc:
        raise _conflict(exc) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Account role update could not be saved. Check the database connection and retry.") from exc


@router.patch("/users/{user_id}/status", response_model=AdminUser)
def patch_user_status(
    user_id: int,
    payload: AccountStatusUpdateRequest,
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AdminUser:
    """Activate, deactivate, or suspend a user and record the action."""
    try:
        return _user_response(change_user_status(db, user_id, actor.id, payload.status))
    except AdminResourceNotFound as exc:
        raise _not_found(exc) from exc
    except ProtectedAdministrator as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator accounts are protected") from exc
    except AdminActionConflict as exc:
        raise _conflict(exc) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Account status update could not be saved. Check the database connection and retry.") from exc


@router.get("/audit-logs/summary", response_model=AuditSummary)
def get_audit_summary(query: AuditQuery = Depends(), db: Session = Depends(get_db)) -> AuditSummary:
    """Return counts for the same selected period and filters as the audit table."""
    return AuditSummary(**summarize_audit_events(db, **_audit_filter_values(query)))


@router.get("/audit-logs/export.csv")
def export_audit_logs(query: AuditExportQuery = Depends(), db: Session = Depends(get_db)) -> Response:
    """Export bounded, sanitized audit fields as a UTF-8 CSV attachment."""
    filters = query.model_dump(exclude_none=True, exclude={"max_rows"})
    events, _total = list_audit_events(db, limit=query.max_rows, offset=0, sort_order="desc", **filters)
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("id", "occurred_at", "actor_id", "actor_email", "actor_username", "action", "resource_type", "resource_id", "organization_id", "organization_name", "outcome", "request_ip", "user_agent", "details", "previous_state", "new_state"))
    for event in events:
        writer.writerow(tuple(_csv_cell(value) for value in (event.id, event.occurred_at.isoformat(), event.actor_id or "", event.actor_email or (event.actor_user.email if event.actor_user else ""), event.actor_username or (event.actor_user.username if event.actor_user else ""), event.action, event.resource_type or "", event.resource_id or "", event.organization_id or "", event.organization.name if event.organization else "", event.outcome, event.request_ip or "", event.user_agent or "", json.dumps(event.details, ensure_ascii=False, sort_keys=True), json.dumps(event.previous_state, ensure_ascii=False, sort_keys=True) if event.previous_state is not None else "", json.dumps(event.new_state, ensure_ascii=False, sort_keys=True) if event.new_state is not None else "")))
    return Response(content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=vaulttrace-audit-logs.csv", "Cache-Control": "no-store"})


@router.get("/audit-logs/{event_id}", response_model=AuditLogResponse)
def get_audit_log_detail(event_id: int, db: Session = Depends(get_db)) -> AuditLogResponse:
    """Return one audit event to an authenticated Administrator."""
    event = get_audit_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Audit event not found.")
    return _audit_response(event)


@router.get("/audit-logs", response_model=AuditLogPage)
def get_audit_logs(
    query: AuditQuery = Depends(),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
) -> AuditLogPage:
    """List filtered audit records with bounded pagination and explicit sorting."""
    events, total = list_audit_events(db, limit=limit, offset=offset, sort_order=sort_order, **_audit_filter_values(query))
    return AuditLogPage(items=[_audit_response(event) for event in events], total=total, limit=limit, offset=offset)


@router.get("/documents", response_model=list[AdminDocumentResponse])
def get_admin_document_metadata(
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AdminDocumentResponse]:
    """Search document metadata only; administrator APIs never expose file bytes."""
    documents = admin_document_metadata(db, search=search, limit=limit, offset=offset)
    db.add(DocumentActivity(actor_user_id=actor.id, action="ADMIN_DOCUMENT_METADATA_VIEWED", result="SUCCESS", details={"result_count": len(documents)}))
    record_audit_event(db, "ADMIN_DOCUMENT_METADATA_VIEWED", actor=actor, details={"result_count": len(documents)})
    db.commit()
    return [AdminDocumentResponse(
        id=item.id,
        document_name=item.document_name,
        original_filename=item.original_filename,
        owner_id=item.owner_id,
        owner_name=item.owner.full_name,
        owner_username=item.owner.username,
        category=item.category,
        file_extension=item.file_extension,
        mime_type=item.mime_type,
        file_size=item.file_size,
        visibility=item.visibility,
        current_version=item.current_version,
        deleted_at=item.deleted_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    ) for item in documents]


@router.get("/documents/audit", response_model=list[DocumentActivityResponse])
def get_admin_document_audit(
    document_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DocumentActivityResponse]:
    """Review document access and permission events for security investigations."""
    events = admin_document_activity(db, document_id=document_id, limit=limit, offset=offset)
    db.add(DocumentActivity(actor_user_id=actor.id, document_id=document_id, action="ADMIN_DOCUMENT_AUDIT_VIEWED", result="SUCCESS", details={"result_count": len(events)}))
    record_audit_event(db, "ADMIN_DOCUMENT_AUDIT_VIEWED", actor=actor, resource_type="Document" if document_id else None, resource_id=document_id, details={"result_count": len(events)})
    db.commit()
    return [DocumentActivityResponse(
        id=event.id,
        document_id=event.document_id,
        actor_user_id=event.actor_user_id,
        actor_username=event.actor.username,
        action=event.action,
        result=event.result,
        details=event.details,
        created_at=event.created_at,
    ) for event in events]


@router.get("/documents/permissions", response_model=list[AdminDocumentPermissionResponse])
def get_admin_document_permissions(
    document_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AdminDocumentPermissionResponse]:
    """Review current and historical grants without exposing document bytes."""
    permissions = admin_document_permissions(db, document_id=document_id, limit=limit, offset=offset)
    db.add(DocumentActivity(actor_user_id=actor.id, action="ADMIN_DOCUMENT_PERMISSIONS_VIEWED", result="SUCCESS", details={"result_count": len(permissions)}))
    record_audit_event(db, "ADMIN_DOCUMENT_PERMISSIONS_VIEWED", actor=actor, resource_type="Document" if document_id else None, resource_id=document_id, details={"result_count": len(permissions)})
    db.commit()
    return [AdminDocumentPermissionResponse(
        id=permission.id,
        document_id=permission.document_id,
        document_name=permission.document.document_name,
        owner_id=permission.document.owner_id,
        recipient_user_id=permission.granted_to_user_id,
        recipient_username=permission.granted_to.username,
        permission_level=permission.permission_level,
        created_at=permission.created_at,
        expires_at=permission.expires_at,
        revoked_at=permission.revoked_at,
    ) for permission in permissions]


@router.delete("/documents/permissions/{permission_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_admin_document_permission(
    permission_id: int,
    request: Request,
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Revoke a grant by policy without granting the administrator content access."""
    try:
        client_ip = request.client.host if request.client else None
        admin_revoke_permission(db, actor.id, permission_id, request_ip=client_ip, user_agent=request.headers.get("user-agent", "")[:512] or None)
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Active permission was not found.") from exc
