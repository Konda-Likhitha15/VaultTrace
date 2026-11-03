"""Provide the database default required for new and existing user inserts."""

from alembic import op
import sqlalchemy as sa

revision = "20261104_0007"
down_revision = "20261104_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Use PostgreSQL time for updated_at when inserts omit the field."""
    op.alter_column("users", "updated_at", server_default=sa.func.now())


def downgrade() -> None:
    """Remove the default while retaining all timestamp values."""
    op.alter_column("users", "updated_at", server_default=None)
