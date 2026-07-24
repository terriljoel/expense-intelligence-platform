from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from io import BytesIO
import json
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import delete, func, select, text
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    Household,
    HouseholdMember,
    IncomeEntry,
    Merchant,
    PaymentMethod,
    Receipt,
    ReceiptCapture,
    ReceiptItem,
    ReceiptPayment,
    User,
)
from app.schemas.maintenance import MaintenanceCounts
from app.services.receipt_image_storage import (
    ReceiptImageNotFoundError,
    ReceiptImageStorage,
    ReceiptImageStorageError,
)


class HouseholdNotFoundError(Exception):
    pass


class ResetConfirmationError(Exception):
    pass


def _household(session: Session, household_id: UUID) -> Household:
    household = session.get(Household, household_id)
    if household is None:
        raise HouseholdNotFoundError
    return household


def confirmation_phrase(household_name: str) -> str:
    return f"RESET {household_name}"


def maintenance_counts(
    session: Session, *, household_id: UUID
) -> MaintenanceCounts:
    models = {
        "receipts": Receipt,
        "receipt_items": ReceiptItem,
        "receipt_payments": ReceiptPayment,
        "receipt_captures": ReceiptCapture,
        "income_entries": IncomeEntry,
        "audit_events": AuditEvent,
    }
    values = {
        name: session.scalar(
            select(func.count()).select_from(model).where(
                model.household_id == household_id
            )
        )
        or 0
        for name, model in models.items()
    }
    return MaintenanceCounts(**values)


def maintenance_preview(
    session: Session, *, household_id: UUID
) -> tuple[Household, MaintenanceCounts]:
    household = _household(session, household_id)
    return household, maintenance_counts(session, household_id=household_id)


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date, time, UUID, Decimal)):
        return str(value)
    return value


def _row(record: object) -> dict[str, Any]:
    return {
        column.key: _json_value(getattr(record, column.key))
        for column in inspect(record).mapper.column_attrs
    }


def _rows(session: Session, model: type, household_id: UUID) -> list[dict[str, Any]]:
    records = session.scalars(
        select(model).where(model.household_id == household_id)
    ).all()
    return [_row(record) for record in records]


def build_household_archive(
    session: Session,
    *,
    household_id: UUID,
    storage: ReceiptImageStorage,
) -> tuple[bytes, str]:
    household = _household(session, household_id)
    members = session.execute(
        select(HouseholdMember, User)
        .join(User, User.id == HouseholdMember.user_id)
        .where(HouseholdMember.household_id == household_id)
    ).all()
    captures = session.scalars(
        select(ReceiptCapture).where(ReceiptCapture.household_id == household_id)
    ).all()
    exported_at = datetime.now().astimezone()
    payload = {
        "format": "expense-intelligence-household-archive-v1",
        "exported_at": exported_at.isoformat(),
        "household": _row(household),
        "members": [
            {
                **_row(membership),
                "email": user.email,
                "display_name": user.display_name,
            }
            for membership, user in members
        ],
        "retained_reference_data": {
            "merchants": _rows(session, Merchant, household_id),
            "payment_methods": _rows(session, PaymentMethod, household_id),
        },
        "transactional_data": {
            "receipts": _rows(session, Receipt, household_id),
            "receipt_items": _rows(session, ReceiptItem, household_id),
            "receipt_payments": _rows(session, ReceiptPayment, household_id),
            "receipt_captures": [_row(capture) for capture in captures],
            "income_entries": _rows(session, IncomeEntry, household_id),
            "audit_events": _rows(session, AuditEvent, household_id),
        },
        "image_export_errors": [],
    }
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for capture in captures:
            try:
                content = storage.get(capture.image_object_key)
                filename = PurePosixPath(capture.original_filename or "receipt-image").name
                archive.writestr(f"images/{capture.id}-{filename}", content)
            except ReceiptImageStorageError as exc:
                payload["image_export_errors"].append(
                    {
                        "capture_id": str(capture.id),
                        "object_key": capture.image_object_key,
                        "error": str(exc),
                    }
                )
        archive.writestr(
            "household-data.json",
            json.dumps(payload, ensure_ascii=False, indent=2, default=_json_value),
        )
    safe_date = exported_at.strftime("%Y%m%d-%H%M%S")
    return output.getvalue(), f"expense-intelligence-archive-{safe_date}.zip"


def reset_household_data(
    session: Session,
    *,
    household_id: UUID,
    supplied_confirmation: str,
    storage: ReceiptImageStorage,
) -> tuple[MaintenanceCounts, int, int, int]:
    household, counts = maintenance_preview(session, household_id=household_id)
    if supplied_confirmation != confirmation_phrase(household.name):
        raise ResetConfirmationError

    object_keys = list(
        dict.fromkeys(
            session.scalars(
                select(ReceiptCapture.image_object_key).where(
                    ReceiptCapture.household_id == household_id
                )
            ).all()
        )
    )
    session.execute(text("SET LOCAL app.allow_audit_purge = 'on'"))
    session.execute(delete(AuditEvent).where(AuditEvent.household_id == household_id))
    session.execute(
        delete(ReceiptCapture).where(ReceiptCapture.household_id == household_id)
    )
    session.execute(delete(Receipt).where(Receipt.household_id == household_id))
    session.execute(delete(IncomeEntry).where(IncomeEntry.household_id == household_id))
    session.commit()

    deleted = not_found = failures = 0
    for object_key in object_keys:
        try:
            storage.delete(object_key)
            deleted += 1
        except ReceiptImageNotFoundError:
            not_found += 1
        except ReceiptImageStorageError:
            failures += 1
    return counts, deleted, not_found, failures

