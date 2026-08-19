from datetime import date
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    Merchant,
    Receipt,
    ReceiptCapture,
    ReceiptItem,
    ReceiptPayment,
)
from app.services.merchant import (
    normalize_merchant_address,
    normalize_merchant_name,
)
from app.services.duplicate_receipt import (
    DuplicateMatch,
    find_duplicate_receipt,
    normalize_receipt_number,
)
from app.services.payment_method import (
    PaymentMethodNotFoundError as PaymentMethodNotFoundError,
    get_payment_method,
)
from app.services.text_normalization import normalize_receipt_item


class MerchantNotFoundError(Exception):
    """Raised when the selected merchant is outside the household or missing."""


class ReceiptNotFoundError(Exception):
    """Raised when a receipt is outside the household or missing."""


class ReceiptNotEditableError(Exception):
    """Raised when line items are changed after the draft stage."""


class ReceiptItemPositionConflictError(Exception):
    """Raised when a receipt already contains the requested position."""


class ReceiptItemNotFoundError(Exception):
    """Raised when an item is missing or outside the selected receipt."""


class ReceiptItemAmountError(Exception):
    """Raised when an updated line type and amount have an invalid sign."""


class ReceiptPaymentConflictError(Exception):
    """Raised when the same payment method is used twice on one receipt."""


class ReceiptPaymentNotFoundError(Exception):
    """Raised when a payment is missing or outside the selected receipt."""


class ReceiptNotReconciledError(Exception):
    """Raised when approval is attempted before totals reconcile."""


class ReceiptNotVoidableError(Exception):
    """Raised when a receipt cannot transition to the voided state."""


class ReceiptCaptureNotFoundError(Exception):
    """Raised when the selected capture is unavailable to the household."""


class ReceiptCaptureNotReadyError(Exception):
    """Raised when OCR has not completed or failed for a capture."""


class ReceiptCaptureAlreadyUsedError(Exception):
    """Raised when the capture is already linked to a receipt."""


class DuplicateReceiptError(Exception):
    """Raised when strong business fields match an existing receipt."""

    def __init__(self, match: DuplicateMatch) -> None:
        self.match = match
        super().__init__(match.reason)


def _audit_value(value: object) -> object:
    if isinstance(value, (date, Decimal, UUID)):
        return str(value)
    return value


def _field_changes(
    record: object,
    changes: dict[str, object],
) -> dict[str, dict[str, object]]:
    return {
        field_name: {
            "old": _audit_value(getattr(record, field_name)),
            "new": _audit_value(value),
        }
        for field_name, value in changes.items()
        if getattr(record, field_name) != value
    }


def _validate_item_amount(line_type: str, line_total: Decimal) -> None:
    if line_type == "discount" and line_total > 0:
        raise ReceiptItemAmountError
    if line_type in {"product", "deposit", "fee", "tax"} and line_total < 0:
        raise ReceiptItemAmountError


def record_audit_event(
    session: Session,
    *,
    household_id: UUID,
    actor_user_id: UUID,
    receipt_id: UUID,
    event_type: str,
    event_data: dict[str, object] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        household_id=household_id,
        actor_user_id=actor_user_id,
        receipt_id=receipt_id,
        event_type=event_type,
        event_data=event_data or {},
    )
    session.add(event)
    session.flush()
    return event


@dataclass(frozen=True)
class ReceiptReconciliation:
    receipt_id: UUID
    stated_total: Decimal
    item_total: Decimal
    payment_total: Decimal
    item_difference: Decimal
    payment_difference: Decimal
    item_count: int
    payment_count: int
    is_reconciled: bool


