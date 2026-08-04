from app.services.text_normalization import normalize_barcode, normalize_receipt_item
from app.services.product import _alias_similarity


def test_product_text_normalization_handles_case_spacing_and_units() -> None:
    assert normalize_receipt_item("  JA! H-MILCH 1 L ") == "ja h milch 1l"
    assert normalize_receipt_item("Ja H-Milch 1L") == "ja h milch 1l"


def test_barcode_is_optional_and_sanitized() -> None:
    assert normalize_barcode(None) is None
    assert normalize_barcode("4001 2345 6789 0") == "4001234567890"
    assert normalize_barcode("123") is None


def test_fuzzy_alias_scoring_rewards_same_merchant_but_stays_review_only() -> None:
    description = "ja h milch 3 5 1l"
    alias = "ja haltbare milch 3 5 1l"

    other_merchant = _alias_similarity(description, alias, same_merchant=False)
    same_merchant = _alias_similarity(description, alias, same_merchant=True)

    assert same_merchant > other_merchant
    assert same_merchant <= 0.91
