from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.base import UpdateRequest


class HouseholdResponse(BaseModel):
    household_id: UUID
    name: str
    default_currency: str
    role: str
    created_at: datetime
    updated_at: datetime


class HouseholdUpdate(UpdateRequest):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    default_currency: str | None = Field(
        default=None, min_length=3, max_length=3
    )

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Household name cannot be blank")
        return cleaned

    @field_validator("default_currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().upper()
        if len(cleaned) != 3 or not cleaned.isalpha():
            raise ValueError("Currency must be a three-letter code")
        return cleaned

class MemberRoleUpdate(BaseModel):
    role: Literal["owner", "member"]


class MemberPasswordReset(BaseModel):
    password: str = Field(min_length=12, max_length=128)
