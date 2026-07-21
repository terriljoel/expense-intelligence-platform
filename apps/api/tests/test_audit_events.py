from collections.abc import Generator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.db.seed import seed_development_data
from app.db.session import engine
from app.models import AuditEvent, Household, HouseholdMember
from app.services.receipt import create_receipt


@pytest.fixture
def audit_session() -> Generator[Session, None, None]:
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection)
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


def test_audit_events_are_append_only_in_postgresql(
    audit_session: Session,
) -> None:
    seed = seed_development_data(audit_session)
    receipt = create_receipt(
        audit_session,
        household_id=seed.household_id,
        created_by_user_id=seed.user_id,
        merchant_id=None,
        purchase_date=date(2026, 7, 22),
        currency="EUR",
        stated_total=Decimal("1.00"),
        notes=None,
    )
    event_id = audit_session.scalar(
        select(AuditEvent.id).where(AuditEvent.receipt_id == receipt.id)
    )

    with pytest.raises(DBAPIError, match="append-only"):
        with audit_session.begin_nested():
            audit_session.execute(
                text(
                    "UPDATE audit_events SET event_type = event_type "
                    "WHERE id = :event_id"
                ),
                {"event_id": event_id},
            )


def test_receipt_audit_foreign_key_is_household_scoped(
    audit_session: Session,
) -> None:
    seed = seed_development_data(audit_session)
    receipt = create_receipt(
        audit_session,
        household_id=seed.household_id,
        created_by_user_id=seed.user_id,
        merchant_id=None,
        purchase_date=date(2026, 7, 22),
        currency="EUR",
        stated_total=Decimal("1.00"),
        notes=None,
    )
    other_household = Household(name="Other", default_currency="EUR")
    audit_session.add(other_household)
    audit_session.flush()
    audit_session.add(
        HouseholdMember(
            household_id=other_household.id,
            user_id=seed.user_id,
            role="owner",
        )
    )
    audit_session.flush()

    with pytest.raises(IntegrityError):
        with audit_session.begin_nested():
            audit_session.add(
                AuditEvent(
                    household_id=other_household.id,
                    actor_user_id=seed.user_id,
                    receipt_id=receipt.id,
                    event_type="receipt_created",
                    event_data={},
                )
            )
            audit_session.flush()
