"""Add OCR business-field duplicate detection.

Revision ID: 016_receipt_duplicates
Revises: 015_categories_payments
Create Date: 2026-07-23
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "016_receipt_duplicates"
down_revision: str | None = "015_categories_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("receipts", sa.Column("receipt_number", sa.Text()))
    op.add_column("receipts", sa.Column("normalized_receipt_number", sa.Text()))
    op.create_index(
        "receipts_number_identity_unique",
        "receipts",
        ["household_id", "merchant_id", "purchase_date", "normalized_receipt_number"],
        unique=True,
        postgresql_where=sa.text(
            "normalized_receipt_number IS NOT NULL AND status <> 'voided'"
        ),
    )
    op.add_column("receipt_captures", sa.Column("suggested_receipt_number", sa.Text()))
    op.add_column(
        "receipt_captures",
        sa.Column("possible_duplicate_receipt_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column("receipt_captures", sa.Column("duplicate_match_level", sa.String(20)))
    op.add_column("receipt_captures", sa.Column("duplicate_reason", sa.Text()))
    op.create_check_constraint(
        "receipt_captures_duplicate_level_valid",
        "receipt_captures",
        "duplicate_match_level IS NULL OR duplicate_match_level IN ('possible', 'strong')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "receipt_captures_duplicate_level_valid", "receipt_captures", type_="check"
    )
    for column in (
        "duplicate_reason",
        "duplicate_match_level",
        "possible_duplicate_receipt_id",
        "suggested_receipt_number",
    ):
        op.drop_column("receipt_captures", column)
    op.drop_index("receipts_number_identity_unique", table_name="receipts")
    op.drop_column("receipts", "normalized_receipt_number")
    op.drop_column("receipts", "receipt_number")

