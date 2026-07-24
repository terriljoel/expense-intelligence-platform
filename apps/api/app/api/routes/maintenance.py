from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentPrincipal, require_household_admin
from app.api.routes.receipt_captures import get_receipt_image_storage
from app.db.session import get_db_session
from app.schemas.maintenance import (
    HouseholdResetRequest,
    HouseholdResetResponse,
    MaintenancePreview,
)
from app.services.maintenance import (
    HouseholdNotFoundError,
    ResetConfirmationError,
    build_household_archive,
    confirmation_phrase,
    maintenance_preview,
    reset_household_data,
)
from app.services.receipt_image_storage import ReceiptImageStorage


router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.get("/preview", response_model=MaintenancePreview)
def get_maintenance_preview(
    principal: CurrentPrincipal = Depends(require_household_admin),
    session: Session = Depends(get_db_session),
) -> MaintenancePreview:
    try:
        household, counts = maintenance_preview(
            session, household_id=principal.household_id
        )
    except HouseholdNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Household not found") from exc
    return MaintenancePreview(
        household_name=household.name,
        confirmation_phrase=confirmation_phrase(household.name),
        counts=counts,
    )


@router.get("/archive", response_class=Response)
def download_household_archive(
    principal: CurrentPrincipal = Depends(require_household_admin),
    session: Session = Depends(get_db_session),
    storage: ReceiptImageStorage = Depends(get_receipt_image_storage),
) -> Response:
    try:
        content, filename = build_household_archive(
            session,
            household_id=principal.household_id,
            storage=storage,
        )
    except HouseholdNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Household not found") from exc
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
        },
    )


@router.post("/reset", response_model=HouseholdResetResponse)
def reset_household(
    payload: HouseholdResetRequest,
    principal: CurrentPrincipal = Depends(require_household_admin),
    session: Session = Depends(get_db_session),
    storage: ReceiptImageStorage = Depends(get_receipt_image_storage),
) -> HouseholdResetResponse:
    try:
        counts, deleted, not_found, failures = reset_household_data(
            session,
            household_id=principal.household_id,
            supplied_confirmation=payload.confirmation,
            storage=storage,
        )
    except HouseholdNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Household not found") from exc
    except ResetConfirmationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Confirmation phrase does not match",
        ) from exc
    return HouseholdResetResponse(
        message="Household transactional data was reset",
        deleted=counts,
        image_objects_deleted=deleted,
        image_objects_not_found=not_found,
        image_delete_failures=failures,
    )

