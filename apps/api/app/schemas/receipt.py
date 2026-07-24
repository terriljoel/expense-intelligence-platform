from datetime import date, datetime, time
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
    capture_id: UUID | None = None
    merchant_id: UUID | None = None
    payment_method_id: UUID | None = None
    category: Literal[
        "groceries", "rent", "health_insurance", "transport",
        "university_fees", "utilities", "subscriptions", "dining",
        "shopping", "travel", "other",
    ] = "other"
    purchase_date: date
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    stated_total: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    notes: str | None = Field(default=None, max_length=1000)
    receipt_number: str | None = Field(default=None, max_length=100)

    @field_validator("notes", "receipt_number")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ReceiptUpdate(BaseModel):
    merchant_id: UUID | None = None
    category: Literal[
        "groceries", "rent", "health_insurance", "transport",
        "university_fees", "utilities", "subscriptions", "dining",
        "shopping", "travel", "other",
    ] | None = None
    purchase_date: date | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    stated_total: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=14,
        decimal_places=2,
    )
    notes: str | None = Field(default=None, max_length=1000)
    receipt_number: str | None = Field(default=None, max_length=100)

    @field_validator("notes", "receipt_number")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def require_valid_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be supplied")
        for required_field in (
            "category",
            "purchase_date",
            "currency",
            "stated_total",
        ):
            if (
                required_field in self.model_fields_set
                and getattr(self, required_field) is None
            ):
                raise ValueError(f"{required_field} cannot be null")
        return self


class ReceiptVoidRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        return cleaned or None


class ReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    merchant_id: UUID | None
    created_by_user_id: UUID
    created_by_display_name: str | None = None
    purchase_date: date
    purchase_time: time | None
    merchant_address: str | None
    merchant_phone: str | None
    currency: str
    stated_total: Decimal
    subtotal: Decimal | None
    tax_amount: Decimal | None
    tip_amount: Decimal | None
    status: str
    source: str
    category: str
    notes: str | None
    receipt_number: str | None
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
            raise ValueError(f"{self.line_type} line totals must be zero or positive")
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


class ReceiptItemUpdate(BaseModel):
    position: int | None = Field(default=None, gt=0)
    line_type: ReceiptLineType | None = None
    raw_description: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, min_length=1, max_length=500)
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
    line_total: Decimal | None = Field(
        default=None,
        max_digits=14,
        decimal_places=2,
    )

    @field_validator("description")
    @classmethod
    def clean_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Item description cannot be blank")
        return cleaned

    @model_validator(mode="after")
    def require_valid_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be supplied")
        for required_field in (
            "position",
            "line_type",
            "description",
            "line_total",
        ):
            if (
                required_field in self.model_fields_set
                and getattr(self, required_field) is None
            ):
                raise ValueError(f"{required_field} cannot be null")
        if self.line_type is not None and self.line_total is not None:
            if self.line_type == "discount" and self.line_total > 0:
                raise ValueError("Discount line totals must be non-positive")
            if (
                self.line_type in {"product", "deposit", "fee", "tax"}
                and self.line_total < 0
            ):
                raise ValueError(f"{self.line_type} line totals must be non-negative")
        return self


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sequence_number: int
    actor_user_id: UUID
    receipt_id: UUID
    event_type: str
    event_data: dict[str, Any]
    created_at: datetime
