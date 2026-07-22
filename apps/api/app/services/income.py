from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IncomeEntry, PaymentMethod


class IncomeNotFoundError(Exception):
    """Raised when an income record is missing or outside the household."""


class IncomeDestinationMethodNotFoundError(Exception):
    """Raised when the receiving user's active method cannot be found."""


def _validate_destination_method(
    session: Session,
    *,
    household_id: UUID,
    user_id: UUID,
    payment_method_id: UUID,
) -> None:
    method = session.scalar(
        select(PaymentMethod.id).where(
            PaymentMethod.id == payment_method_id,
            PaymentMethod.household_id == household_id,
            PaymentMethod.user_id == user_id,
            PaymentMethod.is_active.is_(True),
        )
    )
    if method is None:
        raise IncomeDestinationMethodNotFoundError


def create_income(
    session: Session,
    *,
    household_id: UUID,
    received_by_user_id: UUID,
    source: str,
    income_type: str,
    received_date: date,
    amount: Decimal,
    currency: str,
    destination_payment_method_id: UUID | None,
    notes: str | None,
) -> IncomeEntry:
    if destination_payment_method_id is not None:
        _validate_destination_method(
            session,
            household_id=household_id,
            user_id=received_by_user_id,
            payment_method_id=destination_payment_method_id,
        )
    entry = IncomeEntry(
        household_id=household_id,
        received_by_user_id=received_by_user_id,
        source=source,
        income_type=income_type,
        received_date=received_date,
        amount=amount,
        currency=currency,
        destination_payment_method_id=destination_payment_method_id,
        notes=notes,
    )
    session.add(entry)
    session.flush()
    return entry


def list_income(
    session: Session,
    *,
    household_id: UUID,
    limit: int = 100,
    offset: int = 0,
) -> list[IncomeEntry]:
    return list(
        session.scalars(
            select(IncomeEntry)
            .where(IncomeEntry.household_id == household_id)
            .order_by(IncomeEntry.received_date.desc(), IncomeEntry.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )


def get_income(
    session: Session,
    *,
    household_id: UUID,
    income_id: UUID,
    for_update: bool = False,
) -> IncomeEntry:
    statement = select(IncomeEntry).where(
        IncomeEntry.id == income_id,
        IncomeEntry.household_id == household_id,
    )
    if for_update:
        statement = statement.with_for_update()
    entry = session.scalar(statement)
    if entry is None:
        raise IncomeNotFoundError
    return entry


def update_income(
    session: Session,
    *,
    household_id: UUID,
    income_id: UUID,
    changes: dict[str, object],
) -> IncomeEntry:
    entry = get_income(
        session,
        household_id=household_id,
        income_id=income_id,
        for_update=True,
    )
    if "destination_payment_method_id" in changes:
        method_id = changes["destination_payment_method_id"]
        if method_id is not None:
            _validate_destination_method(
                session,
                household_id=household_id,
                user_id=entry.received_by_user_id,
                payment_method_id=method_id,
            )
    for field_name, value in changes.items():
        setattr(entry, field_name, value)
    session.flush()
    session.refresh(entry)
    return entry


def delete_income(
    session: Session,
    *,
    household_id: UUID,
    income_id: UUID,
) -> None:
    entry = get_income(
        session,
        household_id=household_id,
        income_id=income_id,
        for_update=True,
    )
    session.delete(entry)
    session.flush()
