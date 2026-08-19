from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import CurrentPrincipal, require_household_admin
from app.services.diagnostics import clear_errors, recent_errors


router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


@router.get("/errors")
def get_errors(
    limit: int = Query(default=50, ge=1, le=100),
    principal: CurrentPrincipal = Depends(require_household_admin),
) -> dict[str, object]:
    household_id = None if principal.is_global_admin else principal.household_id
    return {
        "entries": recent_errors(limit, household_id=household_id),
        "storage": "memory",
        "maximum": 100,
    }


@router.delete("/errors", status_code=status.HTTP_204_NO_CONTENT)
def delete_errors(
    principal: CurrentPrincipal = Depends(require_household_admin),
) -> None:
    clear_errors(
        household_id=None if principal.is_global_admin else principal.household_id
    )