def create_receipt(
    session: Session,
    *,
    household_id: UUID,
    created_by_user_id: UUID,
    merchant_id: UUID | None,
    purchase_date: date,
    currency: str,
    stated_total: Decimal,
    notes: str | None,
    capture_id: UUID | None = None,
    payment_method_id: UUID | None = None,
    payment_user_id: UUID | None = None,
    category: str = "other",
    receipt_number: str | None = None,
) -> Receipt:
    if merchant_id is not None:
        merchant_exists = session.scalar(
            select(Merchant.id).where(
                Merchant.id == merchant_id,
                Merchant.household_id == household_id,
            )
        )
        if merchant_exists is None:
            raise MerchantNotFoundError

    capture: ReceiptCapture | None = None
    if capture_id is not None:
        capture = session.scalar(
            select(ReceiptCapture)
            .where(
                ReceiptCapture.id == capture_id,
                ReceiptCapture.household_id == household_id,
            )
            .with_for_update()
        )
        if capture is None:
            raise ReceiptCaptureNotFoundError
        if capture.receipt_id is not None:
            raise ReceiptCaptureAlreadyUsedError
        if capture.ocr_status not in {"succeeded", "failed"}:
            raise ReceiptCaptureNotReadyError

        if merchant_id is None and capture.suggested_merchant_name:
            normalized_name = normalize_merchant_name(capture.suggested_merchant_name)
            normalized_address = normalize_merchant_address(
                capture.suggested_merchant_address
            )
            merchant = session.scalar(
                select(Merchant).where(
                    Merchant.household_id == household_id,
                    Merchant.normalized_name == normalized_name,
                    Merchant.normalized_address == normalized_address,
                )
            )
            if merchant is None:
                merchant = Merchant(
                    household_id=household_id,
                    name=" ".join(capture.suggested_merchant_name.split()),
                    normalized_name=normalized_name,
                    address=(
                        " ".join(capture.suggested_merchant_address.split())
                        if capture.suggested_merchant_address
                        else None
                    ),
                    normalized_address=normalized_address,
                )
                session.add(merchant)
                session.flush()
            merchant_id = merchant.id

    if receipt_number is None and capture is not None:
        receipt_number = capture.suggested_receipt_number
    duplicate = find_duplicate_receipt(
        session,
        household_id=household_id,
        merchant_id=merchant_id,
        purchase_date=purchase_date,
        transaction_time=(capture.suggested_transaction_time if capture else None),
        total=stated_total,
        currency=currency,
        receipt_number=receipt_number,
    )
    if duplicate is not None and duplicate.level == "strong":
        raise DuplicateReceiptError(duplicate)

    receipt = Receipt(
        household_id=household_id,
        merchant_id=merchant_id,
        created_by_user_id=created_by_user_id,
        purchase_date=purchase_date,
        purchase_time=(capture.suggested_transaction_time if capture else None),
        merchant_address=(capture.suggested_merchant_address if capture else None),
        merchant_phone=(capture.suggested_merchant_phone if capture else None),
        currency=currency,
        stated_total=stated_total,
        subtotal=(capture.suggested_subtotal if capture else None),
        tax_amount=(capture.suggested_tax if capture else None),
        tip_amount=(capture.suggested_tip if capture else None),
        status="draft",
        source="image" if capture is not None else "manual",
        category=category,
        image_object_key=(capture.image_object_key if capture else None),
        image_sha256=(capture.image_sha256 if capture else None),
        notes=notes,
        receipt_number=receipt_number,
        normalized_receipt_number=normalize_receipt_number(receipt_number),
    )
    session.add(receipt)
    session.flush()
    if capture is not None:
        capture.receipt_id = receipt.id
        session.flush()
    record_audit_event(
        session,
        household_id=household_id,
        actor_user_id=created_by_user_id,
        receipt_id=receipt.id,
        event_type="receipt_created",
        event_data={
            "stated_total": str(receipt.stated_total),
            "currency": receipt.currency,
            "source": receipt.source,
            "capture_id": str(capture.id) if capture is not None else None,
        },
    )

    if capture is not None:
        for position, item in enumerate(capture.suggested_items or [], start=1):
            line_total = Decimal(str(item["line_total"]))
            add_receipt_item(
                session,
                household_id=household_id,
                receipt_id=receipt.id,
                actor_user_id=created_by_user_id,
                position=position,
                line_type=str(
                    item.get("line_type")
                    or ("discount" if line_total < 0 else "product")
                ),
                raw_description=str(item["description"]),
                description=str(item["description"]),
                raw_quantity_text=(
                    str(item["quantity"]) if item.get("quantity") is not None else None
                ),
                quantity=(
                    Decimal(str(item["quantity"]))
                    if item.get("quantity") is not None
                    else None
                ),
                unit_price=(
                    Decimal(str(item["unit_price"]))
                    if item.get("unit_price") is not None
                    else None
                ),
                line_total=line_total,
            )

    selected_method = (
        get_payment_method(
            session,
            household_id=household_id,
            user_id=payment_user_id or created_by_user_id,
            payment_method_id=payment_method_id,
            active_only=True,
        )
        if payment_method_id is not None
        else None
    )
    if selected_method is not None and stated_total > 0:
        add_receipt_payment(
            session,
            household_id=household_id,
            receipt_id=receipt.id,
            user_id=selected_method.user_id,
            payment_method_id=selected_method.id,
            amount=stated_total,
        )
    return receipt


