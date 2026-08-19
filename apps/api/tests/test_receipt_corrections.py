from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.seed import seed_development_data
from app.db.session import engine, get_db_session
from app.main import app


@pytest.fixture
def correction_context() -> Generator[tuple[TestClient, str], None, None]:
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection)
        seed = seed_development_data(session)

        def override_session() -> Generator[Session, None, None]:
            yield session

        app.dependency_overrides[get_db_session] = override_session
        try:
            with TestClient(app) as client:
                yield client, str(seed.payment_method_id)
        finally:
            app.dependency_overrides.clear()
            session.close()
            transaction.rollback()


def create_draft_parts(
    client: TestClient,
    payment_method_id: str,
    *,
    total: str = "10.00",
    item_total: str = "10.00",
    payment_total: str = "10.00",
) -> tuple[str, str, str]:
    receipt_response = client.post(
        "/receipts",
        json={
            "purchase_date": "2026-07-22",
            "currency": "EUR",
            "stated_total": total,
        },
    )
    assert receipt_response.status_code == 201
    receipt_id = receipt_response.json()["id"]
    item_response = client.post(
        f"/receipts/{receipt_id}/items",
        json={
            "position": 1,
            "line_type": "product",
            "description": "Correction item",
            "line_total": item_total,
        },
    )
    payment_response = client.post(
        f"/receipts/{receipt_id}/payments",
        json={
            "payment_method_id": payment_method_id,
            "amount": payment_total,
        },
    )
    assert item_response.status_code == 201
    assert payment_response.status_code == 201
    return (
        receipt_id,
        item_response.json()["id"],
        payment_response.json()["id"],
    )


def test_update_full_draft_and_reconcile(
    correction_context: tuple[TestClient, str],
) -> None:
    client, method_id = correction_context
    receipt_id, item_id, payment_id = create_draft_parts(
        client,
        method_id,
        total="10.00",
        item_total="9.00",
        payment_total="1.00",
    )

    receipt_update = client.patch(
        f"/receipts/{receipt_id}",
        json={"stated_total": "12.00", "notes": "Corrected"},
    )
    item_update = client.patch(
        f"/receipts/{receipt_id}/items/{item_id}",
        json={"description": "Corrected item", "line_total": "12.00"},
    )
    payment_update = client.patch(
        f"/receipts/{receipt_id}/payments/{payment_id}",
        json={"amount": "12.00"},
    )
    reconciliation = client.get(f"/receipts/{receipt_id}/reconciliation").json()
    events = client.get(f"/receipts/{receipt_id}/audit-events").json()

    assert receipt_update.status_code == 200
    assert receipt_update.json()["stated_total"] == "12.00"
    assert receipt_update.json()["notes"] == "Corrected"
    assert item_update.status_code == 200
    assert item_update.json()["line_total"] == "12.00"
    assert payment_update.status_code == 200
    assert payment_update.json()["amount"] == "12.00"
    assert reconciliation["is_reconciled"] is True
    assert [event["event_type"] for event in events] == [
        "receipt_created",
        "item_added",
        "payment_added",
        "receipt_updated",
        "item_updated",
        "payment_updated",
    ]
    assert events[-1]["event_data"]["payment_id"] == payment_id
    assert "amount" in events[-1]["event_data"]["changes"]


def test_remove_draft_item_and_payment_records_audit(
    correction_context: tuple[TestClient, str],
) -> None:
    client, method_id = correction_context
    receipt_id, item_id, payment_id = create_draft_parts(client, method_id)

    item_delete = client.delete(f"/receipts/{receipt_id}/items/{item_id}")
    payment_delete = client.delete(f"/receipts/{receipt_id}/payments/{payment_id}")
    items = client.get(f"/receipts/{receipt_id}/items").json()
    payments = client.get(f"/receipts/{receipt_id}/payments").json()
    events = client.get(f"/receipts/{receipt_id}/audit-events").json()

    assert item_delete.status_code == 204
    assert item_delete.content == b""
    assert payment_delete.status_code == 204
    assert payment_delete.content == b""
    assert items == []
    assert payments == []
    assert [event["event_type"] for event in events][-2:] == [
        "item_removed",
        "payment_removed",
    ]


def test_item_update_validates_position_and_final_sign(
    correction_context: tuple[TestClient, str],
) -> None:
    client, method_id = correction_context
    receipt_id, item_id, _ = create_draft_parts(client, method_id)
    second_item = client.post(
        f"/receipts/{receipt_id}/items",
        json={
            "position": 2,
            "line_type": "product",
            "description": "Second",
            "line_total": "0.00",
        },
    ).json()

    position_conflict = client.patch(
        f"/receipts/{receipt_id}/items/{second_item['id']}",
        json={"position": 1},
    )
    invalid_sign = client.patch(
        f"/receipts/{receipt_id}/items/{item_id}",
        json={"line_type": "discount"},
    )

    assert position_conflict.status_code == 409
    assert invalid_sign.status_code == 422


def test_approved_receipt_can_be_reopened_corrected_and_approved_again(
    correction_context: tuple[TestClient, str],
) -> None:
    client, method_id = correction_context
    receipt_id, item_id, payment_id = create_draft_parts(client, method_id)
    approval = client.post(f"/receipts/{receipt_id}/approve")

    blocked_edit = client.patch(f"/receipts/{receipt_id}", json={"notes": "too late"})
    reopened = client.post(f"/receipts/{receipt_id}/reopen")
    receipt_edit = client.patch(
        f"/receipts/{receipt_id}", json={"stated_total": "12.00"}
    )
    item_edit = client.patch(
        f"/receipts/{receipt_id}/items/{item_id}", json={"line_total": "12.00"}
    )
    payment_edit = client.patch(
        f"/receipts/{receipt_id}/payments/{payment_id}", json={"amount": "12.00"}
    )
    second_approval = client.post(f"/receipts/{receipt_id}/approve")
    void_response = client.post(
        f"/receipts/{receipt_id}/void",
        json={"reason": "Duplicate receipt"},
    )
    second_void = client.post(
        f"/receipts/{receipt_id}/void",
        json={"reason": "Again"},
    )
    events = client.get(f"/receipts/{receipt_id}/audit-events").json()

    assert approval.status_code == 200
    assert blocked_edit.status_code == 409
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "draft"
    assert reopened.json()["approved_at"] is None
    assert receipt_edit.status_code == 200
    assert item_edit.status_code == 200
    assert payment_edit.status_code == 200
    assert second_approval.status_code == 200
    assert second_approval.json()["stated_total"] == "12.00"
    assert void_response.status_code == 200
    assert void_response.json()["status"] == "voided"
    assert void_response.json()["voided_at"] is not None
    assert second_void.status_code == 409
    assert events[-1]["event_type"] == "receipt_voided"
    assert events[-1]["event_data"] == {
        "previous_status": "approved",
        "reason": "Duplicate receipt",
    }


def test_child_resources_are_scoped_to_the_selected_receipt(
    correction_context: tuple[TestClient, str],
) -> None:
    client, method_id = correction_context
    receipt_id, _, _ = create_draft_parts(client, method_id)

    item_response = client.patch(
        f"/receipts/{receipt_id}/items/{uuid4()}",
        json={"description": "Missing"},
    )
    payment_response = client.patch(
        f"/receipts/{receipt_id}/payments/{uuid4()}",
        json={"amount": "1.00"},
    )

    assert item_response.status_code == 404
    assert payment_response.status_code == 404
