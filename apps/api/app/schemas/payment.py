from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PaymentMethodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    method_type: str
    provider: str | None
    last_four: str | None
    is_active: bool


class ReceiptPaymentCreate(BaseModel):
    payment_method_id: UUID
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)


class ReceiptPaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    receipt_id: UUID
    user_id: UUID
    payment_method_id: UUID | None
    amount: Decimal
    created_at: datetime


class ReceiptReconciliationResponse(BaseModel):
    receipt_id: UUID
    stated_total: Decimal
    item_total: Decimal
    payment_total: Decimal
    item_difference: Decimal
    payment_difference: Decimal
    item_count: int
    payment_count: int
    is_reconciled: bool
