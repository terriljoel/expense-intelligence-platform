from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


IncomeType = Literal[
    "salary",
    "freelance",
    "interest",
    "gift",
    "refund",
    "other",
]


class IncomeCreate(BaseModel):
    source: str = Field(min_length=1, max_length=200)
    income_type: IncomeType = "other"
    category: Literal[
        "salary_payslip", "freelance", "interest", "gift", "refund",
        "benefits", "other",
    ] = "other"
    received_date: date
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    destination_payment_method_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("source")
    @classmethod
    def clean_source(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Income source cannot be blank")
        return cleaned

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class IncomeUpdate(BaseModel):
    source: str | None = Field(default=None, min_length=1, max_length=200)
    income_type: IncomeType | None = None
    category: Literal[
        "salary_payslip", "freelance", "interest", "gift", "refund",
        "benefits", "other",
    ] | None = None
    received_date: date | None = None
    amount: Decimal | None = Field(
        default=None, gt=0, max_digits=14, decimal_places=2
    )
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    destination_payment_method_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("source")
    @classmethod
    def clean_source(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Income source cannot be blank")
        return cleaned

    @field_validator("notes")
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
        for field_name in (
            "source",
            "income_type",
            "category",
            "received_date",
            "amount",
            "currency",
        ):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class IncomeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    received_by_user_id: UUID
    received_by_display_name: str | None = None
    destination_payment_method_id: UUID | None
    source: str
    income_type: str
    category: str
    received_date: date
    amount: Decimal
    currency: str
    notes: str | None
    created_at: datetime
    updated_at: datetime
