"""Add nullable user organization membership for tenant-scoped sharing."""

from alembic import op
import sqlalchemy as sa

revision = "20261104_0009"
down_revision = "20261104_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=160), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("users", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_users_organization_id_organizations", "users", "organizations", ["organization_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_users_organization_id", "users", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_users_organization_id", table_name="users")
    op.drop_constraint("fk_users_organization_id_organizations", "users", type_="foreignkey")
    op.drop_column("users", "organization_id")
    op.drop_table("organizations")
