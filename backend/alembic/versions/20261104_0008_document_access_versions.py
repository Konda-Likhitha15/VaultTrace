"""Add document versions, explicit sharing permissions, and activity audit."""

from alembic import op
import sqlalchemy as sa

revision = "20261104_0008"
down_revision = "20261104_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Additive schema and backfill version one for existing document rows."""
    op.add_column("documents", sa.Column("visibility", sa.String(length=16), nullable=False, server_default="PRIVATE"))
    op.add_column("documents", sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("documents", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("ck_documents_visibility", "documents", "visibility IN ('PRIVATE', 'SHARED', 'RESTRICTED')")
    op.create_check_constraint("ck_documents_current_version_positive", "documents", "current_version >= 1")
    op.create_index("ix_documents_deleted_at", "documents", ["deleted_at"])

    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("storage_provider", sa.String(length=16), nullable=False),
        sa.Column("storage_bucket", sa.String(length=100), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_extension", sa.String(length=16), nullable=False),
        sa.Column("mime_type", sa.String(length=127), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("version_number >= 1", name="ck_document_versions_number_positive"),
        sa.CheckConstraint("file_size > 0", name="ck_document_versions_size_positive"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "version_number", name="uq_document_versions_number"),
        sa.UniqueConstraint("storage_key", name="uq_document_versions_storage_key"),
    )
    op.create_index("ix_document_versions_document_created", "document_versions", ["document_id", "created_at"])
    op.execute(sa.text("""
        INSERT INTO document_versions (
            id, document_id, version_number, storage_provider, storage_bucket, storage_key,
            original_filename, file_extension, mime_type, file_size, checksum,
            created_by_user_id, created_at
        )
        SELECT gen_random_uuid(), id, 1, storage_provider, storage_bucket, storage_key,
               original_filename, file_extension, mime_type, file_size, checksum,
               owner_id, created_at
        FROM documents
    """))

    op.create_table(
        "document_permissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("granted_by_user_id", sa.Integer(), nullable=False),
        sa.Column("granted_to_user_id", sa.Integer(), nullable=False),
        sa.Column("permission_level", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("permission_level IN ('VIEWER', 'EDITOR', 'OWNER')", name="ck_document_permissions_level"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["granted_to_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "granted_to_user_id", name="uq_document_permissions_recipient"),
    )
    op.create_index("ix_document_permissions_recipient_active", "document_permissions", ["granted_to_user_id", "revoked_at", "expires_at"])

    op.create_table(
        "document_activities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=48), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False, server_default="SUCCESS"),
        sa.Column("request_ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("result IN ('SUCCESS', 'DENIED')", name="ck_document_activities_result"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_activities_action", "document_activities", ["action"])
    op.create_index("ix_document_activities_document_created", "document_activities", ["document_id", "created_at"])
    op.create_index("ix_document_activities_actor_created", "document_activities", ["actor_user_id", "created_at"])


def downgrade() -> None:
    """Remove added collaboration tables and columns without deleting document rows."""
    op.drop_index("ix_document_activities_actor_created", table_name="document_activities")
    op.drop_index("ix_document_activities_document_created", table_name="document_activities")
    op.drop_index("ix_document_activities_action", table_name="document_activities")
    op.drop_table("document_activities")
    op.drop_index("ix_document_permissions_recipient_active", table_name="document_permissions")
    op.drop_table("document_permissions")
    op.drop_index("ix_document_versions_document_created", table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_index("ix_documents_deleted_at", table_name="documents")
    op.drop_constraint("ck_documents_current_version_positive", "documents", type_="check")
    op.drop_constraint("ck_documents_visibility", "documents", type_="check")
    op.drop_column("documents", "deleted_at")
    op.drop_column("documents", "current_version")
    op.drop_column("documents", "visibility")
