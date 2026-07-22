from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import secrets
from uuid import UUID

from pwdlib import PasswordHash
from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    AuthSession,
    Household,
    HouseholdMember,
    User,
    UserCredential,
)


SESSION_COOKIE_NAME = "expense_session"
password_hash = PasswordHash.recommended()
_DUMMY_PASSWORD_HASH = password_hash.hash("not-a-real-user-password")


class InvalidCredentialsError(Exception):
    """Raised when an email/password combination is invalid."""


class HouseholdAccessError(Exception):
    """Raised when a user does not belong to the requested household."""


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    session_id: UUID
    user_id: UUID
    household_id: UUID
    role: str
    email: str
    display_name: str
    expires_at: datetime


def _token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def authenticate_password(
    session: Session,
    *,
    email: str,
    password: str,
) -> tuple[User, HouseholdMember]:
    row = session.execute(
        select(User, UserCredential)
        .join(UserCredential, UserCredential.user_id == User.id)
        .where(func.lower(User.email) == email.casefold())
    ).one_or_none()
    if row is None:
        password_hash.verify(password, _DUMMY_PASSWORD_HASH)
        raise InvalidCredentialsError
    user, credential = row
    if not password_hash.verify(password, credential.password_hash):
        raise InvalidCredentialsError
    membership = session.scalar(
        select(HouseholdMember)
        .where(
            HouseholdMember.user_id == user.id,
            HouseholdMember.is_active.is_(True),
        )
        .order_by(
            case(
                (HouseholdMember.role == "owner", 0),
                (HouseholdMember.role == "admin", 1),
                else_=2,
            ),
            HouseholdMember.joined_at,
        )
        .limit(1)
    )
    if membership is None:
        raise InvalidCredentialsError
    return user, membership


def create_auth_session(
    session: Session,
    *,
    user: User,
    membership: HouseholdMember,
    session_hours: int,
) -> tuple[str, AuthSession]:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(hours=session_hours)
    auth_session = AuthSession(
        user_id=user.id,
        household_id=membership.household_id,
        token_hash=_token_hash(token),
        expires_at=expires_at,
    )
    session.add(auth_session)
    session.flush()
    return token, auth_session


def resolve_auth_session(
    session: Session,
    *,
    token: str,
) -> AuthenticatedPrincipal | None:
    row = session.execute(
        select(AuthSession, User, HouseholdMember)
        .join(User, User.id == AuthSession.user_id)
        .join(
            HouseholdMember,
            (HouseholdMember.household_id == AuthSession.household_id)
            & (HouseholdMember.user_id == AuthSession.user_id),
        )
        .where(
            AuthSession.token_hash == _token_hash(token),
            AuthSession.expires_at > datetime.now(UTC),
            HouseholdMember.is_active.is_(True),
        )
    ).one_or_none()
    if row is None:
        return None
    auth_session, user, membership = row
    if user.email is None:
        return None
    return AuthenticatedPrincipal(
        session_id=auth_session.id,
        user_id=user.id,
        household_id=membership.household_id,
        role=membership.role,
        email=user.email,
        display_name=user.display_name,
        expires_at=auth_session.expires_at,
    )


def revoke_auth_session(session: Session, *, token: str) -> None:
    session.execute(
        delete(AuthSession).where(AuthSession.token_hash == _token_hash(token))
    )


def list_user_households(
    session: Session, *, user_id: UUID
) -> list[tuple[Household, HouseholdMember]]:
    return list(
        session.execute(
            select(Household, HouseholdMember)
            .join(
                HouseholdMember,
                HouseholdMember.household_id == Household.id,
            )
            .where(
                HouseholdMember.user_id == user_id,
                HouseholdMember.is_active.is_(True),
            )
            .order_by(Household.name, Household.id)
        ).all()
    )


def create_household(
    session: Session,
    *,
    user_id: UUID,
    name: str,
    default_currency: str,
) -> tuple[Household, HouseholdMember]:
    household = Household(name=name, default_currency=default_currency)
    session.add(household)
    session.flush()
    membership = HouseholdMember(
        household_id=household.id,
        user_id=user_id,
        role="owner",
    )
    session.add(membership)
    session.flush()
    return household, membership


def switch_auth_session_household(
    session: Session,
    *,
    token: str,
    user_id: UUID,
    household_id: UUID,
) -> HouseholdMember:
    membership = session.get(
        HouseholdMember,
        {"household_id": household_id, "user_id": user_id},
    )
    if membership is None:
        raise HouseholdAccessError
    if not membership.is_active:
        raise HouseholdAccessError
    auth_session = session.scalar(
        select(AuthSession)
        .where(
            AuthSession.token_hash == _token_hash(token),
            AuthSession.user_id == user_id,
            AuthSession.expires_at > datetime.now(UTC),
        )
        .with_for_update()
    )
    if auth_session is None:
        raise HouseholdAccessError
    auth_session.household_id = household_id
    session.flush()
    return membership
