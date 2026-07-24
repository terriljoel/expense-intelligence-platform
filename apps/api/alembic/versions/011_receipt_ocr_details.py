"""Store structured OCR details and confirmed receipt metadata.

Revision ID: 011_receipt_ocr_details
Revises: 010_receipt_captures
Create Date: 2026-07-23
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "011_receipt_ocr_details"
down_revision: str | None = "010_receipt_captures"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "receipt_captures",
        sa.Column("ocr_result", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "receipt_captures",
        sa.Column("suggested_merchant_address", sa.Text(), nullable=True),
    )
    op.add_column(
        "receipt_captures",
        sa.Column("suggested_merchant_phone", sa.Text(), nullable=True),
    )
    op.add_column(
        "receipt_captures",
        sa.Column("suggested_transaction_time", sa.Time(), nullable=True),
    )
    for column in ("suggested_subtotal", "suggested_tax", "suggested_tip"):
        op.add_column(
            "receipt_captures",
            sa.Column(column, sa.Numeric(14, 2), nullable=True),
        )

    op.add_column("receipts", sa.Column("purchase_time", sa.Time(), nullable=True))
    op.add_column("receipts", sa.Column("merchant_address", sa.Text(), nullable=True))
    op.add_column("receipts", sa.Column("merchant_phone", sa.Text(), nullable=True))
    for column in ("subtotal", "tax_amount", "tip_amount"):
        op.add_column(
            "receipts",
            sa.Column(column, sa.Numeric(14, 2), nullable=True),
        )


def downgrade() -> None:
    for column in (
        "tip_amount",
        "tax_amount",
        "subtotal",
        "merchant_phone",
        "merchant_address",
        "purchase_time",
    ):
        op.drop_column("receipts", column)
    for column in (
        "suggested_tip",
        "suggested_tax",
        "suggested_subtotal",
        "suggested_transaction_time",
        "suggested_merchant_phone",
        "suggested_merchant_address",
        "ocr_result",
    ):
        op.drop_column("receipt_captures", column)
