from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentPrincipal, get_current_principal
from app.db.session import get_db_session
from app.models import RecurringExpense
from app.schemas.recurring import RecurringExpenseResponse, RecurringExpenseWrite
from app.services.recurring import generate_due, list_templates, save_template


router = APIRouter(prefix="/recurring-expenses", tags=["recurring expenses"])


@router.get("", response_model=list[RecurringExpenseResponse])
def get_all(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
):
    return list_templates(session, principal.household_id)


@router.post(
    "", response_model=RecurringExpenseResponse, status_code=status.HTTP_201_CREATED
)
def create(
    payload: RecurringExpenseWrite,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
):
    return save_template(session, principal.household_id, principal.user_id, payload)


@router.put("/{template_id}", response_model=RecurringExpenseResponse)
def update(
    template_id: UUID,
    payload: RecurringExpenseWrite,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
):
    try:
        return save_template(
            session, principal.household_id, principal.user_id, payload, template_id
        )
    except LookupError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Recurring expense not found"
        ) from exc


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(
    template_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
):
    session.execute(
        delete(RecurringExpense).where(
            RecurringExpense.id == template_id,
            RecurringExpense.household_id == principal.household_id,
        )
    )


@router.post("/generate-due", status_code=status.HTTP_200_OK)
def generate(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
):
    return {"created": len(generate_due(session, principal.household_id))}
