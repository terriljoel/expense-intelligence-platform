"""Store normalized OCR line-item suggestions.

Revision ID: 012_receipt_ocr_items
Revises: 011_receipt_ocr_details
Create Date: 2026-07-23
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "012_receipt_ocr_items"
down_revision: str | None = "011_receipt_ocr_details"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "receipt_captures",
        sa.Column("suggested_items", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("receipt_captures", "suggested_items")
