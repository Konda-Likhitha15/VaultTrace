"""Database-backed administrator storage and analytics queries."""

from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Document,
    DocumentActivity,
    DocumentPermission,
    DocumentVersion,
    Organization,
    RegistrationApplication,
    User,
)

AnalyticsPeriod = Literal["7d", "30d", "90d", "all"]


def period_start(period: AnalyticsPeriod) -> datetime | None:
    days = {"7d": 7, "30d": 30, "90d": 90}.get(period)
    return datetime.now(timezone.utc) - timedelta(days=days) if days else None


def document_storage_rows():
    """Return one row per document with recorded bytes for all retained blobs.

    The documents row points at the current file. Previous versions remain in
    document_versions. A backfilled/current version row is excluded from the
    extra byte sum to avoid counting the current object twice.
    """
    versions = select(
        DocumentVersion.document_id.label("document_id"),
        func.sum(case((DocumentVersion.version_number < Document.current_version, DocumentVersion.file_size), else_=0)).label("prior_bytes"),
        func.max(case((DocumentVersion.version_number < Document.current_version, DocumentVersion.file_size), else_=None)).label("largest_prior_bytes"),
        func.sum(case((DocumentVersion.version_number < Document.current_version, 1), else_=0)).label("prior_version_count"),
        func.max(DocumentVersion.created_at).label("latest_version_at"),
    ).join(Document, Document.id == DocumentVersion.document_id).group_by(DocumentVersion.document_id).subquery()
    return select(
        Document.id.label("document_id"),
        Document.owner_id.label("owner_id"),
        Document.document_name.label("document_name"),
        Document.file_extension.label("file_extension"),
        Document.file_size.label("current_file_bytes"),
        (Document.file_size + func.coalesce(versions.c.prior_bytes, 0)).label("storage_bytes"),
        (func.coalesce(versions.c.prior_version_count, 0) + 1).label("version_count"),
        case((versions.c.latest_version_at > Document.created_at, versions.c.latest_version_at), else_=Document.created_at).label("uploaded_at"),
        case((versions.c.largest_prior_bytes > Document.file_size, versions.c.largest_prior_bytes), else_=Document.file_size).label("largest_file_bytes"),
        Document.created_at.label("created_at"),
        Document.deleted_at.label("deleted_at"),
    ).outerjoin(versions, versions.c.document_id == Document.id).subquery()


def user_storage_rows():
    docs = document_storage_rows()
    return select(
        User.id.label("user_id"),
        func.count(docs.c.document_id).label("document_count"),
        func.coalesce(func.sum(docs.c.storage_bytes), 0).label("storage_bytes"),
        func.max(docs.c.largest_file_bytes).label("largest_file_bytes"),
        func.max(docs.c.uploaded_at).label("last_upload_at"),
    ).outerjoin(docs, docs.c.owner_id == User.id).group_by(User.id).subquery()


def recorded_storage_bytes(db: Session, user_id: int) -> int:
    """Return current and retained-version file bytes from DB metadata."""
    stats = user_storage_rows()
    return int(db.scalar(select(stats.c.storage_bytes).where(stats.c.user_id == user_id)) or 0)


def _period_columns(column, period: AnalyticsPeriod):
    if period in {"7d", "30d"}:
        return (func.date(column),)
    return (func.extract("year", column), func.extract("month", column))


def _time_series(db: Session, model, date_column, period: AnalyticsPeriod, start: datetime | None, *, action_filter=None) -> list[dict[str, object]]:
    buckets = _period_columns(date_column, period)
    query = select(*buckets, func.count()).select_from(model)
    if start is not None:
        query = query.where(date_column >= start)
    if action_filter is not None:
        query = query.where(action_filter)
    rows = db.execute(query.group_by(*buckets).order_by(*buckets)).all()
    if period in {"7d", "30d"}:
        return [{"period": str(row[0])[:10], "count": int(row[1]), "bytes": 0} for row in rows]
    return [{"period": f"{int(row[0]):04d}-{int(row[1]):02d}", "count": int(row[2]), "bytes": 0} for row in rows]


