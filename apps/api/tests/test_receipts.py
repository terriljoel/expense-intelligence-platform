from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.seed import seed_development_data
from app.db.session import engine, get_db_session
from app.main import app


@pytest.fixture
def receipt_client() -> Generator[TestClient, None, None]:
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection)
        seed_development_data(session)

        def override_session() -> Generator[Session, None, None]:
            yield session

        app.dependency_overrides[get_db_session] = override_session

        try:
            with TestClient(app) as client:
                yield client
        finally:
            app.dependency_overrides.clear()
            session.close()
            transaction.rollback()


def test_create_and_get_draft_receipt(receipt_client: TestClient) -> None:
    merchant_response = receipt_client.post(
        "/merchants",
        json={"name": "Receipt Test Market"},
    )
    merchant_id = merchant_response.json()["id"]

    create_response = receipt_client.post(
        "/receipts",
        json={
            "merchant_id": merchant_id,
            "purchase_date": "2026-07-22",
            "currency": "EUR",
            "stated_total": "12.34",
            "notes": "  Weekly groceries  ",
        },
    )

    assert create_response.status_code == 201
    created_receipt = create_response.json()
    assert created_receipt["merchant_id"] == merchant_id
    assert created_receipt["stated_total"] == "12.34"
    assert created_receipt["status"] == "draft"
    assert created_receipt["source"] == "manual"
    assert created_receipt["notes"] == "Weekly groceries"

    get_response = receipt_client.get(f"/receipts/{created_receipt['id']}")

    assert get_response.status_code == 200
    assert get_response.json() == created_receipt


def test_receipt_rejects_unknown_merchant(receipt_client: TestClient) -> None:
    response = receipt_client.post(
        "/receipts",
        json={
            "merchant_id": str(uuid4()),
            "purchase_date": "2026-07-22",
            "currency": "EUR",
            "stated_total": "10.00",
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Merchant not found in this household"
    }


def test_receipt_rejects_invalid_money_and_currency(
    receipt_client: TestClient,
) -> None:
    response = receipt_client.post(
        "/receipts",
        json={
            "purchase_date": "2026-07-22",
            "currency": "eur",
            "stated_total": "-1.00",
        },
    )

    assert response.status_code == 422


def test_get_unknown_receipt_returns_not_found(
    receipt_client: TestClient,
) -> None:
    response = receipt_client.get(f"/receipts/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Receipt not found"}
