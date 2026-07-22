from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import secrets
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Household,
    HouseholdInvitation,
    HouseholdMember,
    User,
    UserCredential,
)
from app.services.auth import password_hash


class InvitationConflictError(Exception):
    """Raised when an invitation would duplicate existing access."""


class InvitationNotFoundError(Exception):
    """Raised when an invitation is missing, expired, or already accepted."""


def _hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def create_invitation(
    session: Session,
    *,
    household_id: UUID,
    invited_by_user_id: UUID,
    email: str,
    role: str,
    invitation_hours: int,
) -> tuple[HouseholdInvitation, str]:
    normalized_email = email.strip().casefold()
    existing_user_id = session.scalar(
        select(User.id).where(func.lower(User.email) == normalized_email)
    )
    if existing_user_id is not None:
        existing_membership = session.get(
            HouseholdMember,
            {
                "household_id": household_id,
                "user_id": existing_user_id,
            },
        )
        if existing_membership is not None and existing_membership.is_active:
            raise InvitationConflictError
    now = datetime.now(UTC)
    session.execute(
        delete(HouseholdInvitation).where(
            HouseholdInvitation.household_id == household_id,
            HouseholdInvitation.email == normalized_email,
            HouseholdInvitation.accepted_at.is_(None),
            HouseholdInvitation.expires_at <= now,
        )
    )
    token = secrets.token_urlsafe(32)
    invitation = HouseholdInvitation(
        household_id=household_id,
        email=normalized_email,
        role=role,
        token_hash=_hash_token(token),
        invited_by_user_id=invited_by_user_id,
        expires_at=now + timedelta(hours=invitation_hours),
    )
    try:
        with session.begin_nested():
            session.add(invitation)
            session.flush()
    except IntegrityError as exc:
        raise InvitationConflictError from exc
    return invitation, token


def list_members(
    session: Session, *, household_id: UUID
) -> list[tuple[HouseholdMember, User]]:
    return list(
        session.execute(
            select(HouseholdMember, User)
            .join(User, User.id == HouseholdMember.user_id)
            .where(HouseholdMember.household_id == household_id)
            .where(HouseholdMember.is_active.is_(True))
            .order_by(HouseholdMember.joined_at, User.display_name)
        ).all()
    )


def list_pending_invitations(
    session: Session, *, household_id: UUID
) -> list[HouseholdInvitation]:
    return list(
        session.scalars(
            select(HouseholdInvitation)
            .where(
                HouseholdInvitation.household_id == household_id,
                HouseholdInvitation.accepted_at.is_(None),
                HouseholdInvitation.expires_at > datetime.now(UTC),
            )
            .order_by(HouseholdInvitation.created_at.desc())
        )
    )


def cancel_invitation(
    session: Session, *, household_id: UUID, invitation_id: UUID
) -> None:
    invitation = session.scalar(
        select(HouseholdInvitation)
        .where(
            HouseholdInvitation.id == invitation_id,
            HouseholdInvitation.household_id == household_id,
            HouseholdInvitation.accepted_at.is_(None),
        )
        .with_for_update()
    )
    if invitation is None:
        raise InvitationNotFoundError
    session.delete(invitation)
    session.flush()


def preview_invitation(
    session: Session, *, token: str
) -> tuple[HouseholdInvitation, Household]:
    row = session.execute(
        select(HouseholdInvitation, Household)
        .join(Household, Household.id == HouseholdInvitation.household_id)
        .where(
            HouseholdInvitation.token_hash == _hash_token(token),
            HouseholdInvitation.accepted_at.is_(None),
            HouseholdInvitation.expires_at > datetime.now(UTC),
        )
    ).one_or_none()
    if row is None:
        raise InvitationNotFoundError
    return row


def accept_invitation(
    session: Session,
    *,
    token: str,
    display_name: str,
    password: str,
) -> HouseholdInvitation:
    invitation = session.scalar(
        select(HouseholdInvitation)
        .where(
            HouseholdInvitation.token_hash == _hash_token(token),
            HouseholdInvitation.accepted_at.is_(None),
            HouseholdInvitation.expires_at > datetime.now(UTC),
        )
        .with_for_update()
    )
    if invitation is None:
        raise InvitationNotFoundError
    if session.scalar(
        select(User.id).where(func.lower(User.email) == invitation.email)
    ) is not None:
        raise InvitationConflictError
    user = User(
        auth_subject=f"local:{uuid4()}",
        email=invitation.email,
        display_name=display_name,
    )
    session.add(user)
    session.flush()
    session.add(
        HouseholdMember(
            household_id=invitation.household_id,
            user_id=user.id,
            role=invitation.role,
        )
    )
    session.add(
        UserCredential(
            user_id=user.id,
            password_hash=password_hash.hash(password),
        )
    )
    invitation.accepted_at = datetime.now(UTC)
    session.flush()
    return invitation


def accept_existing_user_invitation(
    session: Session,
    *,
    token: str,
    user_id: UUID,
) -> HouseholdInvitation:
    invitation = session.scalar(
        select(HouseholdInvitation)
        .where(
            HouseholdInvitation.token_hash == _hash_token(token),
            HouseholdInvitation.accepted_at.is_(None),
            HouseholdInvitation.expires_at > datetime.now(UTC),
        )
        .with_for_update()
    )
    if invitation is None:
        raise InvitationNotFoundError
    user = session.get(User, user_id)
    if user is None or user.email is None:
        raise InvitationConflictError
    if user.email.casefold() != invitation.email:
        raise InvitationConflictError
    existing_membership = session.get(
        HouseholdMember,
        {
            "household_id": invitation.household_id,
            "user_id": user_id,
        },
    )
    if existing_membership is not None and existing_membership.is_active:
        raise InvitationConflictError
    if existing_membership is None:
        session.add(
            HouseholdMember(
                household_id=invitation.household_id,
                user_id=user_id,
                role=invitation.role,
            )
        )
    else:
        existing_membership.role = invitation.role
        existing_membership.is_active = True
        existing_membership.joined_at = datetime.now(UTC)
    invitation.accepted_at = datetime.now(UTC)
    session.flush()
    return invitation
