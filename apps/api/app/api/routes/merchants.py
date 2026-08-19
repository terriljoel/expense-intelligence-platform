from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentPrincipal, get_current_principal
from app.db.session import get_db_session
from app.schemas.merchant import MerchantCreate, MerchantResponse, MerchantUpdate
from app.services.merchant import (
    MerchantAlreadyExistsError,
    MerchantNotFoundError,
    create_merchant,
    list_merchants,
    update_merchant,
)


router = APIRouter(prefix="/merchants", tags=["merchants"])


@router.post(
    "",
    response_model=MerchantResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_merchant(
    payload: MerchantCreate,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> MerchantResponse:
    try:
        merchant = create_merchant(
            session,
            household_id=principal.household_id,
            name=payload.name,
            address=payload.address,
        )
    except MerchantAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Merchant already exists in this household",
        ) from exc

    return MerchantResponse.model_validate(merchant)


@router.get("", response_model=list[MerchantResponse])
def get_merchants(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[MerchantResponse]:
    merchants = list_merchants(session, household_id=principal.household_id)
    return [MerchantResponse.model_validate(merchant) for merchant in merchants]


@router.patch("/{merchant_id}", response_model=MerchantResponse)
def patch_merchant(
    merchant_id: UUID,
    payload: MerchantUpdate,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> MerchantResponse:
    try:
        merchant = update_merchant(
            session,
            household_id=principal.household_id,
            merchant_id=merchant_id,
            changes=payload.model_dump(exclude_unset=True),
        )
    except MerchantNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found",
        ) from exc
    except MerchantAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Merchant already exists in this household",
        ) from exc
    return MerchantResponse.model_validate(merchant)
