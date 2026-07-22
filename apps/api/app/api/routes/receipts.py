from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentPrincipal, get_current_principal
from app.db.session import get_db_session
from app.schemas.receipt import (
    AuditEventResponse,
    ReceiptCreate,
    ReceiptItemCreate,
    ReceiptItemResponse,
    ReceiptItemUpdate,
    ReceiptResponse,
    ReceiptUpdate,
    ReceiptVoidRequest,
)
from app.schemas.payment import (
    ReceiptPaymentCreate,
    ReceiptPaymentResponse,
    ReceiptPaymentUpdate,
    ReceiptReconciliationResponse,
)
from app.services.receipt import (
    MerchantNotFoundError,
    PaymentMethodNotFoundError,
    ReceiptItemPositionConflictError,
    ReceiptItemAmountError,
    ReceiptItemNotFoundError,
    ReceiptNotEditableError,
    ReceiptNotFoundError,
    ReceiptNotReconciledError,
    ReceiptNotVoidableError,
    ReceiptPaymentConflictError,
    ReceiptPaymentNotFoundError,
    add_receipt_item,
    add_receipt_payment,
    approve_receipt,
    create_receipt,
    get_receipt,
    list_receipt_items,
    list_receipt_audit_events,
    list_receipt_payments,
    list_receipts,
    reconcile_receipt,
    remove_receipt_item,
    remove_receipt_payment,
    update_receipt,
    update_receipt_item,
    update_receipt_payment,
    void_receipt,
)


router = APIRouter(prefix="/receipts", tags=["receipts"])


@router.post(
    "",
    response_model=ReceiptResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_receipt(
    payload: ReceiptCreate,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ReceiptResponse:
    try:
        receipt = create_receipt(
            session,
            household_id=principal.household_id,
            created_by_user_id=principal.user_id,
            merchant_id=payload.merchant_id,
            purchase_date=payload.purchase_date,
            currency=payload.currency,
            stated_total=payload.stated_total,
            notes=payload.notes,
        )
    except MerchantNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found in this household",
        ) from exc

    return ReceiptResponse.model_validate(receipt)


@router.get("", response_model=list[ReceiptResponse])
def get_receipts(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[ReceiptResponse]:
    receipts = list_receipts(
        session,
        household_id=principal.household_id,
        limit=limit,
        offset=offset,
    )
    return [ReceiptResponse.model_validate(receipt) for receipt in receipts]


@router.get("/{receipt_id}", response_model=ReceiptResponse)
def get_receipt_by_id(
    receipt_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ReceiptResponse:
    try:
        receipt = get_receipt(
            session,
            household_id=principal.household_id,
            receipt_id=receipt_id,
        )
    except ReceiptNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found",
        ) from exc

    return ReceiptResponse.model_validate(receipt)


@router.patch("/{receipt_id}", response_model=ReceiptResponse)
def patch_receipt(
    receipt_id: UUID,
    payload: ReceiptUpdate,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ReceiptResponse:
    try:
        receipt = update_receipt(
            session,
            household_id=principal.household_id,
            receipt_id=receipt_id,
            actor_user_id=principal.user_id,
            changes=payload.model_dump(exclude_unset=True),
        )
    except ReceiptNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found",
        ) from exc
    except MerchantNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found in this household",
        ) from exc
    except ReceiptNotEditableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft receipts can be edited",
        ) from exc
    return ReceiptResponse.model_validate(receipt)


@router.post(
    "/{receipt_id}/items",
    response_model=ReceiptItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_receipt_item(
    receipt_id: UUID,
    payload: ReceiptItemCreate,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ReceiptItemResponse:
    try:
        item = add_receipt_item(
            session,
            household_id=principal.household_id,
            receipt_id=receipt_id,
            actor_user_id=principal.user_id,
            position=payload.position,
            line_type=payload.line_type,
            raw_description=payload.raw_description,
            description=payload.description,
            raw_quantity_text=payload.raw_quantity_text,
            quantity=payload.quantity,
            unit_price=payload.unit_price,
            line_total=payload.line_total,
        )
    except ReceiptNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found",
        ) from exc
    except ReceiptNotEditableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft receipts can be edited",
        ) from exc
    except ReceiptItemPositionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Receipt item position already exists",
        ) from exc

    return ReceiptItemResponse.model_validate(item)


@router.get(
    "/{receipt_id}/items",
    response_model=list[ReceiptItemResponse],
)
def get_receipt_items(
    receipt_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[ReceiptItemResponse]:
    try:
        items = list_receipt_items(
            session,
            household_id=principal.household_id,
            receipt_id=receipt_id,
        )
    except ReceiptNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found",
        ) from exc

    return [ReceiptItemResponse.model_validate(item) for item in items]


@router.patch(
    "/{receipt_id}/items/{item_id}",
    response_model=ReceiptItemResponse,
)
def patch_receipt_item(
    receipt_id: UUID,
    item_id: UUID,
    payload: ReceiptItemUpdate,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ReceiptItemResponse:
    try:
        item = update_receipt_item(
            session,
            household_id=principal.household_id,
            receipt_id=receipt_id,
            item_id=item_id,
            actor_user_id=principal.user_id,
            changes=payload.model_dump(exclude_unset=True),
        )
    except ReceiptNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found",
        ) from exc
    except ReceiptItemNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt item not found",
        ) from exc
    except ReceiptNotEditableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft receipts can be edited",
        ) from exc
    except ReceiptItemPositionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Receipt item position already exists",
        ) from exc
    except ReceiptItemAmountError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Line type and line total have an invalid sign",
        ) from exc
    return ReceiptItemResponse.model_validate(item)


