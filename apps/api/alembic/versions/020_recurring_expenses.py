"""Add monthly recurring expense templates and generated draft identity."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "020_recurring_expenses"
down_revision: str | None = "019_global_admin_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recurring_expenses",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "household_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("households.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True)),
        sa.Column("payment_method_id", postgresql.UUID(as_uuid=True)),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False, server_default="other"),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("day_of_month", sa.Integer(), nullable=False),
        sa.Column("next_occurrence_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("amount >= 0", name="recurring_expenses_amount_nonnegative"),
        sa.CheckConstraint(
            "day_of_month BETWEEN 1 AND 31", name="recurring_expenses_day_valid"
        ),
    )
    op.add_column(
        "receipts",
        sa.Column(
            "recurring_template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recurring_expenses.id", ondelete="SET NULL"),
        ),
    )
    op.add_column("receipts", sa.Column("recurring_occurrence_date", sa.Date()))
    op.create_unique_constraint(
        "receipts_recurring_occurrence_unique",
        "receipts",
        ["recurring_template_id", "recurring_occurrence_date"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "receipts_recurring_occurrence_unique", "receipts", type_="unique"
    )
    op.drop_column("receipts", "recurring_occurrence_date")
    op.drop_column("receipts", "recurring_template_id")
    op.drop_table("recurring_expenses")
