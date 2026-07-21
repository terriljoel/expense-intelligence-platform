from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.seed import DEV_AUTH_SUBJECT, seed_development_data
from app.db.session import engine
from app.models import Household, HouseholdMember, PaymentMethod, User


def test_development_seed_is_idempotent() -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection)

        try:
            first_result = seed_development_data(session)
            second_result = seed_development_data(session)

            assert first_result == second_result
            assert session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.auth_subject == DEV_AUTH_SUBJECT)
            ) == 1
            assert session.scalar(
                select(func.count())
                .select_from(Household)
                .where(Household.id == first_result.household_id)
            ) == 1
            assert session.scalar(
                select(func.count())
                .select_from(HouseholdMember)
                .where(
                    HouseholdMember.household_id == first_result.household_id,
                    HouseholdMember.user_id == first_result.user_id,
                    HouseholdMember.role == "owner",
                )
            ) == 1
            assert session.scalar(
                select(func.count())
                .select_from(PaymentMethod)
                .where(
                    PaymentMethod.id == first_result.payment_method_id,
                    PaymentMethod.method_type == "cash",
                )
            ) == 1
        finally:
            session.close()
            transaction.rollback()
