from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.text_normalization import normalize_barcode


ProductMatchStatus = Literal["unmatched", "suggested", "confirmed", "rejected"]


class ProductCreate(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=2000)
    brand: str | None = Field(default=None, max_length=300)
    manufacturer: str | None = Field(default=None, max_length=300)
    family_name: str | None = Field(default=None, max_length=200)
    product_type: str = Field(default="other", min_length=1, max_length=100)
    category: str | None = Field(default=None, max_length=100)
    barcode: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    nutrition: dict[str, Any] = Field(default_factory=dict)

    @field_validator("canonical_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("barcode")
    @classmethod
    def clean_barcode(cls, value: str | None) -> str | None:
        if value is None:
            return None
        barcode = normalize_barcode(value)
        if barcode is None:
            raise ValueError("Barcode must contain 8 to 14 digits")
        return barcode


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    canonical_name: str
    description: str | None
    brand: str | None
    manufacturer: str | None
    family_name: str | None
    product_type: str
    category: str | None
    barcode: str | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    nutrition: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ProductMatchResponse(BaseModel):
    product: ProductResponse | None
    status: ProductMatchStatus
    method: str | None = None
    confidence: Decimal | None = None


class ProductMatchConfirm(BaseModel):
    product_id: UUID


class ProductEnrichmentRequest(BaseModel):
    barcode: str | None = None
    description: str | None = Field(default=None, min_length=1, max_length=500)
    refresh_existing: bool = False

    _clean_barcode = field_validator("barcode")(ProductCreate.clean_barcode.__func__)


class ProductCandidateResponse(BaseModel):
    canonical_name: str
    provider: str
    confidence: float
    product_id: UUID | None = None
    barcode: str | None = None
    description: str | None = None
    brand: str | None = None
    manufacturer: str | None = None
    family_name: str | None = None
    product_type: str
    category: str | None = None
    source_url: str | None = None
    external_id: str | None = None
    metadata: dict[str, Any]
    nutrition: dict[str, Any]
    evidence: dict[str, Any]


class BarcodeDetectionResponse(BaseModel):
    detected_barcode: str | None
    barcode_format: str | None
    error_message: str | None


class ProductEnrichmentResponse(BaseModel):
    run_id: UUID | None
    status: str
    match: ProductMatchResponse
    candidates: list[ProductCandidateResponse]
    errors: list[str]
    agent_decision: dict[str, Any] | None = None
    providers_queried: list[str] = Field(default_factory=list)
    ai_used: bool = False
    retailer_web_search_performed: bool = False


class ProductInsightCounts(BaseModel):
    total: int
    unmatched: int
    suggested: int
    confirmed: int
    ignored: int
    products: int
    food_products: int
    food_products_with_nutrition: int


class ProductInsightItem(BaseModel):
    id: UUID
    receipt_id: UUID
    description: str
    quantity: Decimal | None
    line_total: Decimal
    match_status: ProductMatchStatus
    match_method: str | None
    match_score: Decimal | None
    purchase_date: str
    merchant_id: UUID | None
    merchant_name: str | None
    product: ProductResponse | None


class ProductInsightsResponse(BaseModel):
    counts: ProductInsightCounts
    items: list[ProductInsightItem]


class ProductInsightStatusUpdate(BaseModel):
    status: Literal["unmatched", "rejected"]


class ProductInsightBulkMatch(BaseModel):
    item_ids: list[UUID] = Field(min_length=1, max_length=100)


class ProductInsightBulkResult(BaseModel):
    processed: int
    matched: int


class KnowledgeFactResponse(BaseModel):
    fact_type: str
    value: dict[str, Any]
    extraction_method: str
    confidence: Decimal
    confirmation_status: str
    created_at: datetime


class KnowledgeDocumentResponse(BaseModel):
    id: UUID
    provider: str
    source_url: str | None
    title: str
    content_text: str | None
    content_type: str
    content_sha256: str
    retrieved_at: datetime
    metadata: dict[str, Any]
    facts: list[KnowledgeFactResponse]


class ProductKnowledgeResponse(BaseModel):
    product: ProductResponse
    documents: list[KnowledgeDocumentResponse]