def admin_analytics(db: Session, period: AnalyticsPeriod) -> dict[str, object]:
    """Aggregate admin dashboard charts from existing records in SQL."""
    start = period_start(period)
    docs = document_storage_rows()
    user_docs = user_storage_rows()
    total_users = int(db.scalar(select(func.count(User.id))) or 0)
    active_users = int(db.scalar(select(func.count(User.id)).where(User.is_active.is_(True), User.account_status == "ACTIVE")) or 0)
    pending = int(db.scalar(select(func.count(RegistrationApplication.id)).where(RegistrationApplication.approval_status == "PENDING")) or 0)
    total_documents = int(db.scalar(select(func.count(Document.id))) or 0)
    total_storage = int(db.scalar(select(func.coalesce(func.sum(docs.c.storage_bytes), 0))) or 0)
    now = datetime.now(timezone.utc)
    active_permissions = DocumentPermission.revoked_at.is_(None) & (DocumentPermission.expires_at.is_(None) | (DocumentPermission.expires_at > now))
    total_shared = int(db.scalar(select(func.count(func.distinct(DocumentPermission.document_id))).join(Document, Document.id == DocumentPermission.document_id).where(Document.deleted_at.is_(None), active_permissions)) or 0)

    file_rows = db.execute(select(Document.file_extension, func.count(Document.id), func.coalesce(func.sum(docs.c.storage_bytes), 0))
        .join(docs, docs.c.document_id == Document.id).where(Document.deleted_at.is_(None))
        .group_by(Document.file_extension).order_by(func.count(Document.id).desc())).all()
    status_rows = [
        {"name": "Active", "count": active_users, "bytes": 0},
        {"name": "Inactive", "count": max(0, total_users - active_users), "bytes": 0},
    ]
    organization_rows = db.execute(select(Organization.name, func.count(user_docs.c.user_id), func.coalesce(func.sum(user_docs.c.storage_bytes), 0))
        .join(User, User.organization_id == Organization.id).join(user_docs, user_docs.c.user_id == User.id)
        .group_by(Organization.id, Organization.name).order_by(func.sum(user_docs.c.storage_bytes).desc())).all()
    unassigned = db.execute(select(func.count(user_docs.c.user_id), func.coalesce(func.sum(user_docs.c.storage_bytes), 0))
        .join(User, User.id == user_docs.c.user_id).where(User.organization_id.is_(None))).one()
    organization_data = [{"name": row[0], "count": int(row[1]), "bytes": int(row[2])} for row in organization_rows]
    if int(unassigned[0] or 0):
        organization_data.append({"name": "Unassigned", "count": int(unassigned[0]), "bytes": int(unassigned[1])})

    user_rows = db.execute(select(User.username, user_docs.c.document_count, user_docs.c.storage_bytes)
        .join(user_docs, user_docs.c.user_id == User.id).order_by(user_docs.c.storage_bytes.desc(), User.id).limit(10)).all()
    share_buckets = _period_columns(DocumentPermission.created_at, period)
    share_query = select(*share_buckets, func.count(DocumentPermission.id)).where(
        *([DocumentPermission.created_at >= start] if start is not None else [])
    ).group_by(*share_buckets).order_by(*share_buckets)
    share_rows = db.execute(share_query).all()
    if period in {"7d", "30d"}:
        share_data = [{"period": str(row[0])[:10], "count": int(row[1]), "bytes": 0} for row in share_rows]
    else:
        share_data = [{"period": f"{int(row[0]):04d}-{int(row[1]):02d}", "count": int(row[2]), "bytes": 0} for row in share_rows]

    return {
        "period": period,
        "total_registered_users": total_users,
        "total_active_users": active_users,
        "total_inactive_users": max(0, total_users - active_users),
        "pending_applications": pending,
        "total_documents": total_documents,
        "total_storage_bytes": total_storage,
        "total_shared_documents": total_shared,
        "storage_quota_bytes": None,
        "registration_trends": _time_series(db, User, User.created_at, period, start),
        "upload_trends": _time_series(db, Document, Document.created_at, period, start),
        "user_status": status_rows,
        "file_types": [{"name": str(row[0]).upper(), "count": int(row[1]), "bytes": int(row[2])} for row in file_rows],
        "storage_by_organization": organization_data,
        "storage_by_user": [{"name": row[0], "count": int(row[1]), "bytes": int(row[2])} for row in user_rows],
        "sharing_activity": share_data,
        "storage_growth_available": False,
        "storage_growth_note": "Historical storage snapshots are not stored. Current file sizes cannot reconstruct past storage after document versions or deletions.",
    }


