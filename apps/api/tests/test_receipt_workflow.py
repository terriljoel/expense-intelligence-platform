from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.seed import seed_development_data
from app.db.session import engine, get_db_session
from app.main import app


@pytest.fixture
def workflow_context() -> Generator[tuple[TestClient, str], None, None]:
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection)
        seed_result = seed_development_data(session)

        def override_session() -> Generator[Session, None, None]:
            yield session

        app.dependency_overrides[get_db_session] = override_session

        try:
            with TestClient(app) as client:
                yield client, str(seed_result.payment_method_id)
        finally:
            app.dependency_overrides.clear()
            session.close()
            transaction.rollback()


def create_receipt_with_item(client: TestClient, total: str = "8.50") -> str:
    receipt_response = client.post(
        "/receipts",
        json={
            "purchase_date": "2026-07-22",
            "currency": "EUR",
            "stated_total": total,
        },
    )
    receipt_id = receipt_response.json()["id"]
    item_response = client.post(
        f"/receipts/{receipt_id}/items",
        json={
            "position": 1,
            "line_type": "product",
            "description": "Groceries",
            "line_total": "8.50",
        },
    )
    assert item_response.status_code == 201
    return receipt_id


def test_payment_reconciliation_and_approval(
    workflow_context: tuple[TestClient, str],
) -> None:
    client, payment_method_id = workflow_context
    receipt_id = create_receipt_with_item(client)

    methods_response = client.get("/payment-methods")
    assert methods_response.status_code == 200
    assert any(
        method["id"] == payment_method_id
        for method in methods_response.json()
    )

    payment_response = client.post(
        f"/receipts/{receipt_id}/payments",
        json={
            "payment_method_id": payment_method_id,
            "amount": "8.50",
        },
    )
    assert payment_response.status_code == 201

    listed_payments = client.get(f"/receipts/{receipt_id}/payments")
    assert listed_payments.status_code == 200
    assert len(listed_payments.json()) == 1
    assert listed_payments.json()[0]["amount"] == "8.50"

    reconciliation_response = client.get(
        f"/receipts/{receipt_id}/reconciliation"
    )
    reconciliation = reconciliation_response.json()
    assert reconciliation_response.status_code == 200
    assert reconciliation["item_total"] == "8.50"
    assert reconciliation["payment_total"] == "8.50"
    assert reconciliation["item_count"] == 1
    assert reconciliation["payment_count"] == 1
    assert reconciliation["is_reconciled"] is True

    approval_response = client.post(f"/receipts/{receipt_id}/approve")
    assert approval_response.status_code == 200
    assert approval_response.json()["status"] == "approved"
    assert approval_response.json()["approved_at"] is not None

    listed_receipts = client.get("/receipts?limit=10&offset=0")
    assert listed_receipts.status_code == 200
    assert receipt_id in {
        receipt["id"] for receipt in listed_receipts.json()
    }

    audit_response = client.get(f"/receipts/{receipt_id}/audit-events")
    assert audit_response.status_code == 200
    assert [event["event_type"] for event in audit_response.json()] == [
        "receipt_created",
        "item_added",
        "payment_added",
        "receipt_approved",
    ]

    edit_response = client.post(
        f"/receipts/{receipt_id}/items",
        json={
            "position": 2,
            "line_type": "product",
            "description": "Late item",
            "line_total": "1.00",
        },
    )
    assert edit_response.status_code == 409


def test_mismatched_receipt_cannot_be_approved(
    workflow_context: tuple[TestClient, str],
) -> None:
    client, payment_method_id = workflow_context
    receipt_id = create_receipt_with_item(client, total="10.00")
    client.post(
        f"/receipts/{receipt_id}/payments",
        json={
            "payment_method_id": payment_method_id,
            "amount": "8.50",
        },
    )

    reconciliation = client.get(
        f"/receipts/{receipt_id}/reconciliation"
    ).json()
    approval_response = client.post(f"/receipts/{receipt_id}/approve")

    assert reconciliation["item_difference"] == "1.50"
    assert reconciliation["payment_difference"] == "1.50"
    assert reconciliation["is_reconciled"] is False
    assert approval_response.status_code == 409


def test_duplicate_payment_method_is_rejected(
    workflow_context: tuple[TestClient, str],
) -> None:
    client, payment_method_id = workflow_context
    receipt_id = create_receipt_with_item(client)
    payload = {"payment_method_id": payment_method_id, "amount": "8.50"}

    first_response = client.post(
        f"/receipts/{receipt_id}/payments", json=payload
    )
    duplicate_response = client.post(
        f"/receipts/{receipt_id}/payments", json=payload
    )

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409


def test_unknown_payment_method_is_rejected(
    workflow_context: tuple[TestClient, str],
) -> None:
    client, _ = workflow_context
    receipt_id = create_receipt_with_item(client)
    response = client.post(
        f"/receipts/{receipt_id}/payments",
        json={"payment_method_id": str(uuid4()), "amount": "8.50"},
    )

    assert response.status_code == 404
