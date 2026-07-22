"""Add household income entries.

Revision ID: 006_income_entries
Revises: 005_receipt_correction_events
Create Date: 2026-07-22
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "006_income_entries"
down_revision: str | None = "005_receipt_correction_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "income_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "received_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "destination_payment_method_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "income_type",
            sa.Text(),
            server_default=sa.text("'other'"),
            nullable=False,
        ),
        sa.Column("received_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            server_default=sa.text("'EUR'"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "amount > 0", name="income_entries_amount_positive"
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="income_entries_currency_valid",
        ),
        sa.CheckConstraint(
            "btrim(source) <> ''",
            name="income_entries_source_not_blank",
        ),
        sa.CheckConstraint(
            "income_type IN ('salary', 'freelance', 'interest', "
            "'gift', 'refund', 'other')",
            name="income_entries_type_valid",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name="income_entries_household_fk",
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "received_by_user_id"],
            ["household_members.household_id", "household_members.user_id"],
            name="income_entries_member_fk",
        ),
        sa.ForeignKeyConstraint(
            [
                "destination_payment_method_id",
                "household_id",
                "received_by_user_id",
            ],
            [
                "payment_methods.id",
                "payment_methods.household_id",
                "payment_methods.user_id",
            ],
            name="income_entries_destination_method_scope_fk",
        ),
        sa.PrimaryKeyConstraint("id", name="income_entries_pkey"),
        sa.UniqueConstraint(
            "id", "household_id", name="income_entries_scope_unique"
        ),
    )
    op.create_index(
        "income_entries_household_received_date_idx",
        "income_entries",
        ["household_id", sa.text("received_date DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "income_entries_household_received_date_idx",
        table_name="income_entries",
    )
    op.drop_table("income_entries")
