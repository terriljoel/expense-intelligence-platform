from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PaymentMethod


def list_active_payment_methods(
    session: Session,
    *,
    household_id: UUID,
    user_id: UUID,
) -> list[PaymentMethod]:
    return list(
        session.scalars(
            select(PaymentMethod)
            .where(
                PaymentMethod.household_id == household_id,
                PaymentMethod.user_id == user_id,
                PaymentMethod.is_active.is_(True),
            )
            .order_by(PaymentMethod.name)
        )
    )
