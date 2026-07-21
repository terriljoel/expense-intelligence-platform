from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Household, HouseholdMember, PaymentMethod, User


DEV_AUTH_SUBJECT = "local-dev-terril"
DEV_EMAIL = "terril@example.test"
DEV_DISPLAY_NAME = "Terril"
DEV_HOUSEHOLD_NAME = "Personal Household"


@dataclass(frozen=True)
class SeedResult:
    user_id: UUID
    household_id: UUID
    payment_method_id: UUID


def seed_development_data(session: Session) -> SeedResult:
    """Create the single-user development baseline without duplicates."""

    user = session.scalar(
        select(User).where(User.auth_subject == DEV_AUTH_SUBJECT)
    )
    if user is None:
        user = User(
            auth_subject=DEV_AUTH_SUBJECT,
            email=DEV_EMAIL,
            display_name=DEV_DISPLAY_NAME,
        )
        session.add(user)
        session.flush()

    membership = session.scalar(
        select(HouseholdMember)
        .join(Household, Household.id == HouseholdMember.household_id)
        .where(
            HouseholdMember.user_id == user.id,
            Household.name == DEV_HOUSEHOLD_NAME,
        )
    )
    if membership is None:
        household = Household(
            name=DEV_HOUSEHOLD_NAME,
            default_currency="EUR",
        )
        session.add(household)
        session.flush()

        membership = HouseholdMember(
            household_id=household.id,
            user_id=user.id,
            role="owner",
        )
        session.add(membership)
        session.flush()
    else:
        household = session.get(Household, membership.household_id)
        if household is None:
            raise RuntimeError("Seed membership references a missing household")
        if membership.role != "owner":
            membership.role = "owner"

    payment_method = session.scalar(
        select(PaymentMethod).where(
            PaymentMethod.household_id == household.id,
            PaymentMethod.user_id == user.id,
            PaymentMethod.method_type == "cash",
            PaymentMethod.name == "Cash",
        )
    )
    if payment_method is None:
        payment_method = PaymentMethod(
            household_id=household.id,
            user_id=user.id,
            name="Cash",
            method_type="cash",
        )
        session.add(payment_method)
        session.flush()

    return SeedResult(
        user_id=user.id,
        household_id=household.id,
        payment_method_id=payment_method.id,
    )


def main() -> int:
    with SessionLocal.begin() as session:
        result = seed_development_data(session)

    print("Development seed is ready.")
    print(f"user_id={result.user_id}")
    print(f"household_id={result.household_id}")
    print(f"payment_method_id={result.payment_method_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
