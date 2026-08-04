from app.product_intelligence.contracts import ProductQuery
from app.product_intelligence.providers.tavily import TavilyResearchProvider, retailer_domains


def test_tavily_uses_retailer_domain_and_returns_cited_candidate() -> None:
    captured: dict[str, object] = {}

    def transport(url, payload, timeout, headers):
        captured.update(url=url, payload=payload, timeout=timeout, headers=headers)
        return {"results": [{
            "title": "Ja! H-Vollmilch 3,5% 1L",
            "url": "https://www.rewe.de/produkte/ja-vollmilch/",
            "content": "Haltbare Vollmilch der Marke Ja!",
            "score": 0.9,
        }]}

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
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert candidates[0].provider == "tavily_web"
    assert candidates[0].source_url == "https://www.rewe.de/produkte/ja-vollmilch/"
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


def test_retailer_domains_are_explicit() -> None:
    assert retailer_domains("ALDI SÜD") == ["aldi-sued.de"]
    assert retailer_domains("Independent shop") == []