def admin_storage_page(db: Session, *, search: str | None, organization_id: int | None, sort_by: str, limit: int, offset: int) -> tuple[list[dict[str, object]], int]:
    """Return a filtered, paginated per-user storage report."""
    stats = user_storage_rows()
    criteria = []
    if organization_id is not None:
        criteria.append(User.organization_id == organization_id)
    if search and search.strip():
        term = f"%{search.strip()[:160]}%"
        criteria.append(or_(User.username.ilike(term), User.email.ilike(term), User.full_name.ilike(term)))
    total = int(db.scalar(select(func.count(User.id)).where(*criteria)) or 0)
    storage_expr = func.coalesce(stats.c.storage_bytes, 0)
    document_expr = func.coalesce(stats.c.document_count, 0)
    order_expr = document_expr if sort_by == "document_count" else storage_expr
    rows = db.execute(select(
        User.id, User.username, User.full_name, User.email, User.organization_id,
        Organization.name, document_expr, storage_expr, stats.c.largest_file_bytes,
        stats.c.last_upload_at, User.account_status,
    ).outerjoin(Organization, Organization.id == User.organization_id)
        .outerjoin(stats, stats.c.user_id == User.id).where(*criteria)
        .order_by(order_expr.desc(), User.id.asc()).limit(limit).offset(offset)).all()
    items = [{
        "user_id": int(row[0]), "username": row[1], "full_name": row[2], "email": row[3],
        "organization_id": row[4], "organization_name": row[5], "document_count": int(row[6] or 0),
        "storage_bytes": int(row[7] or 0), "quota_bytes": None,
        "largest_file_bytes": int(row[8]) if row[8] is not None else None,
        "last_upload_at": row[9], "account_status": row[10],
    } for row in rows]
    return items, total


def admin_storage_detail(db: Session, user_id: int, *, document_limit: int, document_offset: int) -> dict[str, object] | None:
    """Build a bounded per-customer storage detail view."""
    user = db.get(User, user_id)
    if user is None:
        return None
    docs = document_storage_rows()
    stats = user_storage_rows()
    row = db.execute(select(
        func.coalesce(stats.c.document_count, 0), func.coalesce(stats.c.storage_bytes, 0),
        stats.c.largest_file_bytes, stats.c.last_upload_at,
    ).join(User, User.id == stats.c.user_id).where(User.id == user_id)).one_or_none()
    document_count = int(row[0] or 0) if row else 0
    storage_bytes = int(row[1] or 0) if row else 0
    file_rows = db.execute(select(Document.file_extension, func.count(Document.id), func.coalesce(func.sum(docs.c.storage_bytes), 0))
        .join(docs, docs.c.document_id == Document.id).where(Document.owner_id == user_id)
        .group_by(Document.file_extension).order_by(func.sum(docs.c.storage_bytes).desc())).all()
    total = int(db.scalar(select(func.count(Document.id)).where(Document.owner_id == user_id)) or 0)
    document_rows = db.execute(select(docs).where(docs.c.owner_id == user_id)
        .order_by(docs.c.uploaded_at.desc(), docs.c.document_id).limit(document_limit).offset(document_offset)).all()
    activity_rows = db.execute(select(DocumentActivity.action, DocumentActivity.result, DocumentActivity.created_at, User.username)
        .join(Document, Document.id == DocumentActivity.document_id)
        .join(User, User.id == DocumentActivity.actor_user_id)
        .where(Document.owner_id == user_id, DocumentActivity.action.in_(("DOCUMENT_UPLOADED", "DOCUMENT_VERSION_CREATED")))
        .order_by(DocumentActivity.created_at.desc()).limit(20)).all()
    organization = db.get(Organization, user.organization_id) if user.organization_id is not None else None
    return {
        "user": {
            "user_id": user.id, "username": user.username, "full_name": user.full_name, "email": user.email,
            "organization_id": user.organization_id, "organization_name": organization.name if organization else None,
            "document_count": document_count, "storage_bytes": storage_bytes, "quota_bytes": None,
            "largest_file_bytes": int(row[2]) if row and row[2] is not None else None,
            "last_upload_at": row[3] if row else None, "account_status": user.account_status,
        },
        "file_types": [{"name": str(item[0]).upper(), "count": int(item[1]), "bytes": int(item[2])} for item in file_rows],
        "documents": [{
            "document_id": str(item.document_id), "document_name": item.document_name,
            "file_extension": item.file_extension, "current_file_bytes": int(item.current_file_bytes),
            "total_stored_bytes": int(item.storage_bytes), "version_count": int(item.version_count),
            "uploaded_at": item.uploaded_at, "deleted_at": item.deleted_at,
        } for item in document_rows],
        "document_total": total, "document_limit": document_limit, "document_offset": document_offset,
        "recent_activity": [{"action": item[0], "result": item[1], "created_at": item[2], "actor_username": item[3]} for item in activity_rows],
        "historical_storage_available": False,
        "historical_storage_note": "No storage snapshots exist in the current schema; historical usage cannot be reconstructed accurately.",
    }
