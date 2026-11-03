"""Track user account updates without changing existing account data."""

from alembic import op
import sqlalchemy as sa

revision = "20261104_0006"
down_revision = "20261104_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add a timestamp with a temporary default to backfill existing users."""
    op.add_column(
        "users",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.alter_column("users", "updated_at", server_default=None)


def downgrade() -> None:
    """Remove the added account timestamp column."""
    op.drop_column("users", "updated_at")
