from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes.merchants import router as merchants_router
from app.api.routes.income import router as income_router
from app.api.routes.auth import router as auth_router
from app.api.routes.invitations import household_router, invitation_router
from app.api.routes.payment_methods import router as payment_methods_router
from app.api.routes.receipts import router as receipts_router
from app.api.routes.receipt_captures import router as receipt_captures_router
from app.api.routes.maintenance import router as maintenance_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.products import router as products_router
from app.api.routes.recurring import router as recurring_router
from app.db.session import engine


STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    engine.dispose()


app = FastAPI(
    title="Expense Intelligence API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(merchants_router)
app.include_router(income_router)
app.include_router(auth_router)
app.include_router(household_router)
app.include_router(invitation_router)
app.include_router(payment_methods_router)
app.include_router(receipts_router)
app.include_router(receipt_captures_router)
app.include_router(maintenance_router)
app.include_router(dashboard_router)
app.include_router(products_router)
app.include_router(recurring_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False, response_class=FileResponse)
def web_app() -> FileResponse:
    """Serve the small browser interface from the same FastAPI process."""

    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


@app.get("/health/live", tags=["health"])
def health_live() -> dict[str, str]:
    """Confirm that the API process is running."""

    return {"status": "alive"}


@app.get("/health/ready", tags=["health"])
def health_ready() -> dict[str, str]:
    """Confirm that the API can communicate with PostgreSQL."""

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc

    return {"status": "ready", "database": "connected"}