def get_receipt(
    session: Session,
    *,
    household_id: UUID,
    receipt_id: UUID,
    for_update: bool = False,
) -> Receipt:
    statement = select(Receipt).where(
        Receipt.id == receipt_id,
        Receipt.household_id == household_id,
    )
    if for_update:
        statement = statement.with_for_update()
    receipt = session.scalar(statement)
    if receipt is None:
        raise ReceiptNotFoundError
    return receipt


def _get_editable_receipt(
    session: Session,
    *,
    household_id: UUID,
    receipt_id: UUID,
) -> Receipt:
    receipt = get_receipt(
        session,
        household_id=household_id,
        receipt_id=receipt_id,
        for_update=True,
    )
    if receipt.status != "draft":
        raise ReceiptNotEditableError
    return receipt


def update_receipt(
    session: Session,
    *,
    household_id: UUID,
    receipt_id: UUID,
    actor_user_id: UUID,
    changes: dict[str, object],
) -> Receipt:
    receipt = _get_editable_receipt(
        session, household_id=household_id, receipt_id=receipt_id
    )

    if "merchant_id" in changes and changes["merchant_id"] is not None:
        merchant_exists = session.scalar(
            select(Merchant.id).where(
                Merchant.id == changes["merchant_id"],
                Merchant.household_id == household_id,
            )
        )
        if merchant_exists is None:
            raise MerchantNotFoundError

    if "receipt_number" in changes:
        changes["normalized_receipt_number"] = normalize_receipt_number(
            changes["receipt_number"]
            if isinstance(changes["receipt_number"], str)
            else None
        )
    candidate_duplicate = find_duplicate_receipt(
        session,
        household_id=household_id,
        merchant_id=changes.get("merchant_id", receipt.merchant_id),
        purchase_date=changes.get("purchase_date", receipt.purchase_date),
        transaction_time=receipt.purchase_time,
        total=changes.get("stated_total", receipt.stated_total),
        currency=changes.get("currency", receipt.currency),
        receipt_number=changes.get("receipt_number", receipt.receipt_number),
        exclude_receipt_id=receipt.id,
    )
    if candidate_duplicate is not None and candidate_duplicate.level == "strong":
        raise DuplicateReceiptError(candidate_duplicate)

    changed_fields = _field_changes(receipt, changes)
    for field_name in changed_fields:
        setattr(receipt, field_name, changes[field_name])
    if changed_fields:
        session.flush()
        session.refresh(receipt)
        record_audit_event(
            session,
            household_id=household_id,
            actor_user_id=actor_user_id,
            receipt_id=receipt_id,
            event_type="receipt_updated",
            event_data={"changes": changed_fields},
        )
    return receipt


