from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentPrincipal, get_current_principal
from app.db.session import get_db_session
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard import build_dashboard, dashboard_csv


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
def get_dashboard(
    year: int = Query(default=date.today().year, ge=2000, le=2100),
    month: int = Query(default=date.today().month, ge=1, le=12),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> DashboardResponse:
    return build_dashboard(
        session, household_id=principal.household_id, year=year, month=month
    )


@router.get("/export.csv", response_class=Response)
def export_dashboard_csv(
    year: int = Query(default=date.today().year, ge=2000, le=2100),
    month: int = Query(default=date.today().month, ge=1, le=12),
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> Response:
    report = build_dashboard(
        session, household_id=principal.household_id, year=year, month=month
    )
    filename = f"expense-dashboard-{year}-{month:02d}.csv"
    return Response(
        content=dashboard_csv(report).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
