"""Add secure household invitations.

Revision ID: 008_household_invitations
Revises: 007_local_authentication
Create Date: 2026-07-23
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "008_household_invitations"
down_revision: str | None = "007_local_authentication"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "household_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), server_default=sa.text("'member'"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("email = lower(btrim(email)) AND btrim(email) <> ''", name="household_invitations_email_normalized"),
        sa.CheckConstraint("role IN ('admin', 'member')", name="household_invitations_role_valid"),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="household_invitations_token_hash_valid"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], name="household_invitations_household_fk"),
        sa.ForeignKeyConstraint(
            ["household_id", "invited_by_user_id"],
            ["household_members.household_id", "household_members.user_id"],
            name="household_invitations_inviter_membership_fk",
        ),
        sa.PrimaryKeyConstraint("id", name="household_invitations_pkey"),
        sa.UniqueConstraint("token_hash", name="household_invitations_token_hash_key"),
    )
    op.create_index("household_invitations_expires_at_idx", "household_invitations", ["expires_at"], unique=False)
    op.create_index(
        "household_invitations_pending_email_unique",
        "household_invitations",
        ["household_id", sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("accepted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("household_invitations_pending_email_unique", table_name="household_invitations")
    op.drop_index("household_invitations_expires_at_idx", table_name="household_invitations")
    op.drop_table("household_invitations")
