from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.household import Household


class Receipt(Base):
    __tablename__ = "receipts"
    __table_args__ = (
        UniqueConstraint("id", "household_id", name="receipts_id_household_unique"),
        ForeignKeyConstraint(
            ["household_id", "created_by_user_id"],
            ["household_members.household_id", "household_members.user_id"],
            name="receipts_creator_membership_fk",
        ),
        ForeignKeyConstraint(
            ["merchant_id", "household_id"],
            ["merchants.id", "merchants.household_id"],
            name="receipts_merchant_scope_fk",
        ),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="receipts_currency_valid"),
        CheckConstraint("stated_total >= 0", name="receipts_total_nonnegative"),
        CheckConstraint(
            "status IN ('draft', 'pending_review', "
            "'reconciliation_failed', 'approved', 'voided')",
            name="receipts_status_valid",
        ),
        CheckConstraint(
            "source IN ('manual', 'image', 'import')",
            name="receipts_source_valid",
        ),
        CheckConstraint(
            "category IN ('groceries', 'rent', 'health_insurance', 'transport', "
            "'university_fees', 'utilities', 'subscriptions', 'dining', "
            "'shopping', 'travel', 'other')",
            name="receipts_category_valid",
        ),
        CheckConstraint(
            "image_sha256 IS NULL OR image_sha256 ~ '^[0-9a-f]{64}$'",
            name="receipts_image_hash_valid",
        ),
        CheckConstraint(
            "status <> 'approved' OR approved_at IS NOT NULL",
            name="receipts_approved_state_valid",
        ),
        CheckConstraint(
            "status <> 'voided' OR voided_at IS NOT NULL",
            name="receipts_voided_state_valid",
        ),
        Index(
            "receipts_active_image_hash_unique",
            "household_id",
            "image_sha256",
            unique=True,
            postgresql_where=text("image_sha256 IS NOT NULL AND status <> 'voided'"),
        ),
        Index(
            "receipts_household_purchase_date_idx",
            "household_id",
            text("purchase_date DESC"),
        ),
        Index("receipts_merchant_idx", "household_id", "merchant_id"),
        Index(
            "receipts_number_identity_unique",
            "household_id",
            "merchant_id",
            "purchase_date",
            "normalized_receipt_number",
            unique=True,
            postgresql_where=text(
                "normalized_receipt_number IS NOT NULL AND status <> 'voided'"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    household_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("households.id", name="receipts_household_fk"),
        nullable=False,
    )
    merchant_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    purchase_time: Mapped[time | None] = mapped_column(Time)
    merchant_address: Mapped[str | None] = mapped_column(Text)
    merchant_phone: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'EUR'")
    )
    stated_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    tip_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'draft'")
    )
    source: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'manual'")
    )
    category: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'other'")
    )
    image_object_key: Mapped[str | None] = mapped_column(Text)
    image_sha256: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    receipt_number: Mapped[str | None] = mapped_column(Text)
    normalized_receipt_number: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    household: Mapped[Household] = relationship(
        back_populates="receipts", foreign_keys=[household_id]
    )
    items: Mapped[list[ReceiptItem]] = relationship(
        back_populates="receipt",
        cascade="all, delete-orphan",
        order_by="ReceiptItem.position",
    )
    payments: Mapped[list[ReceiptPayment]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan"
    )


class ReceiptItem(Base):
    __tablename__ = "receipt_items"
    __table_args__ = (
        UniqueConstraint(
            "receipt_id", "position", name="receipt_items_position_unique"
        ),
        ForeignKeyConstraint(
            ["receipt_id", "household_id"],
            ["receipts.id", "receipts.household_id"],
            name="receipt_items_receipt_scope_fk",
            ondelete="CASCADE",
        ),
        CheckConstraint("position > 0", name="receipt_items_position_positive"),
        CheckConstraint(
            "btrim(description) <> ''",
            name="receipt_items_description_not_blank",
        ),
        CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name="receipt_items_quantity_positive",
        ),
        CheckConstraint(
            "unit_price IS NULL OR unit_price >= 0",
            name="receipt_items_unit_price_nonnegative",
        ),
        CheckConstraint(
            "line_type IN ('product', 'deposit', 'discount', "
            "'fee', 'tax', 'adjustment')",
            name="receipt_items_line_type_valid",
        ),
        CheckConstraint(
            "line_type = 'adjustment' "
            "OR (line_type = 'discount' AND line_total <= 0) "
            "OR (line_type IN ('product', 'deposit', 'fee', 'tax') "
            "AND line_total >= 0)",
            name="receipt_items_amount_sign_valid",
        ),
        Index("receipt_items_receipt_position_idx", "receipt_id", "position"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    household_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    receipt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    line_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'product'")
    )
    raw_description: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    raw_quantity_text: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    receipt: Mapped[Receipt] = relationship(back_populates="items")


class ReceiptPayment(Base):
    __tablename__ = "receipt_payments"
    __table_args__ = (
        UniqueConstraint(
            "receipt_id",
            "user_id",
            "payment_method_id",
            name="receipt_payments_method_unique",
        ),
        ForeignKeyConstraint(
            ["receipt_id", "household_id"],
            ["receipts.id", "receipts.household_id"],
            name="receipt_payments_receipt_scope_fk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["household_id", "user_id"],
            ["household_members.household_id", "household_members.user_id"],
            name="receipt_payments_member_fk",
        ),
        ForeignKeyConstraint(
            ["payment_method_id", "household_id", "user_id"],
            [
                "payment_methods.id",
                "payment_methods.household_id",
                "payment_methods.user_id",
            ],
            name="receipt_payments_method_scope_fk",
        ),
        CheckConstraint("amount > 0", name="receipt_payments_amount_positive"),
        Index("receipt_payments_receipt_idx", "receipt_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    payment_method_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    household_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    receipt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    receipt: Mapped[Receipt] = relationship(back_populates="payments")
