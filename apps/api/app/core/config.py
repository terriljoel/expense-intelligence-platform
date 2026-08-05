from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# PROJECT_ROOT = Path(__file__).resolve().parents[4]
try:
    PROJECT_ROOT = Path(__file__).resolve().parents[4]
except IndexError:
    # Inside the Docker container, the repository root maps to /app
    PROJECT_ROOT = Path("/app")


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    database_url: str = Field(repr=False)
    auth_session_hours: int = Field(default=12, ge=1, le=720)
    session_cookie_secure: bool = False
    invitation_hours: int = Field(default=168, ge=1, le=720)
    receipt_image_dir: Path = PROJECT_ROOT / "data" / "receipt-images"
    receipt_image_max_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1024,
        le=25 * 1024 * 1024,
    )
    receipt_storage_provider: str = "local"
    azure_storage_connection_string: str | None = Field(default=None, repr=False)
    azure_storage_account_url: str | None = None
    azure_storage_container: str = "receipt-images"
    ocr_provider: str = "tesseract"
    tesseract_command: str = "tesseract"
    tesseract_language: str = "deu+eng"
    tesseract_timeout_seconds: int = Field(default=45, ge=1, le=300)
    azure_document_intelligence_endpoint: str | None = Field(default=None, repr=False)
    azure_document_intelligence_key: str | None = Field(default=None, repr=False)
    azure_document_intelligence_locale: str = "de-DE"
    azure_document_intelligence_timeout_seconds: int = Field(default=60, ge=1, le=300)
    # F0 accepts at most 4 MiB. S0 users can raise this value through .env.
    azure_document_intelligence_max_bytes: int = Field(
        default=4 * 1024 * 1024,
        ge=256 * 1024,
        le=500 * 1024 * 1024,
    )
    product_enrichment_enabled: bool = True
    product_enrichment_providers: str = "local"
    product_auto_match_threshold: float = Field(default=0.92, ge=0, le=1)
    product_review_threshold: float = Field(default=0.60, ge=0, le=1)
    product_provider_timeout_seconds: int = Field(default=10, ge=1, le=60)
    product_max_provider_requests: int = Field(default=3, ge=1, le=20)
    product_cache_hours: int = Field(default=168, ge=1, le=8760)
    product_fuzzy_match_threshold: float = Field(default=0.60, ge=0, le=1)
    product_max_local_candidates: int = Field(default=5, ge=1, le=20)
    product_max_external_candidates: int = Field(default=5, ge=1, le=20)
    open_food_facts_base_url: str = "https://world.openfoodfacts.org"
    search_a_licious_base_url: str = "https://search.openfoodfacts.org"
    product_provider_user_agent: str = "expense-intelligence/0.1 (personal project)"
    product_agent_enabled: bool = False
    github_models_endpoint: str = "https://models.github.ai/inference"
    github_models_model: str = "openai/gpt-4.1-mini"
    github_models_token: str | None = Field(default=None, repr=False)
    product_agent_timeout_seconds: int = Field(default=30, ge=1, le=120)
    product_llm_extraction_enabled: bool = False
    product_web_search_enabled: bool = False
    tavily_api_key: str | None = Field(default=None, repr=False)
    tavily_search_endpoint: str = "https://api.tavily.com/search"
    tavily_max_results: int = Field(default=5, ge=1, le=10)

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
