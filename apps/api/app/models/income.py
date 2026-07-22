from __future__ import annotations

from datetime import date, datetime
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
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.household import Household


class IncomeEntry(Base):
    __tablename__ = "income_entries"
    __table_args__ = (
        UniqueConstraint(
            "id", "household_id", name="income_entries_scope_unique"
        ),
        ForeignKeyConstraint(
            ["household_id", "received_by_user_id"],
            ["household_members.household_id", "household_members.user_id"],
            name="income_entries_member_fk",
        ),
        ForeignKeyConstraint(
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
        CheckConstraint(
            "btrim(source) <> ''", name="income_entries_source_not_blank"
        ),
        CheckConstraint(
            "income_type IN ('salary', 'freelance', 'interest', "
            "'gift', 'refund', 'other')",
            name="income_entries_type_valid",
        ),
        CheckConstraint("amount > 0", name="income_entries_amount_positive"),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="income_entries_currency_valid"
        ),
        Index(
            "income_entries_household_received_date_idx",
            "household_id",
            text("received_date DESC"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    household_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("households.id", name="income_entries_household_fk"),
        nullable=False,
    )
    received_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    destination_payment_method_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True)
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    income_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'other'")
    )
    received_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'EUR'")
    )
    notes: Mapped[str | None] = mapped_column(Text)
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
        back_populates="income_entries", foreign_keys=[household_id]
    )
