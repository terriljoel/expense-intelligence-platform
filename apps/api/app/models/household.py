from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.income import IncomeEntry
    from app.models.merchant import Merchant
    from app.models.payment_method import PaymentMethod
    from app.models.receipt import Receipt
    from app.models.user import User


class Household(Base):
    __tablename__ = "households"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="households_name_not_blank"),
        CheckConstraint(
            "default_currency ~ '^[A-Z]{3}$'",
            name="households_currency_valid",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    default_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'EUR'")
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

    memberships: Mapped[list[HouseholdMember]] = relationship(
        back_populates="household"
    )
    merchants: Mapped[list[Merchant]] = relationship(
        back_populates="household",
        foreign_keys="Merchant.household_id",
    )
    payment_methods: Mapped[list[PaymentMethod]] = relationship(
        back_populates="household",
        primaryjoin="Household.id == foreign(PaymentMethod.household_id)",
        viewonly=True,
    )
    receipts: Mapped[list[Receipt]] = relationship(
        back_populates="household",
        foreign_keys="Receipt.household_id",
    )
    income_entries: Mapped[list[IncomeEntry]] = relationship(
        back_populates="household",
        foreign_keys="IncomeEntry.household_id",
    )


class HouseholdMember(Base):
    __tablename__ = "household_members"
    __table_args__ = (
        CheckConstraint(
            "role IN ('owner', 'member')",
            name="household_members_role_valid",
        ),
    )

    household_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("households.id", name="household_members_household_fk"),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", name="household_members_user_fk"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'member'")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    household: Mapped[Household] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")
