"""Administrator dashboard, application, role, and account schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class AdminUser(BaseModel):
    """Safe user fields visible to administrators."""

    id: int
    full_name: str
    username: str
    email: EmailStr
    phone_number: str | None
    role: str
    email_verified: bool
    account_status: str
    registration_date: datetime
    updated_at: datetime
    organization_id: int | None = None


class AdminApplication(BaseModel):
    """Application details and current review state."""

    id: int
    user_id: int
    full_name: str
    username: str
    email: EmailStr
    phone_number: str | None
    email_verified: bool
    approval_status: str
    submitted_at: datetime
    reviewed_by_id: int | None
    reviewed_at: datetime | None
    assigned_role: str | None
    rejection_reason: str | None


class AdminOverview(BaseModel):
    """PostgreSQL-backed overview counts."""

    total_registered_users: int
    total_active_users: int
    total_pending_applications: int
    total_approved_users: int
    total_rejected_applications: int
    total_owners: int
    total_viewers: int


class ApproveApplicationRequest(BaseModel):
    """Administrator-selected non-privileged account role."""

    role: Literal["Owner", "Viewer"]


class RejectApplicationRequest(BaseModel):
    """Reason recorded when denying an application."""

    reason: str = Field(min_length=1, max_length=1000)


class RoleUpdateRequest(BaseModel):
    """Allowed target roles; Administrator cannot be assigned here."""

    role: Literal["Owner", "Viewer"]


class AccountStatusUpdateRequest(BaseModel):
    """Administrator-controlled account state."""

    status: Literal["ACTIVE", "INACTIVE", "SUSPENDED"]


class AdminActionResponse(BaseModel):
    """Result of an administrative decision and notification attempt."""

    message: str
    notification_sent: bool | None = None


class OrganizationCreateRequest(BaseModel):
    """Create an organization for administrator-controlled user assignment."""

    name: str = Field(min_length=1, max_length=160)


class OrganizationResponse(BaseModel):
    """Organization identifier exposed to administrators."""

    id: int
    name: str
    member_count: int


class OrganizationAssignmentRequest(BaseModel):
    """Assign or unassign a user from an organization."""

    organization_id: int | None = Field(default=None, ge=1)


class OrganizationUserResponse(BaseModel):
    """Minimal registered-user search result within a tenant."""

    id: int
    full_name: str
    username: str
    email: EmailStr
