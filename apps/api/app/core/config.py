from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[4]


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

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
