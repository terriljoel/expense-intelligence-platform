from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentPrincipal, get_current_principal
from app.db.session import get_db_session
from app.models import IncomeEntry, User
from app.schemas.income import IncomeCreate, IncomeResponse, IncomeUpdate
from app.services.income import (
    IncomeDestinationMethodNotFoundError,
    IncomeNotFoundError,
    create_income,
    delete_income,
    get_income,
    list_income,
    update_income,
)


router = APIRouter(prefix="/income", tags=["income"])


def _income_response(
    session: Session, entry: IncomeEntry
) -> IncomeResponse:
    receiver = session.get(User, entry.received_by_user_id)
    return IncomeResponse.model_validate(entry).model_copy(
        update={
            "received_by_display_name": (
                receiver.display_name if receiver is not None else None
            )
        }
    )


@router.post("", response_model=IncomeResponse, status_code=status.HTTP_201_CREATED)
def post_income(
    payload: IncomeCreate,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> IncomeResponse:
    try:
        entry = create_income(
            session,
            household_id=principal.household_id,
            received_by_user_id=principal.user_id,
            **payload.model_dump(),
        )
    except IncomeDestinationMethodNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active destination payment method not found",
        ) from exc
    return _income_response(session, entry)


@router.get("", response_model=list[IncomeResponse])
def get_income_entries(
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[IncomeResponse]:
    entries = list_income(
        session,
        household_id=principal.household_id,
        limit=limit,
        offset=offset,
    )
    return [_income_response(session, entry) for entry in entries]


@router.get("/{income_id}", response_model=IncomeResponse)
def get_income_by_id(
    income_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> IncomeResponse:
    try:
        entry = get_income(
            session,
            household_id=principal.household_id,
            income_id=income_id,
        )
    except IncomeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Income entry not found",
        ) from exc
    return _income_response(session, entry)


@router.patch("/{income_id}", response_model=IncomeResponse)
def patch_income(
    income_id: UUID,
    payload: IncomeUpdate,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> IncomeResponse:
    try:
        entry = update_income(
            session,
            household_id=principal.household_id,
            income_id=income_id,
            changes=payload.model_dump(exclude_unset=True),
        )
    except IncomeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Income entry not found",
        ) from exc
    except IncomeDestinationMethodNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active destination payment method not found",
        ) from exc
    return _income_response(session, entry)


@router.delete("/{income_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_income(
    income_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> None:
    try:
        delete_income(
            session,
            household_id=principal.household_id,
            income_id=income_id,
        )
    except IncomeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Income entry not found",
        ) from exc