@router.delete(
    "/{receipt_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_receipt_item(
    receipt_id: UUID,
    item_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> None:
    try:
        remove_receipt_item(
            session,
            household_id=principal.household_id,
            receipt_id=receipt_id,
            item_id=item_id,
            actor_user_id=principal.user_id,
        )
    except ReceiptNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found",
        ) from exc
    except ReceiptItemNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt item not found",
        ) from exc
    except ReceiptNotEditableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft receipts can be edited",
        ) from exc


@router.post(
    "/{receipt_id}/payments",
    response_model=ReceiptPaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_receipt_payment(
    receipt_id: UUID,
    payload: ReceiptPaymentCreate,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ReceiptPaymentResponse:
    try:
        payment = add_receipt_payment(
            session,
            household_id=principal.household_id,
            receipt_id=receipt_id,
            user_id=principal.user_id,
            payment_method_id=payload.payment_method_id,
            amount=payload.amount,
        )
    except ReceiptNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found",
        ) from exc
    except PaymentMethodNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active payment method not found",
        ) from exc
    except ReceiptNotEditableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft receipts can be edited",
        ) from exc
    except ReceiptPaymentConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment method already used for this receipt",
        ) from exc

    return ReceiptPaymentResponse.model_validate(payment)


@router.get(
    "/{receipt_id}/payments",
    response_model=list[ReceiptPaymentResponse],
)
def get_receipt_payments(
    receipt_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[ReceiptPaymentResponse]:
    try:
        payments = list_receipt_payments(
            session,
            household_id=principal.household_id,
            receipt_id=receipt_id,
        )
    except ReceiptNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found",
        ) from exc
    return [
        ReceiptPaymentResponse.model_validate(payment) for payment in payments
    ]


@router.patch(
    "/{receipt_id}/payments/{payment_id}",
    response_model=ReceiptPaymentResponse,
)
def patch_receipt_payment(
    receipt_id: UUID,
    payment_id: UUID,
    payload: ReceiptPaymentUpdate,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ReceiptPaymentResponse:
    try:
        payment = update_receipt_payment(
            session,
            household_id=principal.household_id,
            receipt_id=receipt_id,
            payment_id=payment_id,
            user_id=principal.user_id,
            changes=payload.model_dump(exclude_unset=True),
        )
    except ReceiptNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found",
        ) from exc
    except ReceiptPaymentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt payment not found",
        ) from exc
    except PaymentMethodNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active payment method not found",
        ) from exc
    except ReceiptNotEditableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft receipts can be edited",
        ) from exc
    except ReceiptPaymentConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment method already used for this receipt",
        ) from exc
    return ReceiptPaymentResponse.model_validate(payment)


@router.delete(
    "/{receipt_id}/payments/{payment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_receipt_payment(
    receipt_id: UUID,
    payment_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> None:
    try:
        remove_receipt_payment(
            session,
            household_id=principal.household_id,
            receipt_id=receipt_id,
            payment_id=payment_id,
            user_id=principal.user_id,
        )
    except ReceiptNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found",
        ) from exc
    except ReceiptPaymentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt payment not found",
        ) from exc
    except ReceiptNotEditableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft receipts can be edited",
        ) from exc


@router.get(
    "/{receipt_id}/audit-events",
    response_model=list[AuditEventResponse],
)
def get_receipt_audit_events(
    receipt_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[AuditEventResponse]:
    try:
        events = list_receipt_audit_events(
            session,
            household_id=principal.household_id,
            receipt_id=receipt_id,
        )
    except ReceiptNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found",
        ) from exc
    return [AuditEventResponse.model_validate(event) for event in events]


@router.get(
    "/{receipt_id}/reconciliation",
    response_model=ReceiptReconciliationResponse,
)
def get_receipt_reconciliation(
    receipt_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ReceiptReconciliationResponse:
    try:
        reconciliation = reconcile_receipt(
            session,
            household_id=principal.household_id,
            receipt_id=receipt_id,
        )
    except ReceiptNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found",
        ) from exc

    return ReceiptReconciliationResponse.model_validate(
        reconciliation,
        from_attributes=True,
    )


@router.post("/{receipt_id}/approve", response_model=ReceiptResponse)
def post_receipt_approval(
    receipt_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ReceiptResponse:
    try:
        receipt = approve_receipt(
            session,
            household_id=principal.household_id,
            receipt_id=receipt_id,
            actor_user_id=principal.user_id,
        )
    except ReceiptNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found",
        ) from exc
    except ReceiptNotEditableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft receipts can be approved",
        ) from exc
    except ReceiptNotReconciledError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Receipt items and payments do not reconcile",
        ) from exc

    return ReceiptResponse.model_validate(receipt)


@router.post("/{receipt_id}/void", response_model=ReceiptResponse)
def post_receipt_void(
    receipt_id: UUID,
    payload: ReceiptVoidRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ReceiptResponse:
    try:
        receipt = void_receipt(
            session,
            household_id=principal.household_id,
            receipt_id=receipt_id,
            actor_user_id=principal.user_id,
            reason=payload.reason,
        )
    except ReceiptNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt not found",
        ) from exc
    except ReceiptNotVoidableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Receipt cannot be voided from its current status",
        ) from exc
    return ReceiptResponse.model_validate(receipt)
