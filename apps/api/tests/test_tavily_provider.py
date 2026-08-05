from app.product_intelligence.contracts import ProductCandidate, ProductQuery
from app.product_intelligence.providers.tavily import (
    TavilyResearchProvider,
    extract_tavily_candidate,
    retailer_domains,
)


def test_tavily_uses_retailer_domain_and_returns_cited_candidate() -> None:
    captured: dict[str, object] = {}

    def transport(url, payload, timeout, headers):
        captured.update(url=url, payload=payload, timeout=timeout, headers=headers)
        return {
            "results": [
                {
                    "title": "Ja! H-Vollmilch 3,5% 1L",
                    "url": "https://www.rewe.de/shop/p/ja-vollmilch/1234567",
                    "content": "Haltbare Vollmilch der Marke Ja!",
                    "score": 0.9,
                }
            ]
        }

    provider = TavilyResearchProvider(
        endpoint="https://api.tavily.com/search",
        api_key="secret",
        timeout=7,
        transport=transport,
    )
    candidates = provider.search(
        ProductQuery(description="JA H MILCH 3.5 1L", merchant_name="REWE Markt")
    )

    assert captured["payload"]["include_domains"] == ["rewe.de"]
    assert captured["payload"]["query"] == "JA H MILCH 3.5 1L REWE Markt"
    assert '"' not in captured["payload"]["query"]
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert candidates[0].provider == "tavily_web"
    assert candidates[0].source_url == "https://www.rewe.de/shop/p/ja-vollmilch/1234567"
    assert candidates[0].evidence["merchant_domain_match"] is True
    assert candidates[0].confidence < 0.92


def test_tavily_skips_barcode_queries() -> None:
    provider = TavilyResearchProvider(
        endpoint="https://api.tavily.com/search",
        api_key="secret",
        timeout=7,
        transport=lambda *_: (_ for _ in ()).throw(AssertionError("not called")),
    )
    assert provider.search(ProductQuery("Milk", barcode="4001234567890")) == []


def test_tavily_does_not_put_branch_address_in_product_query() -> None:
    captured: dict[str, object] = {}

    def transport(_url, payload, _timeout, _headers):
        captured.update(payload)
        return {"results": []}

    provider = TavilyResearchProvider(
        endpoint="https://api.tavily.com/search",
        api_key="secret",
        timeout=7,
        transport=transport,
    )
    provider.search(
        ProductQuery(
            "HA-MAEGEN",
            merchant_name="REWE",
            merchant_address="Wendenring 1-4, 38114 Braunschweig",
        )
    )

    assert captured["query"] == "HA-MAEGEN REWE"
    assert "Wendenring" not in captured["query"]


def test_retailer_domains_are_explicit() -> None:
    assert retailer_domains("ALDI SÜD") == ["aldi-sued.de"]
    assert retailer_domains("Independent shop") == []


def test_tavily_rejects_retailer_navigation_pages() -> None:
    provider = TavilyResearchProvider(
        endpoint="https://api.tavily.com/search",
        api_key="secret",
        timeout=7,
        transport=lambda *_: {
            "results": [
                {
                    "title": "REWE Supermärkte - REWE.de",
                    "url": "https://www.rewe.de/marktsuche/83000",
                    "content": "Store search",
                    "score": 0.9,
                }
            ]
        },
    )

    assert provider.search(ProductQuery("HA-MAEGEN", merchant_name="REWE")) == []


def test_tavily_extracts_rewe_nutrition_from_cited_page() -> None:
    provider = TavilyResearchProvider(
        endpoint="https://api.tavily.com/search",
        api_key="secret",
        timeout=7,
        transport=lambda *_: {
            "results": [
                {
                    "title": "REWE Regional Hähnchenmägen 350g",
                    "url": "https://www.rewe.de/shop/p/rewe-regional-haehnchenmaegen-350g/8732207",
                    "score": 0.9,
                    "raw_content": """
| Nährwerte | pro 100 g |
| --- | --- |
| Energie | 343 kJ |
| Energie | 81 kcal |
| Fett | 2 g |
| Fett, davon gesättigte Fettsäuren | 0,9 g |
| Kohlenhydrate | 0 g |
| Kohlenhydrate, davon Zucker | 0 g |
| Ballaststoffe | 0 g |
| Eiweiß | 15,8 g |
| Salz | 0,18 g |
""",
                }
            ]
        },
    )

    candidate = provider.search(ProductQuery("HA-MAEGEN", merchant_name="REWE"))[0]
    assert candidate.product_type == "food"
    assert candidate.brand == "REWE Regional"
    assert candidate.nutrition == {
        "energy_kcal": 81.0,
        "fat_g": 2.0,
        "saturated_fat_g": 0.9,
        "carbohydrate_g": 0.0,
        "sugars_g": 0.0,
        "fiber_g": 0.0,
        "protein_g": 15.8,
        "salt_g": 0.18,
        "basis_quantity": 100,
        "basis_unit": "g",
    }


