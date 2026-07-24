from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
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


class Merchant(Base):
    __tablename__ = "merchants"
    __table_args__ = (
        UniqueConstraint("id", "household_id", name="merchants_id_household_unique"),
        UniqueConstraint(
            "household_id",
            "normalized_name",
            "normalized_address",
            name="merchants_identity_unique",
        ),
        CheckConstraint("btrim(name) <> ''", name="merchants_name_not_blank"),
        CheckConstraint(
            "btrim(normalized_name) <> ''",
            name="merchants_normalized_name_not_blank",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    household_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("households.id", name="merchants_household_fk"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    normalized_address: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("''")
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
        back_populates="merchants", foreign_keys=[household_id]
    )
