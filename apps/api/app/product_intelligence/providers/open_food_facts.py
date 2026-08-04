from urllib.parse import urlencode

from app.product_intelligence.contracts import ProductCandidate, ProductQuery
from app.product_intelligence.http import JsonTransport, get_json


FIELDS = (
    "code,product_name,product_name_de,generic_name,generic_name_de,brands,"
    "categories,quantity,ingredients_text,allergens,countries,image_front_url,nutriments"
)
NUTRIENTS = {
    "energy-kcal_100g": "energy_kcal",
    "fat_100g": "fat_g",
    "saturated-fat_100g": "saturated_fat_g",
    "carbohydrates_100g": "carbohydrate_g",
    "sugars_100g": "sugars_g",
    "fiber_100g": "fiber_g",
    "proteins_100g": "protein_g",
    "salt_100g": "salt_g",
}


class OpenFoodFactsProvider:
    name = "open_food_facts"

    def __init__(
        self,
        *,
        base_url: str,
        timeout: float,
        user_agent: str,
        transport: JsonTransport = get_json,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {"User-Agent": user_agent, "Accept": "application/json"}
        self.transport = transport

    def search(self, query: ProductQuery) -> list[ProductCandidate]:
        if not query.barcode:
            return []
        params = urlencode(
            {"fields": FIELDS, "cc": query.country, "lc": query.language}
        )
        payload = self.transport(
            f"{self.base_url}/api/v3/product/{query.barcode}?{params}",
            self.timeout,
            self.headers,
        )
        product = payload.get("product")
        if not isinstance(product, dict):
            return []
        name = _text(product, "product_name_de", "product_name")
        if not name:
            return []
        nutriments = (
            product.get("nutriments")
            if isinstance(product.get("nutriments"), dict)
            else {}
        )
        nutrition = {
            target: nutriments[source]
            for source, target in NUTRIENTS.items()
            if nutriments.get(source) is not None
        }
        if nutrition:
            nutrition.update({"basis_quantity": 100, "basis_unit": "g"})
        code = str(product.get("code") or query.barcode)
        return [
            ProductCandidate(
                canonical_name=name,
                provider=self.name,
                confidence=0.99,
                barcode=code,
                description=_text(product, "generic_name_de", "generic_name"),
                brand=_text(product, "brands"),
                product_type="food",
                category=_text(product, "categories"),
                source_url=f"https://world.openfoodfacts.org/product/{code}",
                external_id=code,
                metadata=_compact(
                    product,
                    "quantity",
                    "ingredients_text",
                    "allergens",
                    "countries",
                    "image_front_url",
                ),
                nutrition=nutrition,
                evidence={
                    "level": "verified",
                    "barcode_exact": code == query.barcode,
                    "barcode": code,
                    "reason": "Exact barcode lookup in Open Food Facts",
                    "ai_generated": False,
                },
            )
        ]


def _text(data: dict[str, object], *keys: str) -> str | None:
    return next((str(data[key]).strip() for key in keys if data.get(key)), None)


def _compact(data: dict[str, object], *keys: str) -> dict[str, object]:
    return {key: data[key] for key in keys if data.get(key) not in (None, "", [], {})}
