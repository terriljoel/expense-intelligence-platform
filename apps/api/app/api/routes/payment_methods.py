from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentPrincipal, get_current_principal
from app.db.session import get_db_session
from app.schemas.payment import (
    PaymentMethodCreate,
    PaymentMethodResponse,
    PaymentMethodUpdate,
)
from app.services.payment_method import (
    PaymentMethodConflictError,
    PaymentMethodNotFoundError,
    create_payment_method,
    deactivate_payment_method,
    get_payment_method,
    list_payment_methods,
    update_payment_method,
)


router = APIRouter(prefix="/payment-methods", tags=["payment methods"])


@router.post(
    "",
    response_model=PaymentMethodResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_payment_method(
    payload: PaymentMethodCreate,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> PaymentMethodResponse:
    try:
        method = create_payment_method(
            session,
            household_id=principal.household_id,
            user_id=principal.user_id,
            name=payload.name,
            method_type=payload.method_type,
            provider=payload.provider,
            last_four=payload.last_four,
        )
    except PaymentMethodConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An equivalent active payment method already exists",
        ) from exc
    return PaymentMethodResponse.model_validate(method)


@router.get("", response_model=list[PaymentMethodResponse])
def get_payment_methods(
    include_inactive: bool = Query(default=False),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[PaymentMethodResponse]:
    methods = list_payment_methods(
        session,
        household_id=principal.household_id,
        user_id=principal.user_id,
        include_inactive=include_inactive,
    )
    return [PaymentMethodResponse.model_validate(method) for method in methods]


@router.get("/{payment_method_id}", response_model=PaymentMethodResponse)
def get_payment_method_by_id(
    payment_method_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> PaymentMethodResponse:
    try:
        method = get_payment_method(
            session,
            household_id=principal.household_id,
            user_id=principal.user_id,
            payment_method_id=payment_method_id,
        )
    except PaymentMethodNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment method not found",
        ) from exc
    return PaymentMethodResponse.model_validate(method)


@router.patch("/{payment_method_id}", response_model=PaymentMethodResponse)
def patch_payment_method(
    payment_method_id: UUID,
    payload: PaymentMethodUpdate,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> PaymentMethodResponse:
    try:
        method = update_payment_method(
            session,
            household_id=principal.household_id,
            user_id=principal.user_id,
            payment_method_id=payment_method_id,
            changes=payload.model_dump(exclude_unset=True),
        )
    except PaymentMethodNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment method not found",
        ) from exc
    except PaymentMethodConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An equivalent active payment method already exists",
        ) from exc
    return PaymentMethodResponse.model_validate(method)


@router.post(
    "/{payment_method_id}/deactivate",
    response_model=PaymentMethodResponse,
)
def post_payment_method_deactivation(
    payment_method_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> PaymentMethodResponse:
    try:
        method = deactivate_payment_method(
            session,
            household_id=principal.household_id,
            user_id=principal.user_id,
            payment_method_id=payment_method_id,
        )
    except PaymentMethodNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment method not found",
        ) from exc
    return PaymentMethodResponse.model_validate(method)
