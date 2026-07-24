"""Add private receipt captures and OCR evidence.

Revision ID: 010_receipt_captures
Revises: 009_active_household_members
Create Date: 2026-07-23
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "010_receipt_captures"
down_revision: str | None = "009_active_household_members"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "receipt_captures",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "uploaded_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("receipt_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("original_filename", sa.Text(), nullable=True),
        sa.Column("media_type", sa.String(length=50), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("image_sha256", sa.String(length=64), nullable=False),
        sa.Column("image_object_key", sa.Text(), nullable=False),
        sa.Column(
            "ocr_status",
            sa.Text(),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("ocr_provider", sa.Text(), nullable=True),
        sa.Column("ocr_raw_text", sa.Text(), nullable=True),
        sa.Column("ocr_error", sa.Text(), nullable=True),
        sa.Column("suggested_merchant_name", sa.Text(), nullable=True),
        sa.Column("suggested_purchase_date", sa.Date(), nullable=True),
        sa.Column("suggested_currency", sa.String(length=3), nullable=True),
        sa.Column("suggested_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("ocr_completed_at", sa.DateTime(timezone=True), nullable=True),
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
            "image_sha256 ~ '^[0-9a-f]{64}$'",
            name="receipt_captures_hash_valid",
        ),
        sa.CheckConstraint(
            "byte_size > 0", name="receipt_captures_size_positive"
        ),
        sa.CheckConstraint(
            "ocr_status IN ('pending', 'processing', 'succeeded', 'failed')",
            name="receipt_captures_ocr_status_valid",
        ),
        sa.CheckConstraint(
            "suggested_currency IS NULL "
            "OR suggested_currency ~ '^[A-Z]{3}$'",
            name="receipt_captures_currency_valid",
        ),
        sa.CheckConstraint(
            "suggested_total IS NULL OR suggested_total >= 0",
            name="receipt_captures_total_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name="receipt_captures_household_fk",
        ),
        sa.ForeignKeyConstraint(
            ["household_id", "uploaded_by_user_id"],
            ["household_members.household_id", "household_members.user_id"],
            name="receipt_captures_member_fk",
        ),
        sa.ForeignKeyConstraint(
            ["receipt_id", "household_id"],
            ["receipts.id", "receipts.household_id"],
            name="receipt_captures_receipt_scope_fk",
        ),
        sa.PrimaryKeyConstraint("id", name="receipt_captures_pkey"),
        sa.UniqueConstraint(
            "id", "household_id", name="receipt_captures_scope_unique"
        ),
        sa.UniqueConstraint(
            "household_id",
            "image_sha256",
            name="receipt_captures_household_hash_unique",
        ),
        sa.UniqueConstraint(
            "receipt_id", name="receipt_captures_receipt_unique"
        ),
    )
    op.create_index(
        "receipt_captures_household_created_idx",
        "receipt_captures",
        ["household_id", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "receipt_captures_household_created_idx",
        table_name="receipt_captures",
    )
    op.drop_table("receipt_captures")
