from app.services.duplicate_receipt import normalize_receipt_number
from app.integrations.azure.document_intelligence import AzureReceiptOcrProvider
from app.services.receipt_capture import detect_merchant_address, detect_receipt_number


def test_extracts_common_german_receipt_number_labels() -> None:
    assert detect_receipt_number("Bon-Nr.: 0012/847-AB") == "0012/847-AB"
    assert detect_receipt_number("Beleg Nummer: 998877") == "998877"


def test_extracts_english_transaction_identifier() -> None:
    assert detect_receipt_number("Transaction ID: TX-8821") == "TX-8821"


def test_receipt_number_normalization_ignores_case_and_punctuation() -> None:
    assert normalize_receipt_number(" TX-88/21 ") == "tx8821"
    assert normalize_receipt_number("tx8821") == "tx8821"


def test_reads_azure_address_field_content() -> None:
    field = {
        "type": "address",
        "content": "Langer Kamp 3\n38106 Braunschweig",
        "valueAddress": {
            "road": "Langer Kamp",
            "houseNumber": "3",
            "postalCode": "38106",
            "city": "Braunschweig",
        },
    }
    assert AzureReceiptOcrProvider._address(field) == (
        "Langer Kamp 3, 38106 Braunschweig"
    )


def test_falls_back_to_german_address_in_raw_text() -> None:
    text = "EDEKA\nEdeka Görge\nLanger Kamp 3\n38106 Braunschweig\nSUMME 9,92"
    assert detect_merchant_address(text) == "Langer Kamp 3, 38106 Braunschweig"
