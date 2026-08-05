from urllib.parse import urlencode

from app.product_intelligence.contracts import ProductCandidate, ProductQuery
from app.product_intelligence.http import JsonTransport, get_json
from app.services.text_normalization import product_search_similarity


FIELDS = (
    "code",
    "product_name",
    "product_name_de",
    "generic_name",
    "generic_name_de",
    "brands",
    "categories",
    "quantity",
    "ingredients_text",
    "allergens",
    "countries",
    "image_front_url",
)


class SearchALiciousProvider:
    name = "search_a_licious"

    def __init__(
        self,
        *,
        base_url: str,
        timeout: float,
        user_agent: str,
        result_limit: int = 5,
        transport: JsonTransport = get_json,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.result_limit = result_limit
        self.headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self.transport = transport

    def search(self, query: ProductQuery) -> list[ProductCandidate]:
        if query.barcode or not query.description.strip():
            return []
        params = urlencode(
            {
                "q": query.description,
                "page_size": self.result_limit,
                "boost_phrase": "true",
                "langs": f"{query.language},en",
                "fields": ",".join(FIELDS),
            }
        )
        payload = self.transport(
            f"{self.base_url}/search?{params}", self.timeout, self.headers
        )
        hits = payload.get("hits")
        if not isinstance(hits, list):
            return []
        return [
            candidate
            for hit in hits
            if isinstance(hit, dict)
            if (candidate := self._candidate(query, hit)) is not None
        ][: self.result_limit]

    def _candidate(
        self, query: ProductQuery, product: dict[str, object]
    ) -> ProductCandidate | None:
        name = _text(product, "product_name_de", "product_name")
        if not name:
            return None
        similarity = product_search_similarity(query.description, name)
        if similarity < 0.55:
            return None
        confidence = round(min(0.89, 0.55 + 0.34 * similarity), 3)
        code = _text(product, "code")
        return ProductCandidate(
            canonical_name=name,
            provider=self.name,
            confidence=confidence,
            barcode=code,
            description=_text(product, "generic_name_de", "generic_name"),
            brand=_text(product, "brands"),
            product_type="food",
            category=_text(product, "categories"),
            source_url=(
                f"https://world.openfoodfacts.org/product/{code}" if code else None
            ),
            external_id=code,
            metadata=_compact(
                product,
                "quantity",
                "ingredients_text",
                "allergens",
                "countries",
                "image_front_url",
            ),
            evidence={
                "level": "possible" if similarity >= 0.7 else "weak",
                "text_similarity": round(similarity, 3),
                "score_formula": "0.55 + 0.34 × text similarity (maximum 0.89)",
                "reason": "Text search in the Open Food Facts search index",
                "ai_generated": False,
            },
        )


def _text(data: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, dict):
            value = value.get("de") or value.get("en")
        if value:
            return str(value).strip()
    return None


def _compact(data: dict[str, object], *keys: str) -> dict[str, object]:
    return {key: data[key] for key in keys if data.get(key) not in (None, "", [], {})}
