from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentPrincipal, get_current_principal
from app.db.session import get_db_session
from app.schemas.payment import PaymentMethodResponse
from app.services.payment_method import list_active_payment_methods


router = APIRouter(prefix="/payment-methods", tags=["payment methods"])


@router.get("", response_model=list[PaymentMethodResponse])
def get_payment_methods(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[PaymentMethodResponse]:
    methods = list_active_payment_methods(
        session,
        household_id=principal.household_id,
        user_id=principal.user_id,
    )
    return [PaymentMethodResponse.model_validate(method) for method in methods]