def add_receipt_item(
    session: Session,
    *,
    household_id: UUID,
    receipt_id: UUID,
    actor_user_id: UUID,
    position: int,
    line_type: str,
    raw_description: str | None,
    description: str,
    raw_quantity_text: str | None,
    quantity: Decimal | None,
    unit_price: Decimal | None,
    line_total: Decimal,
) -> ReceiptItem:
    _validate_item_amount(line_type, line_total)
    _get_editable_receipt(
        session, household_id=household_id, receipt_id=receipt_id
    )

    existing_position = session.scalar(
        select(ReceiptItem.id).where(
            ReceiptItem.receipt_id == receipt_id,
            ReceiptItem.position == position,
        )
    )
    if existing_position is not None:
        raise ReceiptItemPositionConflictError

    item = ReceiptItem(
        household_id=household_id,
        receipt_id=receipt_id,
        position=position,
        line_type=line_type,
        raw_description=raw_description,
        description=description,
        normalized_description=normalize_receipt_item(description),
        raw_quantity_text=raw_quantity_text,
        quantity=quantity,
        unit_price=unit_price,
        line_total=line_total,
    )
    session.add(item)
    session.flush()
    record_audit_event(
        session,
        household_id=household_id,
        actor_user_id=actor_user_id,
        receipt_id=receipt_id,
        event_type="item_added",
        event_data={
            "item_id": str(item.id),
            "position": item.position,
            "line_type": item.line_type,
            "line_total": str(item.line_total),
        },
    )
    return item


def list_receipt_items(
    session: Session,
    *,
    household_id: UUID,
    receipt_id: UUID,
) -> list[ReceiptItem]:
    get_receipt(
        session,
        household_id=household_id,
        receipt_id=receipt_id,
    )
    return list(
        session.scalars(
            select(ReceiptItem)
            .where(
                ReceiptItem.receipt_id == receipt_id,
                ReceiptItem.household_id == household_id,
            )
            .order_by(ReceiptItem.position)
        )
    )


def get_receipt_item(
    session: Session,
    *,
    household_id: UUID,
    receipt_id: UUID,
    item_id: UUID,
    for_update: bool = False,
) -> ReceiptItem:
    statement = select(ReceiptItem).where(
        ReceiptItem.id == item_id,
        ReceiptItem.receipt_id == receipt_id,
        ReceiptItem.household_id == household_id,
    )
    if for_update:
        statement = statement.with_for_update()
    item = session.scalar(statement)
    if item is None:
        raise ReceiptItemNotFoundError
    return item


def update_receipt_item(
    session: Session,
    *,
    household_id: UUID,
    receipt_id: UUID,
    item_id: UUID,
    actor_user_id: UUID,
    changes: dict[str, object],
) -> ReceiptItem:
    _get_editable_receipt(
        session, household_id=household_id, receipt_id=receipt_id
    )
    item = get_receipt_item(
        session,
        household_id=household_id,
        receipt_id=receipt_id,
        item_id=item_id,
        for_update=True,
    )

    new_position = changes.get("position", item.position)
    if new_position != item.position:
        position_exists = session.scalar(
            select(ReceiptItem.id).where(
                ReceiptItem.receipt_id == receipt_id,
                ReceiptItem.position == new_position,
                ReceiptItem.id != item_id,
            )
        )
        if position_exists is not None:
            raise ReceiptItemPositionConflictError

    new_line_type = str(changes.get("line_type", item.line_type))
    new_line_total = changes.get("line_total", item.line_total)
    if not isinstance(new_line_total, Decimal):
        new_line_total = Decimal(str(new_line_total))
    _validate_item_amount(new_line_type, new_line_total)

    changed_fields = _field_changes(item, changes)
    if "description" in changed_fields:
        changes["normalized_description"] = normalize_receipt_item(
            str(changes["description"])
        )
        changes["product_id"] = None
        changes["product_match_status"] = "unmatched"
        changes["product_match_method"] = None
        changes["product_match_confidence"] = None
        changed_fields.update(
            _field_changes(
                item,
                {
                    field_name: changes[field_name]
                    for field_name in (
                        "normalized_description",
                        "product_id",
                        "product_match_status",
                        "product_match_method",
                        "product_match_confidence",
                    )
                },
            )
        )
    for field_name in changed_fields:
        setattr(item, field_name, changes[field_name])
    if changed_fields:
        session.flush()
        session.refresh(item)
        record_audit_event(
            session,
            household_id=household_id,
            actor_user_id=actor_user_id,
            receipt_id=receipt_id,
            event_type="item_updated",
            event_data={
                "item_id": str(item_id),
                "changes": changed_fields,
            },
        )
    return item


