"""Add verified signup, account state, OTP challenges, and admin audit."""

from alembic import op
import sqlalchemy as sa

revision = "20261103_0002"
down_revision = "20261103_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Extend users and create application, OTP, and audit tables."""
    op.add_column("users", sa.Column("full_name", sa.String(length=160), nullable=True))
    op.add_column("users", sa.Column("username", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("phone_number", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("email_verified", sa.Boolean(), nullable=True))
    op.add_column("users", sa.Column("account_status", sa.String(length=16), nullable=True))
    op.execute("UPDATE users SET full_name = LEFT(email, 160) WHERE full_name IS NULL")
    op.execute("UPDATE users SET username = 'legacy_' || id::text WHERE username IS NULL")
    op.execute("UPDATE users SET email_verified = false WHERE email_verified IS NULL")
    op.execute("UPDATE users SET account_status = CASE WHEN is_active THEN 'ACTIVE' ELSE 'INACTIVE' END WHERE account_status IS NULL")
    op.alter_column("users", "full_name", nullable=False)
    op.alter_column("users", "username", nullable=False)
    op.alter_column("users", "email_verified", nullable=False, server_default=sa.false())
    op.alter_column("users", "account_status", nullable=False, server_default="ACTIVE")
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "registration_applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("approval_status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reviewed_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_registration_applications_approval_status", "registration_applications", ["approval_status"])

    op.create_table(
        "otp_challenges",
        sa.Column("email", sa.String(length=320), primary_key=True),
        sa.Column("otp_digest", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("send_window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("send_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("metadata", sa.JSON(), nullable=False),
    )
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_target_user_id", "audit_logs", ["target_user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])


def downgrade() -> None:
    """Drop extension tables and user fields."""
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_target_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_id", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("otp_challenges")
    op.drop_index("ix_registration_applications_approval_status", table_name="registration_applications")
    op.drop_table("registration_applications")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "account_status")
    op.drop_column("users", "email_verified")
    op.drop_column("users", "phone_number")
    op.drop_column("users", "username")
    op.drop_column("users", "full_name")
