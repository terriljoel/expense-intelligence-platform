from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.seed import seed_development_data
from app.db.session import engine, get_db_session
from app.main import app


@pytest.fixture
def item_client() -> Generator[TestClient, None, None]:
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


def create_draft_receipt(client: TestClient) -> str:
    response = client.post(
        "/receipts",
        json={
            "purchase_date": "2026-07-22",
            "currency": "EUR",
            "stated_total": "4.50",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_add_and_list_signed_receipt_items(item_client: TestClient) -> None:
    receipt_id = create_draft_receipt(item_client)
    items = [
        {
            "position": 1,
            "line_type": "product",
            "description": "Milk",
            "quantity": "1.000",
            "unit_price": "4.00",
            "line_total": "4.00",
        },
        {
            "position": 2,
            "line_type": "deposit",
            "description": "Pfand",
            "line_total": "1.00",
        },
        {
            "position": 3,
            "line_type": "discount",
            "description": "Discount",
            "line_total": "-0.50",
        },
    ]

    for item in items:
        response = item_client.post(f"/receipts/{receipt_id}/items", json=item)
        assert response.status_code == 201

    list_response = item_client.get(f"/receipts/{receipt_id}/items")

    assert list_response.status_code == 200
    listed_items = list_response.json()
    assert [item["position"] for item in listed_items] == [1, 2, 3]
    assert [item["line_total"] for item in listed_items] == [
        "4.00",
        "1.00",
        "-0.50",
    ]


def test_duplicate_item_position_is_rejected(item_client: TestClient) -> None:
    receipt_id = create_draft_receipt(item_client)
    item = {
        "position": 1,
        "line_type": "product",
        "description": "Bread",
        "line_total": "4.50",
    }

    first_response = item_client.post(
        f"/receipts/{receipt_id}/items", json=item
    )
    duplicate_response = item_client.post(
        f"/receipts/{receipt_id}/items", json=item
    )

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409
    assert duplicate_response.json() == {
        "detail": "Receipt item position already exists"
    }


def test_invalid_line_total_sign_is_rejected(item_client: TestClient) -> None:
    receipt_id = create_draft_receipt(item_client)
    response = item_client.post(
        f"/receipts/{receipt_id}/items",
        json={
            "position": 1,
            "line_type": "discount",
            "description": "Invalid discount",
            "line_total": "1.00",
        },
    )

    assert response.status_code == 422


def test_items_for_unknown_receipt_return_not_found(
    item_client: TestClient,
) -> None:
    response = item_client.get(f"/receipts/{uuid4()}/items")

    assert response.status_code == 404
    assert response.json() == {"detail": "Receipt not found"}
