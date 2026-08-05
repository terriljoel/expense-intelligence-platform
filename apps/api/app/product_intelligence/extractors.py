import json
from typing import Protocol

from app.product_intelligence.http import JsonPostTransport, post_json
from app.product_intelligence.rankers import _output_text


class ProductTextExtractor(Protocol):
    def extract(self, source_text: str) -> dict[str, object]: ...


class GitHubModelsProductExtractor:
    """Convert cited product text into conservative, structured product facts."""

    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        token: str,
        timeout: float,
        transport: JsonPostTransport = post_json,
    ) -> None:
        self.url = f"{endpoint.rstrip('/')}/chat/completions"
        self.model, self.timeout, self.transport = model, timeout, transport
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2026-03-10",
        }

    def extract(self, source_text: str) -> dict[str, object]:
        response = self.transport(
            self.url,
            {
                "model": self.model,
                "max_tokens": 700,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Extract product facts only when explicitly present in the supplied "
                            "source. Do not infer or calculate missing values. Nutrition must use "
                            "the per-100-g or per-100-ml column, never the package/portion column. "
                            "Use kcal for energy_kcal and grams for nutrient fields. Return only "
                            "one JSON object matching this schema: "
                            + json.dumps(_SCHEMA)
                        ),
                    },
                    {"role": "user", "content": source_text[:24000]},
                ],
            },
            self.timeout,
            self.headers,
        )
        data = json.loads(_output_text(response))
        return data if isinstance(data, dict) else {}


_NUTRIENT_PROPERTIES = {
    name: {"type": ["number", "null"], "minimum": 0}
    for name in (
        "energy_kcal",
        "fat_g",
        "saturated_fat_g",
        "carbohydrate_g",
        "sugars_g",
        "fiber_g",
        "protein_g",
        "salt_g",
    )
}
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "brand": {"type": ["string", "null"]},
        "manufacturer": {"type": ["string", "null"]},
        "ingredients": {"type": ["string", "null"]},
        "nutrition": {
            "type": "object",
            "additionalProperties": False,
            "properties": _NUTRIENT_PROPERTIES,
        },
    },
    "required": ["brand", "manufacturer", "ingredients", "nutrition"],
}
