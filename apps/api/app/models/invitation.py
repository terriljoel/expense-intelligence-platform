from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HouseholdInvitation(Base):
    __tablename__ = "household_invitations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["household_id", "invited_by_user_id"],
            ["household_members.household_id", "household_members.user_id"],
            name="household_invitations_inviter_membership_fk",
        ),
        CheckConstraint(
            "email = lower(btrim(email)) AND btrim(email) <> ''",
            name="household_invitations_email_normalized",
        ),
        CheckConstraint(
            "role = 'member'",
            name="household_invitations_role_valid",
        ),
        CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'",
            name="household_invitations_token_hash_valid",
        ),
        Index(
            "household_invitations_pending_email_unique",
            "household_id",
            text("lower(email)"),
            unique=True,
            postgresql_where=text("accepted_at IS NULL"),
        ),
        Index("household_invitations_expires_at_idx", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    household_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("households.id", name="household_invitations_household_fk"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'member'")
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    invited_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
