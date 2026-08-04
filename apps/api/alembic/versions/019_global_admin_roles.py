"""Separate global administration from household ownership.

Revision ID: 019_global_admin_roles
Revises: 018_product_family
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "019_global_admin_roles"
down_revision: str | None = "018_product_family"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_global_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Preserve existing administrators at the global level, then remove the
    # obsolete household-level role.
    op.execute(
        """
        UPDATE users
        SET is_global_admin = true
        WHERE id IN (
            SELECT user_id FROM household_members WHERE role = 'admin'
        )
        """
    )
    op.execute("UPDATE household_members SET role = 'member' WHERE role = 'admin'")
    op.execute("UPDATE household_invitations SET role = 'member' WHERE role = 'admin'")
    op.drop_constraint("household_members_role_valid", "household_members", type_="check")
    op.create_check_constraint(
        "household_members_role_valid",
        "household_members",
        "role IN ('owner', 'member')",
    )
    op.drop_constraint(
        "household_invitations_role_valid",
        "household_invitations",
        type_="check",
    )
    op.create_check_constraint(
        "household_invitations_role_valid",
        "household_invitations",
        "role = 'member'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "household_invitations_role_valid",
        "household_invitations",
        type_="check",
    )
    op.create_check_constraint(
        "household_invitations_role_valid",
        "household_invitations",
        "role IN ('admin', 'member')",
    )
    op.drop_constraint("household_members_role_valid", "household_members", type_="check")
    op.create_check_constraint(
        "household_members_role_valid",
        "household_members",
        "role IN ('owner', 'admin', 'member')",
    )
    op.drop_column("users", "is_global_admin")
