from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class ReceiptCreate(BaseModel):
    merchant_id: UUID | None = None
    purchase_date: date
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    stated_total: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    merchant_id: UUID | None
    created_by_user_id: UUID
    purchase_date: date
    currency: str
    stated_total: Decimal
    status: str
    source: str
    notes: str | None
    approved_at: datetime | None
    voided_at: datetime | None
    created_at: datetime
    updated_at: datetime


ReceiptLineType = Literal[
    "product",
    "deposit",
    "discount",
    "fee",
    "tax",
    "adjustment",
]


class ReceiptItemCreate(BaseModel):
    position: int = Field(gt=0)
    line_type: ReceiptLineType = "product"
    raw_description: str | None = Field(default=None, max_length=500)
    description: str = Field(min_length=1, max_length=500)
    raw_quantity_text: str | None = Field(default=None, max_length=100)
    quantity: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=3,
    )
    unit_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=14,
        decimal_places=4,
    )
    line_total: Decimal = Field(max_digits=14, decimal_places=2)

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Item description cannot be blank")
        return cleaned

    @model_validator(mode="after")
    def validate_amount_sign(self) -> Self:
        if self.line_type == "discount" and self.line_total > 0:
            raise ValueError("Discount line totals must be zero or negative")
        if (
            self.line_type in {"product", "deposit", "fee", "tax"}
            and self.line_total < 0
        ):
            raise ValueError(
                f"{self.line_type} line totals must be zero or positive"
            )
        return self


class ReceiptItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    receipt_id: UUID
    position: int
    line_type: str
    raw_description: str | None
    description: str
    raw_quantity_text: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    line_total: Decimal
    created_at: datetime
    updated_at: datetime


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sequence_number: int
    actor_user_id: UUID
    receipt_id: UUID
    event_type: str
    event_data: dict[str, Any]
    created_at: datetime