def remove_receipt_item(
    session: Session,
    *,
    household_id: UUID,
    receipt_id: UUID,
    item_id: UUID,
    actor_user_id: UUID,
) -> None:
    _get_editable_receipt(
        session, household_id=household_id, receipt_id=receipt_id
    )
    item = get_receipt_item(
        session,
        household_id=household_id,
        receipt_id=receipt_id,
        item_id=item_id,
        for_update=True,
    )
    snapshot = {
        "item_id": str(item.id),
        "position": item.position,
        "line_type": item.line_type,
        "description": item.description,
        "line_total": str(item.line_total),
    }
    session.delete(item)
    session.flush()
    record_audit_event(
        session,
        household_id=household_id,
        actor_user_id=actor_user_id,
        receipt_id=receipt_id,
        event_type="item_removed",
        event_data=snapshot,
    )


def add_receipt_payment(
    session: Session,
    *,
    household_id: UUID,
    receipt_id: UUID,
    user_id: UUID,
    payment_method_id: UUID,
    amount: Decimal,
) -> ReceiptPayment:
    _get_editable_receipt(
        session, household_id=household_id, receipt_id=receipt_id
    )

    get_payment_method(
        session,
        household_id=household_id,
        user_id=user_id,
        payment_method_id=payment_method_id,
        active_only=True,
    )

    existing_payment = session.scalar(
        select(ReceiptPayment.id).where(
            ReceiptPayment.receipt_id == receipt_id,
            ReceiptPayment.user_id == user_id,
            ReceiptPayment.payment_method_id == payment_method_id,
        )
    )
    if existing_payment is not None:
        raise ReceiptPaymentConflictError

    payment = ReceiptPayment(
        household_id=household_id,
        receipt_id=receipt_id,
        user_id=user_id,
        payment_method_id=payment_method_id,
        amount=amount,
    )
    session.add(payment)
    session.flush()
    record_audit_event(
        session,
        household_id=household_id,
        actor_user_id=user_id,
        receipt_id=receipt_id,
        event_type="payment_added",
        event_data={
            "payment_id": str(payment.id),
            "payment_method_id": str(payment_method_id),
            "amount": str(payment.amount),
        },
    )
    return payment


def list_receipt_payments(
    session: Session,
    *,
    household_id: UUID,
    receipt_id: UUID,
) -> list[ReceiptPayment]:
    get_receipt(
        session,
        household_id=household_id,
        receipt_id=receipt_id,
    )
    return list(
        session.scalars(
            select(ReceiptPayment)
            .where(
                ReceiptPayment.receipt_id == receipt_id,
                ReceiptPayment.household_id == household_id,
            )
            .order_by(ReceiptPayment.created_at, ReceiptPayment.id)
        )
    )


def get_receipt_payment(
    session: Session,
    *,
    household_id: UUID,
    receipt_id: UUID,
    user_id: UUID | None,
    payment_id: UUID,
    for_update: bool = False,
) -> ReceiptPayment:
    statement = select(ReceiptPayment).where(
        ReceiptPayment.id == payment_id,
        ReceiptPayment.receipt_id == receipt_id,
        ReceiptPayment.household_id == household_id,
    )
    if user_id is not None:
        statement = statement.where(ReceiptPayment.user_id == user_id)
    if for_update:
        statement = statement.with_for_update()
    payment = session.scalar(statement)
    if payment is None:
        raise ReceiptPaymentNotFoundError
    return payment


