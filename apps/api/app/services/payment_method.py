from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import PaymentMethod


class PaymentMethodNotFoundError(Exception):
    """Raised when a method is missing or outside the current principal scope."""


class PaymentMethodConflictError(Exception):
    """Raised when an equivalent active method already exists."""


def create_payment_method(
    session: Session,
    *,
    household_id: UUID,
    user_id: UUID,
    name: str,
    method_type: str,
    provider: str | None,
    last_four: str | None,
) -> PaymentMethod:
    method = PaymentMethod(
        household_id=household_id,
        user_id=user_id,
        name=name,
        method_type=method_type,
        provider=provider,
        last_four=last_four,
        is_active=True,
    )
    try:
        with session.begin_nested():
            session.add(method)
            session.flush()
    except IntegrityError as exc:
        raise PaymentMethodConflictError from exc
    return method


def list_payment_methods(
    session: Session,
    *,
    household_id: UUID,
    user_id: UUID,
    include_inactive: bool = False,
) -> list[PaymentMethod]:
    statement = select(PaymentMethod).where(
        PaymentMethod.household_id == household_id,
        PaymentMethod.user_id == user_id,
    )
    if not include_inactive:
        statement = statement.where(PaymentMethod.is_active.is_(True))
    return list(
        session.scalars(
            statement.order_by(
                PaymentMethod.is_active.desc(),
                PaymentMethod.name,
                PaymentMethod.created_at,
            )
        )
    )


def get_payment_method(
    session: Session,
    *,
    household_id: UUID,
    user_id: UUID,
    payment_method_id: UUID,
    for_update: bool = False,
    active_only: bool = False,
) -> PaymentMethod:
    statement = select(PaymentMethod).where(
        PaymentMethod.id == payment_method_id,
        PaymentMethod.household_id == household_id,
        PaymentMethod.user_id == user_id,
    )
    if active_only:
        statement = statement.where(PaymentMethod.is_active.is_(True))
    if for_update:
        statement = statement.with_for_update()
    method = session.scalar(statement)
    if method is None:
        raise PaymentMethodNotFoundError
    return method


def update_payment_method(
    session: Session,
    *,
    household_id: UUID,
    user_id: UUID,
    payment_method_id: UUID,
    changes: dict[str, object],
) -> PaymentMethod:
    method = get_payment_method(
        session,
        household_id=household_id,
        user_id=user_id,
        payment_method_id=payment_method_id,
        for_update=True,
    )
    try:
        with session.begin_nested():
            for field_name, value in changes.items():
                setattr(method, field_name, value)
            session.flush()
    except IntegrityError as exc:
        raise PaymentMethodConflictError from exc
    session.refresh(method)
    return method


def deactivate_payment_method(
    session: Session,
    *,
    household_id: UUID,
    user_id: UUID,
    payment_method_id: UUID,
) -> PaymentMethod:
    method = get_payment_method(
        session,
        household_id=household_id,
        user_id=user_id,
        payment_method_id=payment_method_id,
        for_update=True,
    )
    if method.is_active:
        method.is_active = False
        session.flush()
        session.refresh(method)
    return method
