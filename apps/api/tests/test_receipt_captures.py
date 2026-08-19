from collections.abc import Generator
from datetime import date, time
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.seed import seed_development_data
from app.db.session import engine, get_db_session
from app.integrations.azure.document_intelligence import (
    AzureReceiptOcrProvider,
)
from app.main import app
from app.services.ocr import OcrLineItem
from app.services.receipt_capture import (
    OcrProcessingError,
    OcrResult,
    extract_receipt_suggestions,
    get_ocr_provider,
)


PNG_IMAGE = b"\x89PNG\r\n\x1a\n" + b"test-receipt-image"


class FakeOcrProvider:
    def extract_text(self, image: bytes) -> OcrResult:
        assert image == PNG_IMAGE
        return OcrResult(
            provider="test-ocr",
            raw_text=(
                "REWE Markt GmbH\nMusterstr. 1\nDatum 23.07.2026\nSUMME EUR 12,34\n"
            ),
            line_items=(
                OcrLineItem(
                    description="Apfelsaft",
                    quantity=Decimal("2"),
                    unit_price=Decimal("6.17"),
                    line_total=Decimal("12.34"),
                ),
            ),
        )


class FailingOcrProvider:
    def extract_text(self, image: bytes) -> OcrResult:
        raise OcrProcessingError("Provider unavailable")


class FakeAzurePoller:
    def result(self, timeout: int) -> object:
        assert timeout == 60
        currency = {"amount": 12.34, "currencyCode": "EUR"}
        fields = {
            "MerchantName": {"valueString": "REWE Markt GmbH"},
            "MerchantAddress": {"valueString": "Marktstrasse 1, Berlin"},
            "MerchantPhoneNumber": {"valuePhoneNumber": "+49 30 123456"},
            "TransactionDate": {"valueDate": date(2026, 7, 23)},
            "TransactionTime": {"valueTime": time(18, 42)},
            "Total": {"valueCurrency": currency},
            "Subtotal": {"valueCurrency": {"amount": 10.37, "currencyCode": "EUR"}},
            "TotalTax": {"valueCurrency": {"amount": 1.97, "currencyCode": "EUR"}},
            "Items": {
                "valueArray": [
                    {
                        "valueObject": {
                            "Description": {"valueString": "Apfelsaft"},
                            "Quantity": {"valueNumber": 2},
                            "Price": {
                                "valueCurrency": {
                                    "amount": 2.50,
                                    "currencyCode": "EUR",
                                }
                            },
                            "TotalPrice": {
                                "valueCurrency": {
                                    "amount": 5.00,
                                    "currencyCode": "EUR",
                                }
                            },
                        }
                    }
                ]
            },
        }
        document = type("Document", (), {"fields": fields})()
        return type(
            "Result",
            (),
            {
                "documents": [document],
                "content": "REWE\nSUMME 12,34 EUR",
                "as_dict": lambda self: {"modelId": "prebuilt-receipt"},
            },
        )()


class FakeAzureClient:
    def begin_analyze_document(
        self, model_id: str, *, body: object, locale: str
    ) -> FakeAzurePoller:
        assert model_id == "prebuilt-receipt"
        assert locale == "de-DE"
        assert body.read() == PNG_IMAGE
        return FakeAzurePoller()


@pytest.fixture
def capture_client(tmp_path: Path) -> Generator[TestClient, None, None]:
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection)
        seed_development_data(session)
        settings = get_settings().model_copy(
            update={"receipt_image_dir": tmp_path / "receipt-images"}
        )

        def override_session() -> Generator[Session, None, None]:
            yield session

        app.dependency_overrides[get_db_session] = override_session
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_ocr_provider] = lambda: FakeOcrProvider()
        try:
            with TestClient(app) as client:
                yield client
        finally:
            app.dependency_overrides.clear()
            session.close()
            transaction.rollback()


def upload_capture(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/receipt-captures",
        files={"file": ("receipt.png", PNG_IMAGE, "image/png")},
    )
    assert response.status_code == 201
    return response.json()


def test_capture_ocr_review_and_create_image_receipt(
    capture_client: TestClient,
) -> None:
    uploaded = upload_capture(capture_client)
    assert uploaded["ocr_status"] == "pending"
    assert uploaded["ocr_raw_text"] is None

    image = capture_client.get(uploaded["image_url"])
    assert image.status_code == 200
    assert image.content == PNG_IMAGE
    assert image.headers["content-type"] == "image/png"

    ocr = capture_client.post(f"/receipt-captures/{uploaded['id']}/ocr")
    assert ocr.status_code == 200
    result = ocr.json()
    assert result["ocr_status"] == "succeeded"
    assert result["ocr_provider"] == "test-ocr"
    assert result["suggested_merchant_name"] == "REWE Markt GmbH"
    assert result["suggested_purchase_date"] == "2026-07-23"
    assert result["suggested_currency"] == "EUR"
    assert result["suggested_total"] == "12.34"
    assert "SUMME EUR 12,34" in result["ocr_raw_text"]

    receipt = capture_client.post(
        "/receipts",
        json={
            "capture_id": uploaded["id"],
            "purchase_date": result["suggested_purchase_date"],
            "currency": result["suggested_currency"],
            "stated_total": result["suggested_total"],
        },
    )
    assert receipt.status_code == 201
    assert receipt.json()["source"] == "image"
    assert receipt.json()["image_url"] == f"/receipts/{receipt.json()['id']}/image"
    assert receipt.json()["merchant_id"] is not None

    receipt_image = capture_client.get(receipt.json()["image_url"])
    download = capture_client.get(f"{receipt.json()['image_url']}?download=true")
    assert receipt_image.content == PNG_IMAGE
    assert receipt_image.headers["content-disposition"].startswith("inline;")
    assert download.headers["content-disposition"].startswith("attachment;")

    items = capture_client.get(f"/receipts/{receipt.json()['id']}/items").json()
    assert len(items) == 1
    assert items[0]["description"] == "Apfelsaft"
    assert items[0]["line_total"] == "12.34"

    linked = capture_client.get(f"/receipt-captures/{uploaded['id']}").json()
    assert linked["receipt_id"] == receipt.json()["id"]
    assert (
        capture_client.delete(f"/receipt-captures/{uploaded['id']}").status_code == 409
    )