def test_selected_tavily_candidate_extracts_brand_and_nutrition() -> None:
    captured: dict[str, object] = {}

    def transport(url, payload, timeout, headers):
        captured.update(url=url, payload=payload, timeout=timeout, headers=headers)
        return {
            "results": [
                {
                    "raw_content": """
# ja! Steinofen Pizza Margherita 3x300g
| Nährwerte | pro 100 g |
| --- | --- |
| Energie | 220 kcal |
| Fett | 8,5 g |
| Eiweiß | 9,1 g |
| Salz | 1,2 g |
""",
                }
            ]
        }

    candidate = extract_tavily_candidate(
        ProductCandidate(
            canonical_name="ja! Steinofen Pizza Margherita 3x300g",
            provider="tavily_web",
            confidence=0.8,
            source_url="https://www.rewe.de/shop/p/ja-pizza/123",
        ),
        search_endpoint="https://api.tavily.com/search",
        api_key="secret",
        timeout=7,
        transport=transport,
    )

    assert captured["url"] == "https://api.tavily.com/extract"
    assert candidate.brand == "ja!"
    assert candidate.product_type == "food"
    assert candidate.nutrition["energy_kcal"] == 220.0


def test_tavily_extracts_first_values_from_multi_column_nutrition_table() -> None:
    candidate = extract_tavily_candidate(
        ProductCandidate(
            canonical_name="ja! Steinofen Pizza",
            provider="tavily_web",
            confidence=0.8,
            source_url="https://www.rewe.de/shop/p/ja-pizza/123",
        ),
        search_endpoint="https://api.tavily.com/search",
        api_key="secret",
        timeout=7,
        transport=lambda *_: {
            "results": [
                {
                    "raw_content": """
| Nährwerte | pro 100 g | % NRV (100 g) | pro 300 g | % NRV (300 g) |
| --- | --- | --- | --- | --- |
| Energie | 919 kJ | | 2.756 kJ | |
| Energie | 218 kcal | | 653 kcal | |
| Fett | 4,3 g | 6.1 % | 12,9 g | 18.4 % |
| Eiweiß | 9 g | 18 % | 27 g | 54 % |
| Salz | 0,9 g | 15 % | 2,7 g | 45 % |
"""
                }
            ]
        },
    )

    assert candidate.nutrition == {
        "energy_kcal": 218.0,
        "fat_g": 4.3,
        "protein_g": 9.0,
        "salt_g": 0.9,
        "basis_quantity": 100,
        "basis_unit": "g",
    }


def test_tavily_merges_optional_llm_structured_extraction() -> None:
    class Extractor:
        def extract(self, _source_text):
            return {
                "brand": "ja!",
                "manufacturer": "Example GmbH",
                "ingredients": "Weizenmehl, Wasser",
                "nutrition": {"protein_g": 9.0, "salt_g": 0.9},
            }

    candidate = extract_tavily_candidate(
        ProductCandidate(
            canonical_name="Steinofen Pizza",
            provider="tavily_web",
            confidence=0.8,
            source_url="https://www.rewe.de/shop/p/ja-pizza/123",
        ),
        search_endpoint="https://api.tavily.com/search",
        api_key="secret",
        timeout=7,
        extractor=Extractor(),
        transport=lambda *_: {"results": [{"raw_content": "product text"}]},
    )

    assert candidate.brand == "ja!"
    assert candidate.manufacturer == "Example GmbH"
    assert candidate.metadata["ingredients"] == "Weizenmehl, Wasser"
    assert candidate.nutrition["protein_g"] == 9.0
    assert candidate.evidence["llm_structured_extraction_used"] is True


def test_tavily_infers_non_generic_brand_from_retailer_title_and_slug() -> None:
    provider = TavilyResearchProvider(
        endpoint="https://api.tavily.com/search",
        api_key="secret",
        timeout=7,
        transport=lambda *_: {
            "results": [
                {
                    "title": "Mestemacher Weizen-Wraps XL 280g",
                    "url": "https://www.rewe.de/shop/p/mestemacher-weizen-wraps-xl-280g/436792",
                    "score": 0.9,
                }
            ]
        },
    )

    candidate = provider.search(ProductQuery("CALI, WRAPS XL", merchant_name="REWE"))[0]
    assert candidate.brand == "Mestemacher"
