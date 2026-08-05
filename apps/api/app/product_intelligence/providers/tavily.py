from __future__ import annotations

import re
from dataclasses import replace
from typing import TypedDict
from urllib.parse import urlparse

from app.product_intelligence.contracts import ProductCandidate, ProductQuery
from app.product_intelligence.http import JsonPostTransport, post_json
from app.product_intelligence.extractors import ProductTextExtractor
from app.services.text_normalization import (
    normalize_product_name,
    product_search_similarity,
)


RETAILER_DOMAINS = {
    "rewe": ["rewe.de"],
    "aldi nord": ["aldi-nord.de"],
    "aldi sued": ["aldi-sued.de"],
    "aldi sud": ["aldi-sued.de"],
    "aldi süd": ["aldi-sued.de"],
    "edeka": ["edeka.de"],
    "lidl": ["lidl.de"],
    "penny": ["penny.de"],
    "netto": ["netto-online.de"],
    "kaufland": ["kaufland.de"],
}
RETAILER_PRODUCT_PATHS = {"rewe.de": ("/shop/p/",)}
NUTRITION_LABELS = {
    "energie": ("energy_kcal", "kcal"),
    "fett": ("fat_g", "g"),
    "fett davon gesaettigte fettsaeuren": ("saturated_fat_g", "g"),
    "kohlenhydrate": ("carbohydrate_g", "g"),
    "kohlenhydrate davon zucker": ("sugars_g", "g"),
    "ballaststoffe": ("fiber_g", "g"),
    "eiweiss": ("protein_g", "g"),
    "salz": ("salt_g", "g"),
}
BRAND_PREFIXES = (
    "ja!",
    "REWE Bio",
    "REWE Regional",
    "REWE Beste Wahl",
    "Wilhelm Brandenburg",
    "Original Wagner",
    "Wiesenhof",
    "Stolle",
)
GENERIC_TITLE_PREFIXES = {
    "bio",
    "frisch",
    "haehnchen",
    "haehnchenmaegen",
    "milch",
    "pizza",
    "steinofen",
    "tiefkuehl",
    "vollmilch",
    "weizen",
    "wraps",
}


class ResearchState(TypedDict):
    query: ProductQuery
    search_text: str
    domains: list[str]
    results: list[dict[str, object]]
    candidates: list[ProductCandidate]


class TavilyResearchProvider:
    """Merchant-aware web research represented as an explicit LangGraph flow."""

    name = "tavily_web"

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        timeout: float,
        result_limit: int = 5,
        transport: JsonPostTransport = post_json,
    ) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self.result_limit = result_limit
        self.transport = transport
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.graph = self._build_graph()

    def search(self, query: ProductQuery) -> list[ProductCandidate]:
        if query.barcode or not query.description.strip():
            return []
        result = self.graph.invoke({"query": query})
        return result.get("candidates", [])

    def _build_graph(self):
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(ResearchState)
        graph.add_node("prepare", self._prepare)
        graph.add_node("search", self._search)
        graph.add_node("extract", self._extract)
        graph.add_edge(START, "prepare")
        graph.add_edge("prepare", "search")
        graph.add_edge("search", "extract")
        graph.add_edge("extract", END)
        return graph.compile()

    def _prepare(self, state: ResearchState) -> dict[str, object]:
        query = state["query"]
        merchant = query.merchant_name or "German retailer"
        description = " ".join(query.description.split())
        return {
            # OCR abbreviations and punctuation rarely match catalogue titles exactly.
            # Keep the terms unquoted so Tavily can broaden spelling and word forms.
            "search_text": f"{description} {merchant}",
            "domains": retailer_domains(query.merchant_name),
        }

    def _search(self, state: ResearchState) -> dict[str, object]:
        payload: dict[str, object] = {
            "query": state["search_text"],
            "search_depth": "basic",
            "max_results": self.result_limit,
            "include_answer": False,
            "include_raw_content": "markdown",
        }
        if state["domains"]:
            payload["include_domains"] = state["domains"]
        response = self.transport(self.endpoint, payload, self.timeout, self.headers)
        results = response.get("results")
        return {"results": results if isinstance(results, list) else []}

    def _extract(self, state: ResearchState) -> dict[str, object]:
        candidates = [
            candidate
            for result in state["results"]
            if isinstance(result, dict)
            if (candidate := _candidate(state, result)) is not None
        ]
        return {"candidates": candidates[: self.result_limit]}


def retailer_domains(merchant_name: str | None) -> list[str]:
    normalized = normalize_product_name(merchant_name or "")
    return next(
        (domains for name, domains in RETAILER_DOMAINS.items() if name in normalized),
        [],
    )