def test_duplicate_and_invalid_images_are_rejected(
    capture_client: TestClient,
) -> None:
    upload_capture(capture_client)
    duplicate = capture_client.post(
        "/receipt-captures",
        files={"file": ("again.png", PNG_IMAGE, "image/png")},
    )
    invalid = capture_client.post(
        "/receipt-captures",
        files={"file": ("fake.png", b"not an image", "image/png")},
    )

    assert duplicate.status_code == 409
    assert invalid.status_code == 422


def test_upload_policy_and_oversized_image_return_clear_413(
    capture_client: TestClient,
) -> None:
    current = app.dependency_overrides[get_settings]()
    limited = current.model_copy(update={"receipt_image_max_bytes": 1024})
    app.dependency_overrides[get_settings] = lambda: limited

    policy = capture_client.get("/receipt-captures/upload-policy")
    oversized = capture_client.post(
        "/receipt-captures",
        files={"file": ("large.png", PNG_IMAGE + b"x" * 1024, "image/png")},
    )

    assert policy.status_code == 200
    assert policy.json()["max_bytes"] == 1024
    assert "image/png" in policy.json()["allowed_media_types"]
    assert oversized.status_code == 413
    assert oversized.json()["detail"] == (
        "Receipt image exceeds the 1 KB upload limit. "
        "Choose a smaller image or reduce its resolution."
    )


def test_ocr_failure_is_retained_and_manual_fallback_remains_available(
    capture_client: TestClient,
) -> None:
    uploaded = upload_capture(capture_client)
    app.dependency_overrides[get_ocr_provider] = lambda: FailingOcrProvider()

    ocr = capture_client.post(f"/receipt-captures/{uploaded['id']}/ocr")
    assert ocr.status_code == 200
    assert ocr.json()["ocr_status"] == "failed"
    assert ocr.json()["ocr_error"] == "Provider unavailable"

    receipt = capture_client.post(
        "/receipts",
        json={
            "capture_id": uploaded["id"],
            "purchase_date": "2026-07-23",
            "currency": "EUR",
            "stated_total": "12.34",
        },
    )
    assert receipt.status_code == 201
    assert receipt.json()["source"] == "image"


def test_receipt_suggestion_parser_handles_german_number_format() -> None:
    suggestions = extract_receipt_suggestions(
        "Demo Laden\n23.07.2026\nGesamt € 1.234,56"
    )

    assert suggestions.merchant_name == "Demo Laden"
    assert suggestions.purchase_date.isoformat() == "2026-07-23"
    assert suggestions.currency == "EUR"
    assert suggestions.total is not None
    assert str(suggestions.total) == "1234.56"


def test_azure_receipt_provider_uses_structured_fields() -> None:
    settings = get_settings().model_copy()
    result = AzureReceiptOcrProvider(settings, client=FakeAzureClient()).extract_text(
        PNG_IMAGE
    )

    assert result.provider == "azure-document-intelligence"
    assert result.suggestions is not None
    assert result.suggestions.merchant_name == "REWE Markt GmbH"
    assert result.suggestions.purchase_date.isoformat() == "2026-07-23"
    assert result.suggestions.currency == "EUR"
    assert result.suggestions.total == Decimal("12.34")
    assert result.suggestions.merchant_address == "Marktstrasse 1, Berlin"
    assert result.suggestions.merchant_phone == "+49 30 123456"
    assert result.suggestions.transaction_time == time(18, 42)
    assert result.suggestions.subtotal == Decimal("10.37")
    assert result.suggestions.tax == Decimal("1.97")
    assert result.provider_payload == {"modelId": "prebuilt-receipt"}
    assert len(result.line_items) == 1
    assert result.line_items[0].description == "Apfelsaft"
    assert result.line_items[0].quantity == Decimal("2")
    assert result.line_items[0].unit_price == Decimal("2.50")
    assert result.line_items[0].line_total == Decimal("5.00")


def test_azure_receipt_provider_compresses_only_ocr_copy() -> None:
    source = BytesIO()
    Image.new("RGB", (1400, 1800), "white").save(source, format="BMP")
    original = source.getvalue()
    settings = get_settings().model_copy(
        update={"azure_document_intelligence_max_bytes": 64 * 1024}
    )
    provider = AzureReceiptOcrProvider(settings, client=FakeAzureClient())

    optimized = provider._prepare_document(original)

    assert original.startswith(b"BM")
    assert optimized.startswith(b"\xff\xd8\xff")
    assert len(optimized) <= 64 * 1024
    assert source.getvalue() == original
