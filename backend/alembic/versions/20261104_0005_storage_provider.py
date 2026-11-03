"""Record which backend storage provider owns each existing document object."""

from alembic import op
import sqlalchemy as sa

revision = "20261104_0005"
down_revision = "20261103_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Preserve existing Commit 2 objects as Supabase-backed records."""
    op.add_column(
        "documents",
        sa.Column("storage_provider", sa.String(length=16), nullable=False, server_default="supabase"),
    )
    op.create_check_constraint(
        "ck_documents_storage_provider",
        "documents",
        "storage_provider IN ('local', 'supabase')",
    )
    op.alter_column("documents", "storage_provider", server_default=None)


def downgrade() -> None:
    """Remove provider labels without dropping document metadata or objects."""
    op.drop_constraint("ck_documents_storage_provider", "documents", type_="check")
    op.drop_column("documents", "storage_provider")
