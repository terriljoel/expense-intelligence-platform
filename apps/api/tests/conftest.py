from collections.abc import Generator

import pytest
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentPrincipal, get_current_principal
from app.db.seed import DEV_AUTH_SUBJECT, DEV_HOUSEHOLD_NAME
from app.db.session import get_db_session
from app.main import app
from app.models import Household, HouseholdMember, User


def get_test_principal(
    session: Session = Depends(get_db_session),
) -> CurrentPrincipal:
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
    ).one()
    return CurrentPrincipal(
        user_id=row.id,
        household_id=row.household_id,
        role=row.role,
    )


@pytest.fixture(autouse=True)
def authenticated_domain_test_principal() -> Generator[None, None, None]:
    app.dependency_overrides[get_current_principal] = get_test_principal
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
