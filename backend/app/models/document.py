"""Document metadata stored in PostgreSQL; file bytes remain in private object storage."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Document(Base):
    """Metadata and private-storage pointer for an owned document."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("file_size > 0", name="ck_documents_file_size_positive"),
        CheckConstraint("storage_provider IN ('local', 'supabase')", name="ck_documents_storage_provider"),
        CheckConstraint("visibility IN ('PRIVATE', 'SHARED', 'RESTRICTED')", name="ck_documents_visibility"),
        CheckConstraint("current_version >= 1", name="ck_documents_current_version_positive"),
        CheckConstraint("length(trim(document_name)) > 0", name="ck_documents_name_nonempty"),
        CheckConstraint("length(trim(category)) > 0", name="ck_documents_category_nonempty"),
        UniqueConstraint("storage_key", name="uq_documents_storage_key"),
        Index("ix_documents_owner_created", "owner_id", "created_at"),
        Index("ix_documents_owner_category", "owner_id", "category"),
        Index("ix_documents_document_name", "document_name"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    storage_provider: Mapped[str] = mapped_column(String(16), nullable=False, default="supabase")
    document_name: Mapped[str] = mapped_column(String(200), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_extension: Mapped[str] = mapped_column(String(16), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_bucket: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="PRIVATE", server_default="PRIVATE")
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    owner: Mapped["User"] = relationship(back_populates="documents")
    versions: Mapped[list["DocumentVersion"]] = relationship(back_populates="document", order_by="DocumentVersion.version_number", passive_deletes=True)
    permissions: Mapped[list["DocumentPermission"]] = relationship(back_populates="document", passive_deletes=True)
    activities: Mapped[list["DocumentActivity"]] = relationship(back_populates="document", passive_deletes=True)


class DocumentVersion(Base):
    """Immutable metadata and private storage pointer for a document revision."""

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_versions_number"),
        UniqueConstraint("storage_key", name="uq_document_versions_storage_key"),
        CheckConstraint("version_number >= 1", name="ck_document_versions_number_positive"),
        CheckConstraint("file_size > 0", name="ck_document_versions_size_positive"),
        Index("ix_document_versions_document_created", "document_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_bucket: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(16), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document: Mapped[Document] = relationship(back_populates="versions")


class DocumentPermission(Base):
    """A revocable, optionally time-limited grant for a registered user."""

    __tablename__ = "document_permissions"
    __table_args__ = (
        UniqueConstraint("document_id", "granted_to_user_id", name="uq_document_permissions_recipient"),
        CheckConstraint("permission_level IN ('VIEWER', 'EDITOR', 'OWNER')", name="ck_document_permissions_level"),
        Index("ix_document_permissions_recipient_active", "granted_to_user_id", "revoked_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    granted_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    granted_to_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    permission_level: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    document: Mapped[Document] = relationship(back_populates="permissions")
    granted_by: Mapped["User"] = relationship(foreign_keys=[granted_by_user_id])
    granted_to: Mapped["User"] = relationship(foreign_keys=[granted_to_user_id])
    revoked_by: Mapped["User | None"] = relationship(foreign_keys=[revoked_by_user_id])


class DocumentActivity(Base):
    """Append-only audit event for document access and permission changes."""

    __tablename__ = "document_activities"
    __table_args__ = (
        CheckConstraint("result IN ('SUCCESS', 'DENIED')", name="ck_document_activities_result"),
        Index("ix_document_activities_document_created", "document_id", "created_at"),
        Index("ix_document_activities_actor_created", "actor_user_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    action: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    result: Mapped[str] = mapped_column(String(16), nullable=False, default="SUCCESS")
    request_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document: Mapped[Document | None] = relationship(back_populates="activities")
    actor: Mapped["User"] = relationship()
