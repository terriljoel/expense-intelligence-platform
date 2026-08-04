from app.product_intelligence.contracts import ProductQuery
from app.product_intelligence.providers.search_a_licious import SearchALiciousProvider


def _provider(payload: dict[str, object]) -> SearchALiciousProvider:
    return SearchALiciousProvider(
        base_url="https://search.example.test",
        timeout=5,
        user_agent="test/1.0",
        transport=lambda *_: payload,
    )


def test_text_search_maps_hits_to_review_candidates() -> None:
    provider = _provider(
        {
            "hits": [
                {
                    "code": "4001234567890",
                    "product_name_de": "Ja! Haltbare Vollmilch 3,5%",
                    "brands": "Ja!",
                    "categories": "Milchprodukte",
                    "quantity": "1 l",
                }
            ]
        }
    )

    candidates = provider.search(ProductQuery(description="JA H MILCH 3 5 1L"))

    assert len(candidates) == 1
    assert candidates[0].provider == "search_a_licious"
    assert candidates[0].barcode == "4001234567890"
    assert candidates[0].confidence < 0.92


def test_barcode_query_is_left_to_exact_barcode_provider() -> None:
    provider = _provider({"hits": [{"product_name": "Ignored"}]})

    assert (
        provider.search(ProductQuery(description="Milk", barcode="4001234567890")) == []
    )


def test_invalid_response_returns_no_candidates() -> None:
    assert _provider({"errors": []}).search(ProductQuery(description="Milk")) == []
