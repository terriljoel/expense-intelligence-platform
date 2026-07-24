from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReceiptCapture(Base):
    """A private image and its OCR evidence before receipt approval."""

    __tablename__ = "receipt_captures"
    __table_args__ = (
        UniqueConstraint("id", "household_id", name="receipt_captures_scope_unique"),
        UniqueConstraint(
            "household_id",
            "image_sha256",
            name="receipt_captures_household_hash_unique",
        ),
        UniqueConstraint("receipt_id", name="receipt_captures_receipt_unique"),
        ForeignKeyConstraint(
            ["household_id", "uploaded_by_user_id"],
            ["household_members.household_id", "household_members.user_id"],
            name="receipt_captures_member_fk",
        ),
        ForeignKeyConstraint(
            ["receipt_id", "household_id"],
            ["receipts.id", "receipts.household_id"],
            name="receipt_captures_receipt_scope_fk",
        ),
        ForeignKeyConstraint(
            ["suggested_payment_method_id", "household_id", "uploaded_by_user_id"],
            ["payment_methods.id", "payment_methods.household_id", "payment_methods.user_id"],
            name="receipt_captures_suggested_method_scope_fk",
        ),
        CheckConstraint(
            "image_sha256 ~ '^[0-9a-f]{64}$'",
            name="receipt_captures_hash_valid",
        ),
        CheckConstraint("byte_size > 0", name="receipt_captures_size_positive"),
        CheckConstraint(
            "ocr_status IN ('pending', 'processing', 'succeeded', 'failed')",
            name="receipt_captures_ocr_status_valid",
        ),
        CheckConstraint(
            "suggested_currency IS NULL OR suggested_currency ~ '^[A-Z]{3}$'",
            name="receipt_captures_currency_valid",
        ),
        CheckConstraint(
            "suggested_total IS NULL OR suggested_total >= 0",
            name="receipt_captures_total_nonnegative",
        ),
        CheckConstraint(
            "duplicate_match_level IS NULL OR duplicate_match_level IN ('possible', 'strong')",
            name="receipt_captures_duplicate_level_valid",
        ),
        Index(
            "receipt_captures_household_created_idx",
            "household_id",
            text("created_at DESC"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    household_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("households.id", name="receipt_captures_household_fk"),
        nullable=False,
    )
    uploaded_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    receipt_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    original_filename: Mapped[str | None] = mapped_column(Text)
    media_type: Mapped[str] = mapped_column(String(50), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    image_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    image_object_key: Mapped[str] = mapped_column(Text, nullable=False)
    ocr_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'pending'")
    )
    ocr_provider: Mapped[str | None] = mapped_column(Text)
    ocr_raw_text: Mapped[str | None] = mapped_column(Text)
    ocr_error: Mapped[str | None] = mapped_column(Text)
    ocr_result: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    suggested_items: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB)
    suggested_merchant_name: Mapped[str | None] = mapped_column(Text)
    suggested_merchant_address: Mapped[str | None] = mapped_column(Text)
    suggested_merchant_phone: Mapped[str | None] = mapped_column(Text)
    suggested_purchase_date: Mapped[date | None] = mapped_column(Date)
    suggested_transaction_time: Mapped[time | None] = mapped_column(Time)
    suggested_currency: Mapped[str | None] = mapped_column(String(3))
    suggested_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    suggested_subtotal: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    suggested_tax: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    suggested_tip: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    suggested_payment_type: Mapped[str | None] = mapped_column(Text)
    suggested_payment_provider: Mapped[str | None] = mapped_column(Text)
    suggested_payment_last_four: Mapped[str | None] = mapped_column(String(4))
    suggested_payment_method_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    suggested_payment_reason: Mapped[str | None] = mapped_column(Text)
    suggested_receipt_number: Mapped[str | None] = mapped_column(Text)
    possible_duplicate_receipt_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    duplicate_match_level: Mapped[str | None] = mapped_column(String(20))
    duplicate_reason: Mapped[str | None] = mapped_column(Text)
    ocr_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
