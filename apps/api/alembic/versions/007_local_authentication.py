"""Add local credentials and server-side authentication sessions.

Revision ID: 007_local_authentication
Revises: 006_income_entries
Create Date: 2026-07-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "007_local_authentication"
down_revision: str | None = "006_income_entries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_credentials",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(password_hash) <> ''",
            name="user_credentials_password_hash_not_blank",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="user_credentials_user_fk",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name="user_credentials_pkey"),
    )
    op.create_table(
        "auth_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'",
            name="auth_sessions_token_hash_valid",
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "user_id"],
            ["household_members.household_id", "household_members.user_id"],
            name="auth_sessions_membership_fk",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="auth_sessions_pkey"),
        sa.UniqueConstraint(
            "token_hash", name="auth_sessions_token_hash_key"
        ),
    )
    op.create_index(
        "auth_sessions_expires_at_idx",
        "auth_sessions",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("auth_sessions_expires_at_idx", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("user_credentials")
