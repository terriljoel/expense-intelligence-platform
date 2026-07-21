from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Identity,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditEvent(Base):
    """Immutable record of a business action within a household."""

    __tablename__ = "audit_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["household_id", "actor_user_id"],
            ["household_members.household_id", "household_members.user_id"],
            name="audit_events_actor_membership_fk",
        ),
        ForeignKeyConstraint(
            ["receipt_id", "household_id"],
            ["receipts.id", "receipts.household_id"],
            name="audit_events_receipt_scope_fk",
        ),
        CheckConstraint(
            "event_type IN ('receipt_created', 'item_added', "
            "'payment_added', 'receipt_approved')",
            name="audit_events_type_valid",
        ),
        Index(
            "audit_events_receipt_created_idx",
            "receipt_id",
            text("created_at DESC"),
        ),
        Index(
            "audit_events_household_created_idx",
            "household_id",
            text("created_at DESC"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    sequence_number: Mapped[int] = mapped_column(
        BigInteger,
        Identity(
            always=True,
            start=1,
            increment=1,
            minvalue=1,
            maxvalue=9223372036854775807,
            cycle=False,
            cache=1,
        ),
        nullable=False,
        unique=True,
    )
    household_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    actor_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    receipt_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    event_data: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
