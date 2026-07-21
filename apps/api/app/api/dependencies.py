from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.seed import DEV_AUTH_SUBJECT, DEV_HOUSEHOLD_NAME
from app.db.session import get_db_session
from app.models import Household, HouseholdMember, User


@dataclass(frozen=True)
class CurrentPrincipal:
    user_id: UUID
    household_id: UUID
    role: str


def get_current_principal(
    session: Session = Depends(get_db_session),
) -> CurrentPrincipal:
    """Resolve the seeded local owner until authentication is implemented."""

    row = session.execute(
        select(
            User.id,
            HouseholdMember.household_id,
            HouseholdMember.role,
        )
        .join(HouseholdMember, HouseholdMember.user_id == User.id)
        .join(Household, Household.id == HouseholdMember.household_id)
        .where(
            User.auth_subject == DEV_AUTH_SUBJECT,
            Household.name == DEV_HOUSEHOLD_NAME,
        )
    ).one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Development owner is not seeded",
        )

    return CurrentPrincipal(
        user_id=row.id,
        household_id=row.household_id,
        role=row.role,
    )
