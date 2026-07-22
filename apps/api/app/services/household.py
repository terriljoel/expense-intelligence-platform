from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import AuthSession, Household, HouseholdMember


class HouseholdMemberNotFoundError(Exception):
    """Raised when the target is not an active household member."""


class HouseholdPermissionError(Exception):
    """Raised when a role is not allowed to perform an administration action."""


class LastOwnerError(Exception):
    """Raised when an action would leave a household without an owner."""


class SelfRemovalError(Exception):
    """Raised when an administrator uses removal instead of leave for themself."""


def get_household(
    session: Session, *, household_id: UUID
) -> Household:
    household = session.get(Household, household_id)
    if household is None:
        raise HouseholdMemberNotFoundError
    return household


def update_household(
    session: Session,
    *,
    household_id: UUID,
    changes: dict[str, object],
) -> Household:
    household = get_household(session, household_id=household_id)
    for field_name, value in changes.items():
        setattr(household, field_name, value)
    session.flush()
    return household


def _active_member_for_update(
    session: Session, *, household_id: UUID, user_id: UUID
) -> HouseholdMember:
    membership = session.scalar(
        select(HouseholdMember)
        .where(
            HouseholdMember.household_id == household_id,
            HouseholdMember.user_id == user_id,
            HouseholdMember.is_active.is_(True),
        )
        .with_for_update()
    )
    if membership is None:
        raise HouseholdMemberNotFoundError
    return membership


def _ensure_not_last_owner(
    session: Session,
    *,
    household_id: UUID,
    membership: HouseholdMember,
) -> None:
    if membership.role != "owner":
        return
    owner_count = session.scalar(
        select(func.count())
        .select_from(HouseholdMember)
        .where(
            HouseholdMember.household_id == household_id,
            HouseholdMember.role == "owner",
            HouseholdMember.is_active.is_(True),
        )
    )
    if owner_count is None or owner_count <= 1:
        raise LastOwnerError


def update_member_role(
    session: Session,
    *,
    household_id: UUID,
    actor_user_id: UUID,
    actor_role: str,
    target_user_id: UUID,
    new_role: str,
) -> HouseholdMember:
    target = _active_member_for_update(
        session,
        household_id=household_id,
        user_id=target_user_id,
    )
    if actor_role == "admin" and (
        target.role == "owner"
        or new_role == "owner"
        or target.user_id == actor_user_id
    ):
        raise HouseholdPermissionError
    if target.role == "owner" and new_role != "owner":
        _ensure_not_last_owner(
            session,
            household_id=household_id,
            membership=target,
        )
    target.role = new_role
    session.flush()
    return target


def deactivate_member(
    session: Session,
    *,
    household_id: UUID,
    actor_user_id: UUID,
    actor_role: str,
    target_user_id: UUID,
) -> None:
    if actor_user_id == target_user_id:
        raise SelfRemovalError
    target = _active_member_for_update(
        session,
        household_id=household_id,
        user_id=target_user_id,
    )
    if actor_role == "admin" and target.role == "owner":
        raise HouseholdPermissionError
    _ensure_not_last_owner(
        session,
        household_id=household_id,
        membership=target,
    )
    target.is_active = False
    session.execute(
        delete(AuthSession).where(
            AuthSession.household_id == household_id,
            AuthSession.user_id == target_user_id,
        )
    )
    session.flush()


def leave_household(
    session: Session,
    *,
    household_id: UUID,
    user_id: UUID,
) -> None:
    membership = _active_member_for_update(
        session,
        household_id=household_id,
        user_id=user_id,
    )
    _ensure_not_last_owner(
        session,
        household_id=household_id,
        membership=membership,
    )
    membership.is_active = False
    session.execute(
        delete(AuthSession).where(
            AuthSession.household_id == household_id,
            AuthSession.user_id == user_id,
        )
    )
    session.flush()