def _candidate(
    state: ResearchState, result: dict[str, object]
) -> ProductCandidate | None:
    title = str(result.get("title") or "").strip()
    url = str(result.get("url") or "").strip()
    if not title or not url:
        return None
    query = state["query"]
    similarity = product_search_similarity(query.description, title)
    provider_score = _number(result.get("score"))
    domain = urlparse(url).netloc.removeprefix("www.")
    domain_match = any(
        domain == allowed or domain.endswith(f".{allowed}")
        for allowed in state["domains"]
    )
    allowed_paths = RETAILER_PRODUCT_PATHS.get(domain)
    product_page = bool(allowed_paths and urlparse(url).path.startswith(allowed_paths))
    if allowed_paths and not product_page:
        return None
    if not product_page and similarity < 0.30:
        return None
    confidence = round(
        min(
            0.90,
            0.35
            + 0.25 * similarity
            + 0.15 * provider_score
            + (0.10 if domain_match else 0)
            + (0.10 if product_page else 0),
        ),
        3,
    )
    nutrition = _nutrition(str(result.get("raw_content") or ""))
    brand = _brand(title, str(result.get("raw_content") or ""), url)
    return ProductCandidate(
        canonical_name=title,
        provider="tavily_web",
        confidence=confidence,
        description=str(result.get("content") or "").strip() or None,
        brand=brand,
        source_url=url,
        external_id=url,
        product_type="food" if nutrition else "other",
        nutrition=nutrition,
        evidence={
            "level": "possible" if confidence >= 0.65 else "weak",
            "search_query": state["search_text"],
            "matched_domain": domain,
            "merchant_domain_match": domain_match,
            "retailer_product_page": product_page,
            "nutrition_extracted": bool(nutrition),
            "text_similarity": round(similarity, 3),
            "provider_score": round(provider_score, 3),
            "score_formula": (
                "0.35 + 0.25 × text similarity + 0.15 × search score + "
                "0.10 retailer-domain bonus (maximum 0.85)"
            ),
            "reason": "Merchant-aware Tavily web result; confirmation is required",
            "ai_generated": False,
        },
    )


def _number(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _nutrition(markdown: str) -> dict[str, object]:
    nutrition: dict[str, object] = {}
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in markdown.splitlines()
        if line.lstrip().startswith("|")
    ]
    for cells in rows:
        if len(cells) < 2:
            continue
        label, raw_value = cells[0], cells[1]
        normalized = normalize_product_name(label).translate(
            str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
        )
        target = NUTRITION_LABELS.get(normalized)
        if not target or (target[1] == "kcal" and "kcal" not in raw_value.casefold()):
            continue
        match = re.search(r"<?\s*(\d+(?:[.,]\d+)?)", raw_value)
        if match:
            nutrition[target[0]] = float(match.group(1).replace(",", "."))
    if nutrition:
        nutrition.update({"basis_quantity": 100, "basis_unit": "g"})
    return nutrition


def _brand(title: str, markdown: str, source_url: str | None = None) -> str | None:
    explicit = re.search(r"^### Marke:\s*\n+([^#|\n][^\n]*)", markdown, re.MULTILINE)
    if explicit:
        return explicit.group(1).strip()
    comparison = title.casefold()
    known = next(
        (brand for brand in BRAND_PREFIXES if comparison.startswith(brand.casefold())),
        None,
    )
    if known or not source_url:
        return known
    clean_title = re.split(r"\s+bei\s+REWE", title, flags=re.IGNORECASE)[0]
    words = clean_title.split()
    slug = urlparse(source_url).path.rsplit("/", 2)[-2].casefold()
    first = words[0].strip("!.,").casefold() if words else ""
    normalized_first = normalize_product_name(first).translate(
        str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
    )
    if (
        len(words) >= 3
        and normalized_first not in GENERIC_TITLE_PREFIXES
        and slug.startswith(f"{normalized_first}-")
    ):
        return words[0].rstrip(".,")
    return None


def extract_tavily_candidate(
    candidate: ProductCandidate,
    *,
    search_endpoint: str,
    api_key: str,
    timeout: float,
    transport: JsonPostTransport = post_json,
    extractor: ProductTextExtractor | None = None,
) -> ProductCandidate:
    if not candidate.source_url:
        return candidate
    endpoint = f"{search_endpoint.rsplit('/', 1)[0]}/extract"
    response = transport(
        endpoint,
        {
            "urls": [candidate.source_url],
            "extract_depth": "basic",
            "format": "markdown",
        },
        timeout,
        {"Authorization": f"Bearer {api_key}"},
    )
    results = response.get("results")
    if not isinstance(results, list) or not results:
        return candidate
    markdown = str(results[0].get("raw_content") or "")
    nutrition = _nutrition(markdown)
    extracted: dict[str, object] = {}
    if extractor and markdown:
        try:
            extracted = extractor.extract(markdown)
        except Exception:
            extracted = {}
    llm_nutrition = extracted.get("nutrition")
    if isinstance(llm_nutrition, dict):
        nutrition = {
            **nutrition,
            **{key: value for key, value in llm_nutrition.items() if value is not None},
        }
        if nutrition:
            nutrition.update({"basis_quantity": 100, "basis_unit": "g"})
    ingredients = extracted.get("ingredients")
    return replace(
        candidate,
        brand=candidate.brand
        or extracted.get("brand")
        or _brand(candidate.canonical_name, markdown, candidate.source_url),
        manufacturer=candidate.manufacturer or extracted.get("manufacturer"),
        product_type="food" if nutrition else candidate.product_type,
        nutrition=nutrition or candidate.nutrition,
        metadata={
            **candidate.metadata,
            **({"ingredients": ingredients} if ingredients else {}),
        },
        evidence={
            **candidate.evidence,
            "details_extracted": bool(markdown),
            "nutrition_extracted": bool(nutrition),
            "llm_structured_extraction_used": bool(extracted),
            "source_content": markdown,
        },
    )
