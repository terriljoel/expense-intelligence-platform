from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import CurrentPrincipal, require_global_admin
from app.services.diagnostics import clear_errors, recent_errors


router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


@router.get("/errors")
def get_errors(
    limit: int = Query(default=50, ge=1, le=100),
    _: CurrentPrincipal = Depends(require_global_admin),
) -> dict[str, object]:
    return {"entries": recent_errors(limit), "storage": "memory", "maximum": 100}


@router.delete("/errors", status_code=status.HTTP_204_NO_CONTENT)
def delete_errors(
    _: CurrentPrincipal = Depends(require_global_admin),
) -> None:
    clear_errors()
