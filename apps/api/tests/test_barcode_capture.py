from io import BytesIO

from PIL import Image
from fastapi.testclient import TestClient
import zxingcpp

from app.main import app
from app.product_intelligence.taxonomy import infer_family
from app.services.barcode_decoder import decode_barcode


def test_decodes_ean13_from_stored_image_bytes() -> None:
    barcode = zxingcpp.create_barcode("4006381333931", zxingcpp.BarcodeFormat.EAN13)
    image = Image.fromarray(barcode.to_image(scale=5))
    content = BytesIO()
    image.save(content, format="PNG")

    value, barcode_format, error = decode_barcode(content.getvalue())

    assert value == "4006381333931"
    assert "EAN" in barcode_format
    assert error is None


def test_semantic_family_is_separate_from_specific_product() -> None:
    assert infer_family("Ja! Haltbare Vollmilch 3,5%, 1 L") == ("Milk", "Dairy")
    assert infer_family("XL Pizza Salami") == ("Pizza", "Prepared food")


def test_barcode_photo_is_decoded_without_storage() -> None:
    barcode = zxingcpp.create_barcode("4006381333931", zxingcpp.BarcodeFormat.EAN13)
    image = Image.fromarray(barcode.to_image(scale=5))
    content = BytesIO()
    image.save(content, format="PNG")

    with TestClient(app) as client:
        receipt = client.post(
            "/receipts",
            json={
                "purchase_date": "2026-08-03",
                "currency": "EUR",
                "stated_total": "1.00",
            },
        ).json()
        item = client.post(
            f"/receipts/{receipt['id']}/items",
            json={
                "position": 1,
                "line_type": "product",
                "description": "Test milk",
                "line_total": "1.00",
            },
        ).json()
        response = client.post(
            f"/receipt-items/{item['id']}/barcode-detect",
            files={"file": ("barcode.png", content.getvalue(), "image/png")},
        )

    assert response.status_code == 200
    assert response.json() == {
        "detected_barcode": "4006381333931",
        "barcode_format": "EAN-13",
        "error_message": None,
    }
