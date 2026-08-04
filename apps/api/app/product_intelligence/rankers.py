import json
from dataclasses import dataclass
from typing import Protocol

from app.product_intelligence.contracts import ProductCandidate, ProductQuery
from app.product_intelligence.http import JsonPostTransport, post_json


@dataclass(frozen=True)
class RankingDecision:
    selected_index: int
    canonical_name: str
    confidence: float
    should_match: bool
    explanation: str
    family_name: str | None = None
    category: str | None = None


class CandidateRanker(Protocol):
    def rank(
        self, query: ProductQuery, candidates: list[ProductCandidate]
    ) -> RankingDecision: ...


class GitHubModelsRanker:
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

    def rank(
        self, query: ProductQuery, candidates: list[ProductCandidate]
    ) -> RankingDecision:
        response = self.transport(
            self.url, self._payload(query, candidates), self.timeout, self.headers
        )
        data = json.loads(_output_text(response))
        decision = RankingDecision(**data)
        if (
            not 0 <= decision.selected_index < len(candidates)
            or not 0 <= decision.confidence <= 1
        ):
            raise ValueError("AI ranking decision is outside the valid range")
        return decision

    def _payload(
        self, query: ProductQuery, candidates: list[ProductCandidate]
    ) -> dict[str, object]:
        evidence = [
            {"index": index, **candidate.as_dict()}
            for index, candidate in enumerate(candidates)
        ]
        return {
            "model": self.model,
            "max_tokens": 400,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Rank product candidates using only supplied evidence. Never invent "
                        "manufacturer, barcode, nutrition, or ingredients. Return only one JSON "
                        "object matching this schema: " + json.dumps(_SCHEMA)
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "receipt_description": query.description,
                            "candidates": evidence,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }


def _output_text(response: dict[str, object]) -> str:
    choices = response.get("choices", [])
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message", {})
        if isinstance(message, dict) and message.get("content"):
            text = str(message["content"]).strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            return text
    raise ValueError("GitHub Models returned no output")


_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "selected_index": {"type": "integer"},
        "canonical_name": {"type": "string"},
        "confidence": {"type": "number"},
        "should_match": {"type": "boolean"},
        "explanation": {"type": "string"},
        "family_name": {"type": ["string", "null"]},
        "category": {"type": ["string", "null"]},
    },
    "required": [
        "selected_index",
        "canonical_name",
        "confidence",
        "should_match",
        "explanation",
    ],
}
