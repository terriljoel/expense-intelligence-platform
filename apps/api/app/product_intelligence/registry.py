from app.core.config import Settings
from app.product_intelligence.contracts import ProductProvider
from app.product_intelligence.extractors import (
    GitHubModelsProductExtractor,
    ProductTextExtractor,
)
from app.product_intelligence.providers.open_food_facts import OpenFoodFactsProvider
from app.product_intelligence.providers.search_a_licious import SearchALiciousProvider
from app.product_intelligence.providers.tavily import TavilyResearchProvider
from app.product_intelligence.rankers import CandidateRanker, GitHubModelsRanker


def configured_providers(settings: Settings) -> list[ProductProvider]:
    names = {
        name.strip().lower()
        for name in settings.product_enrichment_providers.split(",")
    }
    providers: list[ProductProvider] = []
    if "open_food_facts" in names:
        providers.append(
            OpenFoodFactsProvider(
                base_url=settings.open_food_facts_base_url,
                timeout=settings.product_provider_timeout_seconds,
                user_agent=settings.product_provider_user_agent,
            )
        )
    if "search_a_licious" in names:
        providers.append(
            SearchALiciousProvider(
                base_url=settings.search_a_licious_base_url,
                timeout=settings.product_provider_timeout_seconds,
                user_agent=settings.product_provider_user_agent,
                result_limit=settings.product_max_external_candidates,
            )
        )
    if settings.product_web_search_enabled and settings.tavily_api_key:
        providers.append(
            TavilyResearchProvider(
                endpoint=settings.tavily_search_endpoint,
                api_key=settings.tavily_api_key,
                timeout=settings.product_provider_timeout_seconds,
                result_limit=settings.tavily_max_results,
            )
        )
    return providers[: settings.product_max_provider_requests]


def configured_ranker(settings: Settings) -> CandidateRanker | None:
    if not settings.product_agent_enabled:
        return None
    if not all(
        (
            settings.github_models_endpoint,
            settings.github_models_model,
            settings.github_models_token,
        )
    ):
        return None
    return GitHubModelsRanker(
        endpoint=settings.github_models_endpoint,
        model=settings.github_models_model,
        token=settings.github_models_token,
        timeout=settings.product_agent_timeout_seconds,
    )


def configured_extractor(settings: Settings) -> ProductTextExtractor | None:
    if not settings.product_llm_extraction_enabled or not settings.github_models_token:
        return None
    return GitHubModelsProductExtractor(
        endpoint=settings.github_models_endpoint,
        model=settings.github_models_model,
        token=settings.github_models_token,
        timeout=settings.product_agent_timeout_seconds,
    )
