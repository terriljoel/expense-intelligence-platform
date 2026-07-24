from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ReceiptCaptureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    receipt_id: UUID | None
    original_filename: str | None
    media_type: str
    byte_size: int
    image_sha256: str
    ocr_status: str
    ocr_provider: str | None
    ocr_raw_text: str | None
    ocr_error: str | None
    ocr_result: dict[str, object] | None
    suggested_items: list[dict[str, object]] | None
    suggested_merchant_name: str | None
    suggested_merchant_address: str | None
    suggested_merchant_phone: str | None
    suggested_purchase_date: date | None
    suggested_transaction_time: time | None
    suggested_currency: str | None
    suggested_total: Decimal | None
    suggested_subtotal: Decimal | None
    suggested_tax: Decimal | None
    suggested_tip: Decimal | None
    suggested_payment_type: str | None
    suggested_payment_provider: str | None
    suggested_payment_last_four: str | None
    suggested_payment_method_id: UUID | None
    suggested_payment_reason: str | None
    suggested_receipt_number: str | None
    possible_duplicate_receipt_id: UUID | None
    duplicate_match_level: str | None
    duplicate_reason: str | None
    ocr_completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    image_url: str = ""
