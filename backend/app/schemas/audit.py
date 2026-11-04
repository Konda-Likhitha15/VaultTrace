"""Safe administrator-facing audit event projections and filters."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AuditLogResponse(BaseModel):
    """Audit record without credentials, storage pointers, or file contents."""

    id: int
    actor_id: int | None
    actor_email: str | None
    actor_username: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    organization_id: int | None
    organization_name: str | None
    occurred_at: datetime
    outcome: Literal["SUCCESS", "FAILURE"]
    request_ip: str | None
    user_agent: str | None
    details: dict[str, object]
    previous_state: dict[str, object] | None
    new_state: dict[str, object] | None


class AuditLogPage(BaseModel):
    """One bounded, sorted page and total count."""

    items: list[AuditLogResponse]
    total: int
    limit: int
    offset: int


class AuditSummary(BaseModel):
    """Period-filtered dashboard totals."""

    total_events: int
    successful_operations: int
    failed_operations: int
    active_users: int


class AuditQuery(BaseModel):
    """Validated filters shared by admin endpoints."""

    user_id: int | None = Field(default=None, ge=1)
    resource_id: str | None = Field(default=None, min_length=1, max_length=64)
    action: str | None = Field(default=None, min_length=1, max_length=64)
    search: str | None = Field(default=None, max_length=100)
    outcome: Literal["SUCCESS", "FAILURE"] | None = None
    organization_id: int | None = Field(default=None, ge=1)
    date_from: datetime | None = None
    date_to: datetime | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> "AuditQuery":
        start = _as_utc(self.date_from) if self.date_from is not None else None
        end = _as_utc(self.date_to) if self.date_to is not None else None
        if start is not None and end is not None and start > end:
            raise ValueError("date_from must be before or equal to date_to")
        return self


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class AuditExportQuery(AuditQuery):
    """CSV export accepts at most 10,000 matching records."""

    max_rows: int = Field(default=5000, ge=1, le=10000)
