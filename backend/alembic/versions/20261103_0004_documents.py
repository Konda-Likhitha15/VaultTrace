"""Add document metadata without storing document bytes in PostgreSQL."""

from alembic import op
import sqlalchemy as sa

revision = "20261103_0004"
down_revision = "20261103_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the document metadata table and its owner/search indexes."""
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_name", sa.String(length=200), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("file_extension", sa.String(length=16), nullable=False),
        sa.Column("mime_type", sa.String(length=127), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("storage_bucket", sa.String(length=100), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("file_size > 0", name="ck_documents_file_size_positive"),
        sa.CheckConstraint("length(trim(document_name)) > 0", name="ck_documents_name_nonempty"),
        sa.CheckConstraint("length(trim(category)) > 0", name="ck_documents_category_nonempty"),
        sa.UniqueConstraint("storage_key", name="uq_documents_storage_key"),
    )
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"])
    op.create_index("ix_documents_owner_created", "documents", ["owner_id", "created_at"])
    op.create_index("ix_documents_owner_category", "documents", ["owner_id", "category"])
    op.create_index("ix_documents_document_name", "documents", ["document_name"])


def downgrade() -> None:
    """Drop only the Commit 2 document metadata table and its indexes."""
    op.drop_index("ix_documents_document_name", table_name="documents")
    op.drop_index("ix_documents_owner_category", table_name="documents")
    op.drop_index("ix_documents_owner_created", table_name="documents")
    op.drop_index("ix_documents_owner_id", table_name="documents")
    op.drop_table("documents")
