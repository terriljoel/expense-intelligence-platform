import unicodedata
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Merchant


class MerchantAlreadyExistsError(Exception):
    """Raised when a household already has the normalized merchant name."""


def normalize_merchant_name(name: str) -> str:
    cleaned = " ".join(name.split())
    return unicodedata.normalize("NFKC", cleaned).casefold()


def create_merchant(
    session: Session,
    *,
    household_id: UUID,
    name: str,
) -> Merchant:
    normalized_name = normalize_merchant_name(name)
    existing = session.scalar(
        select(Merchant).where(
            Merchant.household_id == household_id,
            Merchant.normalized_name == normalized_name,
        )
    )
    if existing is not None:
        raise MerchantAlreadyExistsError

    merchant = Merchant(
        household_id=household_id,
        name=" ".join(name.split()),
        normalized_name=normalized_name,
    )
    session.add(merchant)

    try:
        session.flush()
    except IntegrityError as exc:
        raise MerchantAlreadyExistsError from exc

    return merchant


def list_merchants(session: Session, *, household_id: UUID) -> list[Merchant]:
    return list(
        session.scalars(
            select(Merchant)
            .where(Merchant.household_id == household_id)
            .order_by(Merchant.normalized_name)
        )
    )
