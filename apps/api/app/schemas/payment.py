from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.base import UpdateRequest


PaymentMethodType = Literal[
    "cash",
    "debit_card",
    "credit_card",
    "bank_transfer",
    "direct_debit",
    "mobile_wallet",
    "voucher",
    "other",
]


class PaymentMethodCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    method_type: PaymentMethodType
    provider: str | None = Field(default=None, max_length=100)
    last_four: str | None = Field(default=None, pattern=r"^[0-9]{4}$")

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Payment method name cannot be blank")
        return cleaned

    @field_validator("provider")
    @classmethod
    def clean_provider(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None


class PaymentMethodUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    method_type: PaymentMethodType | None = None
    provider: str | None = Field(default=None, max_length=100)
    last_four: str | None = Field(default=None, pattern=r"^[0-9]{4}$")

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Payment method name cannot be blank")
        return cleaned

    @field_validator("provider")
    @classmethod
    def clean_provider(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None

    @model_validator(mode="after")
    def require_valid_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be supplied")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Payment method name cannot be null")
        if "method_type" in self.model_fields_set and self.method_type is None:
            raise ValueError("Payment method type cannot be null")
        return self


class PaymentMethodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    method_type: str
    provider: str | None
    last_four: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ReceiptPaymentCreate(BaseModel):
    payment_method_id: UUID
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)


class ReceiptPaymentUpdate(UpdateRequest):
    non_nullable_fields: ClassVar[tuple[str, ...]] = (
        "payment_method_id",
        "amount",
    )

    payment_method_id: UUID | None = None
    amount: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=14,
        decimal_places=2,
    )

class ReceiptPaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    receipt_id: UUID
    user_id: UUID
    payer_display_name: str | None = None
    payment_method_id: UUID | None
    payment_method_name: str | None = None
    payment_method_last_four: str | None = None
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
