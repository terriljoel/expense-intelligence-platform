from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.seed import seed_development_data
from app.db.session import engine, get_db_session
from app.main import app


@pytest.fixture
def income_client() -> Generator[TestClient, None, None]:
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


def create_income(client: TestClient) -> dict[str, object]:
    method_id = client.get("/payment-methods").json()[0]["id"]
    response = client.post(
        "/income",
        json={
            "source": "  Example   Employer  ",
            "income_type": "salary",
            "received_date": "2026-07-22",
            "amount": "2500.00",
            "currency": "EUR",
            "destination_payment_method_id": method_id,
            "notes": "  Monthly salary  ",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_create_get_and_list_income(income_client: TestClient) -> None:
    entry = create_income(income_client)

    assert entry["source"] == "Example Employer"
    assert entry["income_type"] == "salary"
    assert entry["amount"] == "2500.00"
    assert entry["notes"] == "Monthly salary"
    assert entry["received_by_user_id"]
    assert entry["destination_payment_method_id"]

    get_response = income_client.get(f"/income/{entry['id']}")
    list_response = income_client.get("/income")

    assert get_response.status_code == 200
    assert get_response.json() == entry
    assert entry["id"] in {item["id"] for item in list_response.json()}


def test_update_and_delete_income(income_client: TestClient) -> None:
    entry = create_income(income_client)

    update_response = income_client.patch(
        f"/income/{entry['id']}",
        json={
            "source": "Corrected Employer",
            "amount": "2600.00",
            "destination_payment_method_id": None,
            "notes": None,
        },
    )
    delete_response = income_client.delete(f"/income/{entry['id']}")
    get_response = income_client.get(f"/income/{entry['id']}")

    assert update_response.status_code == 200
    assert update_response.json()["source"] == "Corrected Employer"
    assert update_response.json()["amount"] == "2600.00"
    assert update_response.json()["destination_payment_method_id"] is None
    assert update_response.json()["notes"] is None
    assert delete_response.status_code == 204
    assert get_response.status_code == 404


def test_income_validation_errors(income_client: TestClient) -> None:
    negative = income_client.post(
        "/income",
        json={
            "source": "Employer",
            "income_type": "salary",
            "received_date": "2026-07-22",
            "amount": "-1.00",
            "currency": "eur",
        },
    )
    invalid_type = income_client.post(
        "/income",
        json={
            "source": "Employer",
            "income_type": "lottery",
            "received_date": "2026-07-22",
            "amount": "10.00",
        },
    )
    missing_method = income_client.post(
        "/income",
        json={
            "source": "Employer",
            "income_type": "salary",
            "received_date": "2026-07-22",
            "amount": "10.00",
            "destination_payment_method_id": str(uuid4()),
        },
    )
    empty_update = income_client.patch(f"/income/{uuid4()}", json={})

    assert negative.status_code == 422
    assert invalid_type.status_code == 422
    assert missing_method.status_code == 404
    assert empty_update.status_code == 422


def test_inactive_method_cannot_receive_new_income(
    income_client: TestClient,
) -> None:
    method_id = income_client.get("/payment-methods").json()[0]["id"]
    income_client.post(f"/payment-methods/{method_id}/deactivate")

    response = income_client.post(
        "/income",
        json={
            "source": "Employer",
            "income_type": "salary",
            "received_date": "2026-07-22",
            "amount": "10.00",
            "destination_payment_method_id": method_id,
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Active destination payment method not found"
    }
