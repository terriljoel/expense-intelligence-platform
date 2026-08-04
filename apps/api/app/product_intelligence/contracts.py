from dataclasses import asdict, dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ProductQuery:
    description: str
    barcode: str | None = None
    merchant_name: str | None = None
    merchant_address: str | None = None
    country: str = "de"
    language: str = "de"


@dataclass(frozen=True)
class ProductCandidate:
    canonical_name: str
    provider: str
    confidence: float
    product_id: str | None = None
    barcode: str | None = None
    description: str | None = None
    brand: str | None = None
    manufacturer: str | None = None
    family_name: str | None = None
    product_type: str = "other"
    category: str | None = None
    source_url: str | None = None
    external_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    nutrition: dict[str, object] = field(default_factory=dict)
    evidence: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class ProductProvider(Protocol):
    name: str

    def search(self, query: ProductQuery) -> list[ProductCandidate]: ...
