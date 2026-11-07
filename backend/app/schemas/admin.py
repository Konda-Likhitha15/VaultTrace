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
    total_documents: int = 0
    active_document_shares: int = 0


class AdminAnalyticsPoint(BaseModel):
    period: str
    count: int
    bytes: int = 0


class AdminAnalyticsBreakdown(BaseModel):
    name: str
    count: int
    bytes: int = 0


class AdminAnalytics(BaseModel):
    period: Literal["7d", "30d", "90d", "all"]
    total_registered_users: int
    total_active_users: int
    total_inactive_users: int
    pending_applications: int
    total_documents: int
    total_storage_bytes: int
    total_shared_documents: int
    storage_quota_bytes: int | None = None
    registration_trends: list[AdminAnalyticsPoint]
    upload_trends: list[AdminAnalyticsPoint]
    user_status: list[AdminAnalyticsBreakdown]
    file_types: list[AdminAnalyticsBreakdown]
    storage_by_organization: list[AdminAnalyticsBreakdown]
    storage_by_user: list[AdminAnalyticsBreakdown]
    sharing_activity: list[AdminAnalyticsPoint]
    storage_growth_available: bool = False
    storage_growth_note: str


class AdminStorageUser(BaseModel):
    user_id: int
    username: str
    full_name: str
    email: EmailStr
    organization_id: int | None
    organization_name: str | None
    document_count: int
    storage_bytes: int
    quota_bytes: int | None = None
    largest_file_bytes: int | None
    last_upload_at: datetime | None
    account_status: str


class AdminStoragePage(BaseModel):
    items: list[AdminStorageUser]
    total: int
    limit: int
    offset: int


class AdminStorageDocument(BaseModel):
    document_id: str
    document_name: str
    file_extension: str
    current_file_bytes: int
    total_stored_bytes: int
    version_count: int
    uploaded_at: datetime
    deleted_at: datetime | None


class AdminStorageActivity(BaseModel):
    action: str
    result: str
    created_at: datetime
    actor_username: str


class AdminStorageDetail(BaseModel):
    user: AdminStorageUser
    file_types: list[AdminAnalyticsBreakdown]
    documents: list[AdminStorageDocument]
    document_total: int
    document_limit: int
    document_offset: int
    recent_activity: list[AdminStorageActivity]
    historical_storage_available: bool = False
    historical_storage_note: str


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
