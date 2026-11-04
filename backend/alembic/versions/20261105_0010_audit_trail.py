"""Extend audit rows with safe actor, resource, outcome, and request context."""

from alembic import context, op
import sqlalchemy as sa


revision = "20261105_0010"
down_revision = "20261104_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable event context without deleting or rewriting existing rows."""
    op.alter_column("audit_logs", "actor_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("audit_logs", "target_user_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("audit_logs", sa.Column("actor_email", sa.String(length=320), nullable=True))
    op.add_column("audit_logs", sa.Column("actor_username", sa.String(length=32), nullable=True))
    op.add_column("audit_logs", sa.Column("resource_type", sa.String(length=48), nullable=True))
    op.add_column("audit_logs", sa.Column("resource_id", sa.String(length=64), nullable=True))
    op.add_column("audit_logs", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.add_column("audit_logs", sa.Column("outcome", sa.String(length=16), server_default="SUCCESS", nullable=False))
    op.add_column("audit_logs", sa.Column("request_ip", sa.String(length=64), nullable=True))
    op.add_column("audit_logs", sa.Column("user_agent", sa.String(length=512), nullable=True))
    op.add_column("audit_logs", sa.Column("previous_state", sa.JSON(), nullable=True))
    op.add_column("audit_logs", sa.Column("new_state", sa.JSON(), nullable=True))
    op.create_foreign_key(
        "fk_audit_logs_organization_id_organizations",
        "audit_logs", "organizations", ["organization_id"], ["id"], ondelete="SET NULL",
    )
    op.create_check_constraint("ck_audit_logs_outcome", "audit_logs", "outcome IN ('SUCCESS', 'FAILURE')")
    op.create_index("ix_audit_logs_resource_id", "audit_logs", ["resource_id"])
    op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"])
    op.create_index("ix_audit_logs_resource", "audit_logs", ["resource_type", "resource_id", "occurred_at"])
    op.create_index("ix_audit_logs_organization_occurred", "audit_logs", ["organization_id", "occurred_at"])
    op.create_index("ix_audit_logs_occurred", "audit_logs", ["occurred_at"])


def downgrade() -> None:
    """Remove the extension only when no event relies on nullable identities."""
    if not context.is_offline_mode():
        connection = op.get_bind()
        missing_actor = connection.scalar(sa.text("SELECT count(*) FROM audit_logs WHERE actor_id IS NULL OR target_user_id IS NULL"))
        if missing_actor:
            raise RuntimeError("Cannot downgrade audit trail: anonymous audit events must be retained.")
    op.drop_index("ix_audit_logs_occurred", table_name="audit_logs")
    op.drop_index("ix_audit_logs_organization_occurred", table_name="audit_logs")
    op.drop_index("ix_audit_logs_resource", table_name="audit_logs")
    op.drop_index("ix_audit_logs_organization_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_resource_id", table_name="audit_logs")
    op.drop_constraint("ck_audit_logs_outcome", "audit_logs", type_="check")
    op.drop_constraint("fk_audit_logs_organization_id_organizations", "audit_logs", type_="foreignkey")
    for column in ("new_state", "previous_state", "user_agent", "request_ip", "outcome", "organization_id", "resource_id", "resource_type", "actor_username", "actor_email"):
        op.drop_column("audit_logs", column)
    op.alter_column("audit_logs", "target_user_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("audit_logs", "actor_id", existing_type=sa.Integer(), nullable=False)
