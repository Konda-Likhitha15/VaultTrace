"""Add purpose-scoped email OTPs and single-use reset authorizations."""

from alembic import op
import sqlalchemy as sa

revision = "20261103_0003"
down_revision = "20261103_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add new OTP tables and a session revocation version without touching users."""
    op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "email_verifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("otp_hash", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_delivered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("send_window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("send_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("purpose IN ('SIGNUP', 'PASSWORD_RESET')", name="ck_email_verifications_purpose"),
        sa.CheckConstraint("attempts >= 0", name="ck_email_verifications_attempts_nonnegative"),
    )
    op.create_index("ix_email_verifications_email_purpose_created", "email_verifications", ["email", "purpose", "created_at"])
    op.create_index("ix_email_verifications_user_id", "email_verifications", ["user_id"])
    op.create_index("ix_email_verifications_expires_at", "email_verifications", ["expires_at"])
    op.create_table(
        "password_reset_authorizations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_password_reset_authorizations_user_id", "password_reset_authorizations", ["user_id"])


def downgrade() -> None:
    """Remove only tables and column introduced by this revision."""
    op.drop_index("ix_password_reset_authorizations_user_id", table_name="password_reset_authorizations")
    op.drop_table("password_reset_authorizations")
    op.drop_index("ix_email_verifications_expires_at", table_name="email_verifications")
    op.drop_index("ix_email_verifications_user_id", table_name="email_verifications")
    op.drop_index("ix_email_verifications_email_purpose_created", table_name="email_verifications")
    op.drop_table("email_verifications")
    op.drop_column("users", "token_version")
