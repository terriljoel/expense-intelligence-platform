from __future__ import annotations

from difflib import SequenceMatcher
from typing import TypedDict
from urllib.parse import urlparse

from app.product_intelligence.contracts import ProductCandidate, ProductQuery
from app.product_intelligence.http import JsonPostTransport, post_json
from app.services.text_normalization import normalize_product_name


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
        address = f" {query.merchant_address}" if query.merchant_address else ""
        return {
            "search_text": f'"{query.description}" {merchant}{address} product',
            "domains": retailer_domains(query.merchant_name),
        }

    def _search(self, state: ResearchState) -> dict[str, object]:
        payload: dict[str, object] = {
            "query": state["search_text"],
            "search_depth": "basic",
            "max_results": self.result_limit,
            "include_answer": False,
            "include_raw_content": False,
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
    similarity = SequenceMatcher(
        None, normalize_product_name(query.description), normalize_product_name(title)
    ).ratio()
    provider_score = _number(result.get("score"))
    domain = urlparse(url).netloc.removeprefix("www.")
    domain_match = any(
        domain == allowed or domain.endswith(f".{allowed}")
        for allowed in state["domains"]
    )
    confidence = round(
        min(
            0.85,
            0.35
            + 0.25 * similarity
            + 0.15 * provider_score
            + (0.10 if domain_match else 0),
        ),
        3,
    )
    return ProductCandidate(
        canonical_name=title,
        provider="tavily_web",
        confidence=confidence,
        description=str(result.get("content") or "").strip() or None,
        source_url=url,
        external_id=url,
        evidence={
            "level": "possible" if confidence >= 0.65 else "weak",
            "search_query": state["search_text"],
            "matched_domain": domain,
            "merchant_domain_match": domain_match,
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
