"""Centralized, privacy-filtered audit event writes and administrator queries."""

import ipaddress
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import AuditLog, User

_SENSITIVE_KEY = re.compile(r"password|token|otp|secret|credential|authorization|storage.?key|signed.?url|file.?url|document.?content", re.I)


def _safe_value(value: Any, depth: int = 0) -> Any:
    """Bound structured metadata to JSON-safe, non-secret primitives."""
    if depth > 4:
        return "[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (datetime, UUID)):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    if isinstance(value, str):
        return "".join(char for char in value[:512] if char >= " " or char in "\t\n")
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in list(value.items())[:50]:
            safe_key = str(key)[:64]
            if not _SENSITIVE_KEY.search(safe_key):
                result[safe_key] = _safe_value(item, depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, depth + 1) for item in value[:50]]
    return str(value)[:256]


def request_context(request: Any | None) -> tuple[str | None, str | None]:
    """Return bounded IP and user-agent values without trusting proxy headers."""
    if request is None:
        return None, None
    client = getattr(request, "client", None)
    candidate = getattr(client, "host", None)
    safe_ip = _safe_ip(candidate)
    headers = getattr(request, "headers", {})
    agent = str(headers.get("user-agent", ""))[:512] or None
    agent = re.sub(r"(?i)(bearer\s+)[^\s,;]+", r"\1[redacted]", agent) if agent else None
    agent = re.sub(r"(?i)(password|token|otp|secret)=([^\s;&]+)", r"\1=[redacted]", agent) if agent else None
    return safe_ip, agent


def _safe_ip(value: str | None) -> str | None:
    try:
        return str(ipaddress.ip_address(value)) if value else None
    except ValueError:
        return None


def record_audit_event(
    db: Session,
    action: str,
    *,
    actor: User | None = None,
    actor_id: int | None = None,
    actor_email: str | None = None,
    actor_username: str | None = None,
    target_user_id: int | None = None,
    resource_type: str | None = None,
    resource_id: str | UUID | int | None = None,
    organization_id: int | None = None,
    outcome: str = "SUCCESS",
    request: Any | None = None,
    request_ip: str | None = None,
    user_agent: str | None = None,
    details: dict[str, Any] | None = None,
    previous_state: dict[str, Any] | None = None,
    new_state: dict[str, Any] | None = None,
) -> AuditLog:
    """Add a sanitized event to the caller's transaction; the caller commits once."""
    if outcome not in {"SUCCESS", "FAILURE"}:
        raise ValueError("Audit outcome must be SUCCESS or FAILURE.")
    ip, request_agent = request_context(request)
    event = AuditLog(
        actor_id=actor.id if actor is not None else actor_id,
        target_user_id=target_user_id,
        actor_email=(actor.email if actor is not None else actor_email)[:320] if (actor.email if actor is not None else actor_email) else None,
        actor_username=(actor.username if actor is not None else actor_username)[:32] if (actor.username if actor is not None else actor_username) else None,
        action=action[:64],
        resource_type=resource_type[:48] if resource_type else None,
        resource_id=str(resource_id)[:64] if resource_id is not None else None,
        organization_id=organization_id if organization_id is not None else (actor.organization_id if actor else None),
        outcome=outcome,
        request_ip=ip or _safe_ip(request_ip),
        user_agent=(request_agent or user_agent or "")[:512] or None,
        details=_safe_value(details or {}),
        previous_state=_safe_value(previous_state) if previous_state is not None else None,
        new_state=_safe_value(new_state) if new_state is not None else None,
    )
    db.add(event)
    return event


def audit_filters(
    *, user_id: int | None = None, resource_id: str | None = None,
    action: str | None = None, outcome: str | None = None, search: str | None = None,
    organization_id: int | None = None, date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[Any]:
    """Build validated database predicates shared by pages, summary, and export."""
    criteria: list[Any] = []
    if user_id is not None:
        criteria.append(AuditLog.actor_id == user_id)
    if resource_id:
        criteria.append(AuditLog.resource_id == resource_id.strip())
    if action:
        criteria.append(AuditLog.action == action)
    if search and search.strip():
        term = f"%{search.strip()[:100]}%"
        criteria.append(or_(AuditLog.action.ilike(term), AuditLog.resource_id.ilike(term), AuditLog.actor_email.ilike(term), AuditLog.actor_username.ilike(term)))
    if outcome:
        criteria.append(AuditLog.outcome == outcome)
    if organization_id is not None:
        criteria.append(AuditLog.organization_id == organization_id)
    if date_from is not None:
        criteria.append(AuditLog.occurred_at >= _aware(date_from))
    if date_to is not None:
        criteria.append(AuditLog.occurred_at <= _aware(date_to))
    return criteria


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def list_audit_events(db: Session, *, limit: int, offset: int, sort_order: str = "desc", **filters: Any) -> tuple[list[AuditLog], int]:
    criteria = audit_filters(**filters)
    query = select(AuditLog).options(joinedload(AuditLog.actor_user), joinedload(AuditLog.organization)).where(*criteria)
    total = int(db.scalar(select(func.count(AuditLog.id)).where(*criteria)) or 0)
    ordering = AuditLog.occurred_at.asc() if sort_order == "asc" else AuditLog.occurred_at.desc()
    rows = db.scalars(query.order_by(ordering, AuditLog.id.desc()).limit(limit).offset(offset)).unique().all()
    return list(rows), total


def get_audit_event(db: Session, event_id: int) -> AuditLog | None:
    return db.scalar(select(AuditLog).options(joinedload(AuditLog.actor_user), joinedload(AuditLog.organization)).where(AuditLog.id == event_id))


def summarize_audit_events(db: Session, **filters: Any) -> dict[str, int]:
    criteria = audit_filters(**filters)
    total = int(db.scalar(select(func.count(AuditLog.id)).where(*criteria)) or 0)
    successful = int(db.scalar(select(func.count(AuditLog.id)).where(*criteria, AuditLog.outcome == "SUCCESS")) or 0)
    failed = int(db.scalar(select(func.count(AuditLog.id)).where(*criteria, AuditLog.outcome == "FAILURE")) or 0)
    active = int(db.scalar(select(func.count(func.distinct(AuditLog.actor_id))).where(*criteria, AuditLog.actor_id.is_not(None))) or 0)
    return {"total_events": total, "successful_operations": successful, "failed_operations": failed, "active_users": active}
