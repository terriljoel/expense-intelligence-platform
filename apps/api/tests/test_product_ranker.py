import json

import pytest

from app.product_intelligence.contracts import ProductCandidate, ProductQuery
from app.product_intelligence.rankers import GitHubModelsRanker


def test_github_ranker_requests_json_and_validates_decision() -> None:
    captured: dict[str, object] = {}

    def transport(url, payload, timeout, headers):
        captured.update(url=url, payload=payload, timeout=timeout, headers=headers)
        decision = {
            "selected_index": 1,
            "canonical_name": "Ja! Haltbare Vollmilch 3,5%, 1 L",
            "confidence": 0.84,
            "should_match": True,
            "explanation": "The brand, milk type, fat level and package size agree.",
        }
        return {"choices": [{"message": {"content": json.dumps(decision)}}]}

    ranker = GitHubModelsRanker(
        endpoint="https://models.github.ai/inference",
        model="openai/gpt-4.1-mini",
        token="secret",
        timeout=20,
        transport=transport,
    )
    candidates = [
        ProductCandidate("Milk", "search", 0.6),
        ProductCandidate("Haltbare Vollmilch", "search", 0.75),
    ]

    decision = ranker.rank(ProductQuery("JA H-MILCH 3.5 1L"), candidates)

    assert decision.selected_index == 1
    assert captured["url"] == "https://models.github.ai/inference/chat/completions"
    assert captured["payload"]["model"] == "openai/gpt-4.1-mini"
    assert captured["headers"]["Authorization"] == "Bearer secret"


def test_github_ranker_rejects_invalid_candidate_index() -> None:
    response = {"choices": [{"message": {"content": json.dumps({
        "selected_index": 9, "canonical_name": "Milk", "confidence": 0.8,
        "should_match": True, "explanation": "Invalid index",
    })}}]}
    ranker = GitHubModelsRanker(
        endpoint="https://models.github.ai/inference",
        model="model",
        token="secret",
        timeout=20,
        transport=lambda *_: response,
    )

    with pytest.raises(ValueError):
        ranker.rank(ProductQuery("Milk"), [ProductCandidate("Milk", "search", 0.7)])
