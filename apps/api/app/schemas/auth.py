from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        cleaned = value.strip().casefold()
        if "@" not in cleaned:
            raise ValueError("Enter a valid email address")
        return cleaned


class AuthenticatedUserResponse(BaseModel):
    user_id: UUID
    household_id: UUID
    email: str
    display_name: str
    role: str
    is_global_admin: bool
    session_expires_at: datetime


class HouseholdCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    default_currency: str = Field(default="EUR", min_length=3, max_length=3)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Household name cannot be blank")
        return cleaned

    @field_validator("default_currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if len(cleaned) != 3 or not cleaned.isalpha():
            raise ValueError("Currency must be a three-letter code")
        return cleaned


class HouseholdAccessResponse(BaseModel):
    household_id: UUID
    name: str
    default_currency: str
    role: str
    is_active: bool