def update_receipt_payment(
    session: Session,
    *,
    household_id: UUID,
    receipt_id: UUID,
    payment_id: UUID,
    user_id: UUID | None,
    actor_user_id: UUID,
    changes: dict[str, object],
) -> ReceiptPayment:
    _get_editable_receipt(
        session, household_id=household_id, receipt_id=receipt_id
    )
    payment = get_receipt_payment(
        session,
        household_id=household_id,
        receipt_id=receipt_id,
        user_id=user_id,
        payment_id=payment_id,
        for_update=True,
    )

    new_method_id = changes.get("payment_method_id", payment.payment_method_id)
    new_user_id = changes.get("user_id", payment.user_id)
    if new_method_id != payment.payment_method_id or new_user_id != payment.user_id:
        get_payment_method(
            session,
            household_id=household_id,
            user_id=new_user_id,
            payment_method_id=new_method_id,
            active_only=True,
        )
        duplicate = session.scalar(
            select(ReceiptPayment.id).where(
                ReceiptPayment.receipt_id == receipt_id,
                ReceiptPayment.user_id == new_user_id,
                ReceiptPayment.payment_method_id == new_method_id,
                ReceiptPayment.id != payment_id,
            )
        )
        if duplicate is not None:
            raise ReceiptPaymentConflictError

    changed_fields = _field_changes(payment, changes)
    for field_name in changed_fields:
        setattr(payment, field_name, changes[field_name])
    if changed_fields:
        session.flush()
        record_audit_event(
            session,
            household_id=household_id,
            actor_user_id=actor_user_id,
            receipt_id=receipt_id,
            event_type="payment_updated",
            event_data={
                "payment_id": str(payment_id),
                "changes": changed_fields,
            },
        )
    return payment


def remove_receipt_payment(
    session: Session,
    *,
    household_id: UUID,
    receipt_id: UUID,
    payment_id: UUID,
    user_id: UUID | None,
    actor_user_id: UUID,
) -> None:
    _get_editable_receipt(
        session, household_id=household_id, receipt_id=receipt_id
    )
    payment = get_receipt_payment(
        session,
        household_id=household_id,
        receipt_id=receipt_id,
        user_id=user_id,
        payment_id=payment_id,
        for_update=True,
    )
    snapshot = {
        "payment_id": str(payment.id),
        "payment_method_id": (
            str(payment.payment_method_id)
            if payment.payment_method_id is not None
            else None
        ),
        "amount": str(payment.amount),
    }
    session.delete(payment)
    session.flush()
    record_audit_event(
        session,
        household_id=household_id,
        actor_user_id=actor_user_id,
        receipt_id=receipt_id,
        event_type="payment_removed",
        event_data=snapshot,
    )


def list_receipts(
    session: Session,
    *,
    household_id: UUID,
    limit: int = 50,
    offset: int = 0,
    query: str | None = None,
) -> list[Receipt]:
    statement = select(Receipt).where(Receipt.household_id == household_id)
    if query and (term := query.strip()):
        pattern = f"%{term}%"
        statement = statement.where(
            or_(
                Receipt.category.ilike(pattern),
                Receipt.notes.ilike(pattern),
                Receipt.receipt_number.ilike(pattern),
                exists().where(
                    Merchant.id == Receipt.merchant_id,
                    Merchant.name.ilike(pattern),
                ),
                exists().where(
                    ReceiptItem.receipt_id == Receipt.id,
                    ReceiptItem.description.ilike(pattern),
                ),
            )
        )
    return list(
        session.scalars(
            statement.order_by(Receipt.purchase_date.desc(), Receipt.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )


def list_receipt_audit_events(
    session: Session,
    *,
    household_id: UUID,
    receipt_id: UUID,
) -> list[AuditEvent]:
    get_receipt(
        session,
        household_id=household_id,
        receipt_id=receipt_id,
    )
    return list(
        session.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.receipt_id == receipt_id,
                AuditEvent.household_id == household_id,
            )
            .order_by(AuditEvent.sequence_number)
        )
    )


