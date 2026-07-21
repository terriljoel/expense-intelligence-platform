from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes.merchants import router as merchants_router
from app.api.routes.payment_methods import router as payment_methods_router
from app.api.routes.receipts import router as receipts_router
from app.db.session import engine


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
app.include_router(payment_methods_router)
app.include_router(receipts_router)


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
