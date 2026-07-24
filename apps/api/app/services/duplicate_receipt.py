from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
import re
import unicodedata
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Receipt


@dataclass(frozen=True)
class DuplicateMatch:
    receipt_id: UUID
    level: str
    reason: str


def normalize_receipt_number(value: str | None) -> str | None:
    if not value:
        return None
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^a-z0-9]", "", normalized)
    return normalized or None


def find_duplicate_receipt(
    session: Session,
    *,
    household_id: UUID,
    merchant_id: UUID | None,
    purchase_date: date | None,
    transaction_time: time | None,
    total: Decimal | None,
    currency: str | None,
    receipt_number: str | None,
    exclude_receipt_id: UUID | None = None,
) -> DuplicateMatch | None:
    if merchant_id is None or purchase_date is None:
        return None
    statement = select(Receipt).where(
        Receipt.household_id == household_id,
        Receipt.merchant_id == merchant_id,
        Receipt.purchase_date == purchase_date,
        Receipt.status != "voided",
    )
    if exclude_receipt_id is not None:
        statement = statement.where(Receipt.id != exclude_receipt_id)
    candidates = session.scalars(statement).all()
    normalized_number = normalize_receipt_number(receipt_number)
    for candidate in candidates:
        if normalized_number and candidate.normalized_receipt_number == normalized_number:
            return DuplicateMatch(
                candidate.id, "strong",
                "Same merchant branch, purchase date and receipt number",
            )
    for candidate in candidates:
        if (
            transaction_time is not None
            and candidate.purchase_time == transaction_time
            and total is not None
            and candidate.stated_total == total
            and (currency is None or candidate.currency == currency)
        ):
            return DuplicateMatch(
                candidate.id, "strong",
                "Same merchant branch, date, time and total",
            )
    for candidate in candidates:
        if (
            total is not None
            and candidate.stated_total == total
            and (currency is None or candidate.currency == currency)
        ):
            return DuplicateMatch(
                candidate.id, "possible",
                "Same merchant branch, purchase date and total; verify before saving",
            )
    return None
