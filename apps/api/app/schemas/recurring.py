from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


Category = Literal[
    "groceries",
    "rent",
    "health_insurance",
    "transport",
    "university_fees",
    "utilities",
    "subscriptions",
    "dining",
    "shopping",
    "travel",
    "other",
]


class RecurringExpenseWrite(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    merchant_id: UUID | None = None
    payment_method_id: UUID | None = None
    category: Category = "other"
    amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    day_of_month: int = Field(ge=1, le=31)
    next_occurrence_date: date
    notes: str | None = Field(default=None, max_length=1000)
    is_active: bool = True


class RecurringExpenseResponse(RecurringExpenseWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime
