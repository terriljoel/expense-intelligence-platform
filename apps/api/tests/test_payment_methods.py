from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.seed import seed_development_data
from app.db.session import engine, get_db_session
from app.main import app


@pytest.fixture
def payment_method_client() -> Generator[TestClient, None, None]:
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


def create_card(
    client: TestClient,
    *,
    name: str = "Travel Visa",
    last_four: str = "1234",
) -> dict[str, object]:
    response = client.post(
        "/payment-methods",
        json={
            "name": name,
            "method_type": "credit_card",
            "provider": "Example Bank",
            "last_four": last_four,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_create_get_and_list_payment_method(
    payment_method_client: TestClient,
) -> None:
    method = create_card(payment_method_client, name="  Travel   Visa  ")

    assert method["name"] == "Travel Visa"
    assert method["method_type"] == "credit_card"
    assert method["provider"] == "Example Bank"
    assert method["last_four"] == "1234"
    assert method["is_active"] is True
    assert method["user_id"]
    assert method["created_at"]
    assert method["updated_at"]

    get_response = payment_method_client.get(
        f"/payment-methods/{method['id']}"
    )
    list_response = payment_method_client.get("/payment-methods")

    assert get_response.status_code == 200
    assert get_response.json()["id"] == method["id"]
    assert method["id"] in {
        item["id"] for item in list_response.json()
    }


def test_duplicate_active_method_is_rejected(
    payment_method_client: TestClient,
) -> None:
    create_card(payment_method_client)
    duplicate = payment_method_client.post(
        "/payment-methods",
        json={
            "name": "travel visa",
            "method_type": "credit_card",
            "provider": "example bank",
            "last_four": "1234",
        },
    )

    assert duplicate.status_code == 409


def test_update_and_deactivate_payment_method(
    payment_method_client: TestClient,
) -> None:
    method = create_card(payment_method_client)
    method_id = method["id"]

    update_response = payment_method_client.patch(
        f"/payment-methods/{method_id}",
        json={"name": "Daily Visa", "provider": None},
    )
    deactivate_response = payment_method_client.post(
        f"/payment-methods/{method_id}/deactivate"
    )
    active_list = payment_method_client.get("/payment-methods").json()
    all_list = payment_method_client.get(
        "/payment-methods?include_inactive=true"
    ).json()

    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Daily Visa"
    assert update_response.json()["provider"] is None
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False
    assert method_id not in {item["id"] for item in active_list}
    assert method_id in {item["id"] for item in all_list}


def test_update_cannot_duplicate_another_active_method(
    payment_method_client: TestClient,
) -> None:
    create_card(payment_method_client, name="Primary Visa", last_four="1111")
    second = create_card(
        payment_method_client,
        name="Backup Visa",
        last_four="2222",
    )

    conflict = payment_method_client.patch(
        f"/payment-methods/{second['id']}",
        json={"name": "primary visa", "last_four": "1111"},
    )

    assert conflict.status_code == 409


def test_deactivated_method_cannot_pay_new_receipt(
    payment_method_client: TestClient,
) -> None:
    method = create_card(payment_method_client)
    method_id = method["id"]
    payment_method_client.post(f"/payment-methods/{method_id}/deactivate")
    receipt = payment_method_client.post(
        "/receipts",
        json={
            "purchase_date": "2026-07-22",
            "currency": "EUR",
            "stated_total": "1.00",
        },
    ).json()

    payment_response = payment_method_client.post(
        f"/receipts/{receipt['id']}/payments",
        json={"payment_method_id": method_id, "amount": "1.00"},
    )

    assert payment_response.status_code == 404


def test_payment_method_validation_and_scope_errors(
    payment_method_client: TestClient,
) -> None:
    invalid_last_four = payment_method_client.post(
        "/payment-methods",
        json={
            "name": "Unsafe card",
            "method_type": "credit_card",
            "last_four": "12AB",
        },
    )
    empty_update = payment_method_client.patch(
        f"/payment-methods/{uuid4()}", json={}
    )
    missing_method = payment_method_client.get(
        f"/payment-methods/{uuid4()}"
    )

    assert invalid_last_four.status_code == 422
    assert empty_update.status_code == 422
    assert missing_method.status_code == 404
