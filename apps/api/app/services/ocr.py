"""Provider-neutral contracts used by receipt OCR integrations."""

from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from typing import Protocol


class OcrProcessingError(Exception):
    """Raised when the selected OCR integration cannot extract a receipt."""


@dataclass(frozen=True)
class ReceiptSuggestions:
    merchant_name: str | None
    purchase_date: date | None
    currency: str | None
    total: Decimal | None
    merchant_address: str | None = None
    merchant_phone: str | None = None
    transaction_time: time | None = None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    tip: Decimal | None = None
    payment_type: str | None = None
    payment_provider: str | None = None
    payment_last_four: str | None = None
    receipt_number: str | None = None


@dataclass(frozen=True)
class OcrLineItem:
    description: str
    quantity: Decimal | None
    unit_price: Decimal | None
    line_total: Decimal


@dataclass(frozen=True)
class OcrResult:
    provider: str
    raw_text: str
    suggestions: ReceiptSuggestions | None = None
    provider_payload: dict[str, object] | None = None
    line_items: tuple[OcrLineItem, ...] = ()


class OcrProvider(Protocol):
    def extract_text(self, image: bytes) -> OcrResult: ...
