"""Add transaction categories and OCR payment suggestions.

Revision ID: 015_categories_payments
Revises: 014_household_data_reset
Create Date: 2026-07-23
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "015_categories_payments"
down_revision: str | None = "014_household_data_reset"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("receipts", sa.Column("category", sa.Text(), server_default="other", nullable=False))
    op.create_check_constraint(
        "receipts_category_valid", "receipts",
        "category IN ('groceries', 'rent', 'health_insurance', 'transport', "
        "'university_fees', 'utilities', 'subscriptions', 'dining', "
        "'shopping', 'travel', 'other')",
    )
    op.add_column("income_entries", sa.Column("category", sa.Text(), server_default="other", nullable=False))
    op.create_check_constraint(
        "income_entries_category_valid", "income_entries",
        "category IN ('salary_payslip', 'freelance', 'interest', 'gift', "
        "'refund', 'benefits', 'other')",
    )
    op.add_column("receipt_captures", sa.Column("suggested_payment_type", sa.Text()))
    op.add_column("receipt_captures", sa.Column("suggested_payment_provider", sa.Text()))
    op.add_column("receipt_captures", sa.Column("suggested_payment_last_four", sa.String(4)))
    op.add_column("receipt_captures", sa.Column("suggested_payment_method_id", postgresql.UUID(as_uuid=True)))
    op.add_column("receipt_captures", sa.Column("suggested_payment_reason", sa.Text()))
    op.create_foreign_key(
        "receipt_captures_suggested_method_scope_fk", "receipt_captures", "payment_methods",
        ["suggested_payment_method_id", "household_id", "uploaded_by_user_id"],
        ["id", "household_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_constraint("receipt_captures_suggested_method_scope_fk", "receipt_captures", type_="foreignkey")
    for column in (
        "suggested_payment_reason", "suggested_payment_method_id",
        "suggested_payment_last_four", "suggested_payment_provider",
        "suggested_payment_type",
    ):
        op.drop_column("receipt_captures", column)
    op.drop_constraint("income_entries_category_valid", "income_entries", type_="check")
    op.drop_column("income_entries", "category")
    op.drop_constraint("receipts_category_valid", "receipts", type_="check")
    op.drop_column("receipts", "category")
