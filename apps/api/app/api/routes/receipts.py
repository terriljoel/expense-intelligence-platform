from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import (
    CurrentPrincipal,
    get_current_principal,
    get_receipt_image_storage,
)
from app.db.session import get_db_session
from app.models import PaymentMethod, Receipt, ReceiptCapture, ReceiptPayment, User
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
    ReceiptCaptureAlreadyUsedError,
    ReceiptCaptureNotFoundError,
    ReceiptCaptureNotReadyError,
    DuplicateReceiptError,
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
    reopen_receipt,
    remove_receipt_item,
    remove_receipt_payment,
    update_receipt,
    update_receipt_item,
    update_receipt_payment,
    void_receipt,
)
from app.services.receipt_image_storage import (
    ReceiptImageNotFoundError,
    ReceiptImageStorage,
    ReceiptImageStorageError,
)


router = APIRouter(prefix="/receipts", tags=["receipts"])


def _receipt_response(session: Session, receipt: Receipt) -> ReceiptResponse:
    creator = session.get(User, receipt.created_by_user_id)
    return ReceiptResponse.model_validate(receipt).model_copy(
        update={
            "created_by_display_name": (
                creator.display_name if creator is not None else None
            ),
            "image_url": (
                f"/receipts/{receipt.id}/image" if receipt.image_object_key else None
            ),
        }
    )


@router.get("/{receipt_id}/image", response_class=Response)
def get_receipt_image(
    receipt_id: UUID,
    download: bool = Query(default=False),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    storage: ReceiptImageStorage = Depends(get_receipt_image_storage),
) -> Response:
    try:
        receipt = get_receipt(
            session, household_id=principal.household_id, receipt_id=receipt_id
        )
        if not receipt.image_object_key:
            raise ReceiptImageNotFoundError
        content = storage.get(receipt.image_object_key)
    except (ReceiptNotFoundError, ReceiptImageNotFoundError) as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Receipt image not found"
        ) from exc
    except ReceiptImageStorageError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    capture = session.scalar(
        select(ReceiptCapture).where(ReceiptCapture.receipt_id == receipt_id)
    )
    filename = capture.original_filename if capture else f"receipt-{receipt_id}.jpg"
    disposition = "attachment" if download else "inline"
    return Response(
        content=content,
        media_type=capture.media_type if capture else "application/octet-stream",
        headers={
            "Content-Disposition": (
                f"{disposition}; filename*=UTF-8''{quote(filename or 'receipt-image', safe='')}"
            )
        },
    )


def _payment_response(
    session: Session, payment: ReceiptPayment
) -> ReceiptPaymentResponse:
    payer = session.get(User, payment.user_id)
    method = (
        session.get(PaymentMethod, payment.payment_method_id)
        if payment.payment_method_id is not None
        else None
    )
    return ReceiptPaymentResponse.model_validate(payment).model_copy(
        update={
            "payer_display_name": (payer.display_name if payer is not None else None),
            "payment_method_name": (method.name if method is not None else None),
            "payment_method_last_four": (
                method.last_four if method is not None else None
            ),
        }
    )


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
            payment_method_id=payload.payment_method_id,
            category=payload.category,
            purchase_date=payload.purchase_date,
            currency=payload.currency,
            stated_total=payload.stated_total,
            notes=payload.notes,
            capture_id=payload.capture_id,
            receipt_number=payload.receipt_number,
        )
    except MerchantNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found in this household",
        ) from exc
    except PaymentMethodNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active payment method not found for this user",
        ) from exc
    except ReceiptCaptureNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt capture not found in this household",
        ) from exc
    except ReceiptCaptureNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run OCR before creating a receipt from this capture",
        ) from exc
    except ReceiptCaptureAlreadyUsedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Receipt capture is already linked to a receipt",
        ) from exc
    except DuplicateReceiptError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "This appears to be a duplicate receipt",
                "existing_receipt_id": str(exc.match.receipt_id),
                "reason": exc.match.reason,
            },
        ) from exc

    return _receipt_response(session, receipt)


@router.get("", response_model=list[ReceiptResponse])
def get_receipts(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=100),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[ReceiptResponse]:
    receipts = list_receipts(
        session,
        household_id=principal.household_id,
        limit=limit,
        offset=offset,
        query=q,
    )
    return [_receipt_response(session, receipt) for receipt in receipts]


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

    return _receipt_response(session, receipt)


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
    except DuplicateReceiptError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "These changes match an existing receipt",
                "existing_receipt_id": str(exc.match.receipt_id),
                "reason": exc.match.reason,
            },
        ) from exc
    return _receipt_response(session, receipt)


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

    return _payment_response(session, payment)


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
    return [_payment_response(session, payment) for payment in payments]


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
    return _payment_response(session, payment)


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

    return _receipt_response(session, receipt)


@router.post("/{receipt_id}/reopen", response_model=ReceiptResponse)
def post_receipt_reopen(
    receipt_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ReceiptResponse:
    try:
        receipt = reopen_receipt(
            session,
            household_id=principal.household_id,
            receipt_id=receipt_id,
            actor_user_id=principal.user_id,
        )
    except ReceiptNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Receipt not found") from exc
    except ReceiptNotEditableError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Only approved receipts can be reopened"
        ) from exc
    return _receipt_response(session, receipt)


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
    return _receipt_response(session, receipt)
