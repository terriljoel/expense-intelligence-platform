from app.product_intelligence.contracts import ProductQuery
from app.product_intelligence.providers.open_food_facts import OpenFoodFactsProvider


def _provider(payload: dict[str, object]) -> OpenFoodFactsProvider:
    return OpenFoodFactsProvider(
        base_url="https://example.test",
        timeout=5,
        user_agent="test/1.0",
        transport=lambda *_: payload,
    )


def test_barcode_lookup_maps_product_and_nutrition() -> None:
    provider = _provider(
        {
            "product": {
                "code": "4001234567890",
                "product_name_de": "Vollmilch 3,5%",
                "brands": "Example",
                "categories": "Milchprodukte",
                "quantity": "1 l",
                "nutriments": {
                    "energy-kcal_100g": 64,
                    "fat_100g": 3.5,
                    "proteins_100g": 3.3,
                },
            }
        }
    )

    candidates = provider.search(
        ProductQuery(description="H-MILCH", barcode="4001234567890")
    )

    assert len(candidates) == 1
    assert candidates[0].canonical_name == "Vollmilch 3,5%"
    assert candidates[0].nutrition == {
        "energy_kcal": 64,
        "fat_g": 3.5,
        "protein_g": 3.3,
        "basis_quantity": 100,
        "basis_unit": "g",
    }


def test_missing_barcode_skips_barcode_provider() -> None:
    called = False

    def transport(*_: object) -> dict[str, object]:
        nonlocal called
        called = True
        return {}

    provider = OpenFoodFactsProvider(
        base_url="https://example.test",
        timeout=5,
        user_agent="test/1.0",
        transport=transport,
    )

    assert provider.search(ProductQuery(description="Milk")) == []
    assert called is False