def reconcile_receipt(
    session: Session,
    *,
    household_id: UUID,
    receipt_id: UUID,
) -> ReceiptReconciliation:
    receipt = get_receipt(
        session,
        household_id=household_id,
        receipt_id=receipt_id,
    )

    item_total, item_count = session.execute(
        select(
            func.coalesce(func.sum(ReceiptItem.line_total), 0),
            func.count(ReceiptItem.id),
        ).where(
            ReceiptItem.receipt_id == receipt_id,
            ReceiptItem.household_id == household_id,
        )
    ).one()
    payment_total, payment_count = session.execute(
        select(
            func.coalesce(func.sum(ReceiptPayment.amount), 0),
            func.count(ReceiptPayment.id),
        ).where(
            ReceiptPayment.receipt_id == receipt_id,
            ReceiptPayment.household_id == household_id,
        )
    ).one()

    item_total = Decimal(item_total).quantize(Decimal("0.01"))
    payment_total = Decimal(payment_total).quantize(Decimal("0.01"))
    item_difference = receipt.stated_total - item_total
    payment_difference = receipt.stated_total - payment_total
    is_reconciled = (
        item_count > 0
        and payment_count > 0
        and item_difference == 0
        and payment_difference == 0
    )

    return ReceiptReconciliation(
        receipt_id=receipt.id,
        stated_total=receipt.stated_total,
        item_total=item_total,
        payment_total=payment_total,
        item_difference=item_difference,
        payment_difference=payment_difference,
        item_count=item_count,
        payment_count=payment_count,
        is_reconciled=is_reconciled,
    )


def approve_receipt(
    session: Session,
    *,
    household_id: UUID,
    receipt_id: UUID,
    actor_user_id: UUID,
) -> Receipt:
    receipt = _get_editable_receipt(
        session, household_id=household_id, receipt_id=receipt_id
    )

    reconciliation = reconcile_receipt(
        session,
        household_id=household_id,
        receipt_id=receipt_id,
    )
    if not reconciliation.is_reconciled:
        raise ReceiptNotReconciledError

    receipt.status = "approved"
    receipt.approved_at = func.now()
    session.flush()
    session.refresh(receipt)
    record_audit_event(
        session,
        household_id=household_id,
        actor_user_id=actor_user_id,
        receipt_id=receipt_id,
        event_type="receipt_approved",
        event_data={"stated_total": str(receipt.stated_total)},
    )
    return receipt


def reopen_receipt(
    session: Session,
    *,
    household_id: UUID,
    receipt_id: UUID,
    actor_user_id: UUID,
) -> Receipt:
    receipt = get_receipt(
        session,
        household_id=household_id,
        receipt_id=receipt_id,
        for_update=True,
    )
    if receipt.status != "approved":
        raise ReceiptNotEditableError
    receipt.status = "draft"
    receipt.approved_at = None
    session.flush()
    record_audit_event(
        session,
        household_id=household_id,
        actor_user_id=actor_user_id,
        receipt_id=receipt_id,
        event_type="receipt_updated",
        event_data={"changes": {"status": {"from": "approved", "to": "draft"}}},
    )
    return receipt


def void_receipt(
    session: Session,
    *,
    household_id: UUID,
    receipt_id: UUID,
    actor_user_id: UUID,
    reason: str | None,
) -> Receipt:
    receipt = get_receipt(
        session,
        household_id=household_id,
        receipt_id=receipt_id,
        for_update=True,
    )
    if receipt.status not in {"draft", "approved"}:
        raise ReceiptNotVoidableError

    previous_status = receipt.status
    receipt.status = "voided"
    receipt.voided_at = func.now()
    session.flush()
    session.refresh(receipt)
    record_audit_event(
        session,
        household_id=household_id,
        actor_user_id=actor_user_id,
        receipt_id=receipt_id,
        event_type="receipt_voided",
        event_data={
            "previous_status": previous_status,
            "reason": reason,
        },
    )
    return receipt
