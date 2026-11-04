"""Public document metadata schemas; storage credentials and keys stay private."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class DocumentResponse(BaseModel):
    """Document metadata returned to an authorized owner."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_name: str
    original_filename: str
    owner_id: int
    category: str
    description: str | None
    file_extension: str
    mime_type: str
    file_size: int
    checksum: str | None
    visibility: str
    current_version: int
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SharedDocumentResponse(BaseModel):
    """A shared file plus minimal owner and active-grant details."""

    document: DocumentResponse
    owner_name: str
    owner_username: str
    shared_at: datetime
    permission_level: str
    expires_at: datetime | None


class DocumentSearchResponse(DocumentResponse):
    """Authorized search result with the minimum owner/access context."""

    owner_name: str
    owner_username: str
    access_level: str


class AdminDocumentResponse(BaseModel):
    """Metadata-only administrative projection without storage pointers or content."""

    id: UUID
    document_name: str
    original_filename: str
    owner_id: int
    owner_name: str
    owner_username: str
    category: str
    file_extension: str
    mime_type: str
    file_size: int
    visibility: str
    current_version: int
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AdminDocumentPermissionResponse(BaseModel):
    """Administrator-safe access-grant metadata without file content or keys."""

    id: int
    document_id: UUID
    document_name: str
    owner_id: int
    recipient_user_id: int
    recipient_username: str
    permission_level: str
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None


class SharedByMeResponse(BaseModel):
    """A grant created by the current owner or delegated owner."""

    document_id: UUID
    permission_id: int
    document_name: str
    recipient_user_id: int
    recipient_name: str
    recipient_username: str
    permission_level: str
    shared_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None


class DocumentMetadataUpdate(BaseModel):
    """Editable, non-storage metadata for an authorized Editor or Owner."""

    document_name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=4000)
    visibility: str | None = Field(default=None, pattern="^(PRIVATE|SHARED|RESTRICTED)$")


class DocumentPermissionCreate(BaseModel):
    """Grant a permission to one registered recipient by ID or email."""

    recipient_user_id: int | None = Field(default=None, ge=1)
    recipient_email: EmailStr | None = None
    permission_level: str = Field(pattern="^(READ|EDIT|VIEWER|EDITOR)$")
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def exactly_one_recipient(self) -> "DocumentPermissionCreate":
        if (self.recipient_user_id is None) == (self.recipient_email is None):
            raise ValueError("Provide exactly one of recipient_user_id or recipient_email")
        return self


class DocumentPermissionUpdate(BaseModel):
    """Change a permission level and/or its expiration."""

    permission_level: str | None = Field(default=None, pattern="^(READ|EDIT|VIEWER|EDITOR)$")
    expires_at: datetime | None = None


class DocumentPermissionResponse(BaseModel):
    """Safe access-grant details returned to the document owner/delegate."""

    id: int
    granted_to_user_id: int
    recipient_username: str
    recipient_name: str
    recipient_email: EmailStr
    permission_level: str
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None


class EligibleShareUserResponse(BaseModel):
    """A verified, active user in the document owner's organization."""

    id: int
    full_name: str
    username: str
    email: EmailStr


class DocumentVersionResponse(BaseModel):
    """Safe metadata for one immutable document revision."""

    id: UUID
    version_number: int
    original_filename: str
    file_extension: str
    mime_type: str
    file_size: int
    checksum: str | None
    created_by_user_id: int
    created_by_full_name: str
    created_at: datetime


class DocumentActivityResponse(BaseModel):
    """Document event without internal storage pointers or request secrets."""

    id: UUID
    document_id: UUID | None
    actor_user_id: int
    actor_username: str
    action: str
    result: str
    details: dict[str, object]
    created_at: datetime
