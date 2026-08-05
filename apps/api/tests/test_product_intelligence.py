from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.seed import seed_development_data
from app.db.session import engine, get_db_session
from app.main import app


@pytest.fixture
def product_client() -> Generator[TestClient, None, None]:
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


def _create_item(client: TestClient, description: str) -> str:
    receipt = client.post(
        "/receipts",
        json={
            "purchase_date": "2026-08-02",
            "currency": "EUR",
            "stated_total": "1.29",
        },
    ).json()
    item = client.post(
        f"/receipts/{receipt['id']}/items",
        json={
            "position": 1,
            "description": description,
            "line_total": "1.29",
        },
    )
    assert item.status_code == 201
    return item.json()["id"]


def test_confirmation_teaches_future_matching(product_client: TestClient) -> None:
    product = product_client.post(
        "/products",
        json={
            "canonical_name": "Ja! Haltbare Vollmilch 3.5%, 1 L",
            "brand": "Ja!",
            "product_type": "food",
            "category": "dairy",
        },
    )
    assert product.status_code == 201

    first_item = _create_item(product_client, "JA! H-MILCH 1 L")
    confirmation = product_client.post(
        f"/receipt-items/{first_item}/product-match/confirm",
        json={"product_id": product.json()["id"]},
    )
    assert confirmation.status_code == 200
    assert confirmation.json()["status"] == "confirmed"

    second_item = _create_item(product_client, "Ja H-Milch 1L")
    learned_match = product_client.post(f"/receipt-items/{second_item}/product-match")
    assert learned_match.status_code == 200
    assert learned_match.json()["product"]["id"] == product.json()["id"]
    assert learned_match.json()["method"] == "confirmed_alias"


def test_products_are_not_duplicated_without_barcode(
    product_client: TestClient,
) -> None:
    payload = {"canonical_name": "Whole Milk", "product_type": "food"}
    assert product_client.post("/products", json=payload).status_code == 201
    assert product_client.post("/products", json=payload).status_code == 409


def test_product_insights_support_manual_matching_and_nutrition(
    product_client: TestClient,
) -> None:
    item_id = _create_item(product_client, "JA H-MILCH 3.5 1L")

    before = product_client.get(
        "/product-insights", params={"match_status": "unmatched"}
    )
    manual = product_client.post(
        f"/product-insights/items/{item_id}/manual",
        json={
            "canonical_name": "Ja! Haltbare Vollmilch 3.5%, 1 L",
            "brand": "Ja!",
            "family_name": "Milk",
            "product_type": "food",
            "category": "dairy",
            "nutrition": {
                "energy_kcal": 64,
                "protein_g": 3.4,
                "basis_quantity": 100,
                "basis_unit": "ml",
            },
        },
    )
    after = product_client.get(
        "/product-insights", params={"match_status": "confirmed"}
    )

    assert before.status_code == 200
    assert before.json()["counts"]["unmatched"] >= 1
    assert manual.status_code == 201
    assert manual.json()["product"]["nutrition"]["protein_g"] == 3.4
    assert after.status_code == 200
    assert any(item["id"] == item_id for item in after.json()["items"])
    assert after.json()["counts"]["food_products_with_nutrition"] >= 1


def test_product_insights_can_ignore_restore_and_bulk_match_known_aliases(
    product_client: TestClient,
) -> None:
    first_item = _create_item(product_client, "BIO VOLLMILCH 1L")
    product = product_client.post(
        "/products",
        json={"canonical_name": "Organic Whole Milk", "product_type": "food"},
    ).json()
    assert product_client.post(
        f"/receipt-items/{first_item}/product-match/confirm",
        json={"product_id": product["id"]},
    ).status_code == 200

    second_item = _create_item(product_client, "Bio Vollmilch 1L")
    ignored = product_client.patch(
        f"/product-insights/items/{second_item}/status",
        json={"status": "rejected"},
    )
    restored = product_client.patch(
        f"/product-insights/items/{second_item}/status",
        json={"status": "unmatched"},
    )
    matched = product_client.post(
        "/product-insights/local-match", json={"item_ids": [second_item]}
    )

    assert ignored.status_code == 200
    assert ignored.json()["status"] == "rejected"
    assert restored.status_code == 200
    assert matched.status_code == 200
    assert matched.json() == {"processed": 1, "matched": 1}
