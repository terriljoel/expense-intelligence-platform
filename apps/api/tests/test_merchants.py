from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.seed import seed_development_data
from app.db.session import engine, get_db_session
from app.main import app


@pytest.fixture
def merchant_client() -> Generator[TestClient, None, None]:
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


def test_create_and_list_merchant(merchant_client: TestClient) -> None:
    create_response = merchant_client.post(
        "/merchants",
        json={"name": "  Test Market   Berlin  "},
    )

    assert create_response.status_code == 201
    assert create_response.json()["name"] == "Test Market Berlin"
    assert create_response.json()["normalized_name"] == "test market berlin"

    list_response = merchant_client.get("/merchants")

    assert list_response.status_code == 200
    assert any(
        merchant["id"] == create_response.json()["id"]
        for merchant in list_response.json()
    )


def test_duplicate_normalized_merchant_is_rejected(
    merchant_client: TestClient,
) -> None:
    first_response = merchant_client.post(
        "/merchants",
        json={"name": "Duplicate Market"},
    )
    duplicate_response = merchant_client.post(
        "/merchants",
        json={"name": "  DUPLICATE   MARKET "},
    )

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409
    assert duplicate_response.json() == {
        "detail": "Merchant already exists in this household"
    }


def test_same_merchant_name_at_different_addresses_is_allowed(
    merchant_client: TestClient,
) -> None:
    first = merchant_client.post(
        "/merchants",
        json={"name": "ALDI", "address": "Hauptstrasse 1"},
    )
    second = merchant_client.post(
        "/merchants",
        json={"name": "ALDI", "address": "Bahnhofstrasse 20"},
    )
    duplicate = merchant_client.post(
        "/merchants",
        json={"name": "aldi", "address": "  HAUPTSTRASSE   1 "},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert duplicate.status_code == 409


def test_blank_merchant_name_is_rejected(merchant_client: TestClient) -> None:
    response = merchant_client.post("/merchants", json={"name": "   "})

    assert response.status_code == 422
