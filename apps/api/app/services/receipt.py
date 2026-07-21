from datetime import date
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    Merchant,
    PaymentMethod,
    Receipt,
    ReceiptItem,
    ReceiptPayment,
)


class MerchantNotFoundError(Exception):
    """Raised when the selected merchant is outside the household or missing."""


class ReceiptNotFoundError(Exception):
    """Raised when a receipt is outside the household or missing."""


class ReceiptNotEditableError(Exception):
    """Raised when line items are changed after the draft stage."""


class ReceiptItemPositionConflictError(Exception):
    """Raised when a receipt already contains the requested position."""


class PaymentMethodNotFoundError(Exception):
    """Raised when the selected payment method is unavailable to the user."""


class ReceiptPaymentConflictError(Exception):
    """Raised when the same payment method is used twice on one receipt."""


class ReceiptNotReconciledError(Exception):
    """Raised when approval is attempted before totals reconcile."""


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

    receipt = Receipt(
        household_id=household_id,
        merchant_id=merchant_id,
        created_by_user_id=created_by_user_id,
        purchase_date=purchase_date,
        currency=currency,
        stated_total=stated_total,
        status="draft",
        source="manual",
        notes=notes,
    )
    session.add(receipt)
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
        },
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
    receipt = get_receipt(
        session,
        household_id=household_id,
        receipt_id=receipt_id,
        for_update=True,
    )
    if receipt.status != "draft":
        raise ReceiptNotEditableError

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


def add_receipt_payment(
    session: Session,
    *,
    household_id: UUID,
    receipt_id: UUID,
    user_id: UUID,
    payment_method_id: UUID,
    amount: Decimal,
) -> ReceiptPayment:
    receipt = get_receipt(
        session,
        household_id=household_id,
        receipt_id=receipt_id,
        for_update=True,
    )
    if receipt.status != "draft":
        raise ReceiptNotEditableError

    payment_method = session.scalar(
        select(PaymentMethod).where(
            PaymentMethod.id == payment_method_id,
            PaymentMethod.household_id == household_id,
            PaymentMethod.user_id == user_id,
            PaymentMethod.is_active.is_(True),
        )
    )
    if payment_method is None:
        raise PaymentMethodNotFoundError

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


def list_receipts(
    session: Session,
    *,
    household_id: UUID,
    limit: int = 50,
    offset: int = 0,
) -> list[Receipt]:
    return list(
        session.scalars(
            select(Receipt)
            .where(Receipt.household_id == household_id)
            .order_by(Receipt.purchase_date.desc(), Receipt.created_at.desc())
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
    receipt = get_receipt(
        session,
        household_id=household_id,
        receipt_id=receipt_id,
        for_update=True,
    )
    if receipt.status != "draft":
        raise ReceiptNotEditableError

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
