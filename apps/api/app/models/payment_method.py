from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
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


class PaymentMethod(Base):
    __tablename__ = "payment_methods"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "household_id",
            "user_id",
            name="payment_methods_scope_unique",
        ),
        ForeignKeyConstraint(
            ["household_id", "user_id"],
            ["household_members.household_id", "household_members.user_id"],
            name="payment_methods_member_fk",
        ),
        CheckConstraint(
            "btrim(name) <> ''", name="payment_methods_name_not_blank"
        ),
        CheckConstraint(
            "method_type IN ('cash', 'debit_card', 'credit_card', "
            "'bank_transfer', 'direct_debit', 'mobile_wallet', "
            "'voucher', 'other')",
            name="payment_methods_type_valid",
        ),
        CheckConstraint(
            "last_four IS NULL OR last_four ~ '^[0-9]{4}$'",
            name="payment_methods_last_four_valid",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    household_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    method_type: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(Text)
    last_four: Mapped[str | None] = mapped_column(String(4))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
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
        back_populates="payment_methods",
        primaryjoin="foreign(PaymentMethod.household_id) == Household.id",
        viewonly=True,
    )
