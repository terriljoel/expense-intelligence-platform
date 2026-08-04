from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InvitationCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Literal["member"] = "member"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        cleaned = value.strip().casefold()
        if "@" not in cleaned:
            raise ValueError("Enter a valid email address")
        return cleaned


class InvitationTokenRequest(BaseModel):
    token: str = Field(min_length=32, max_length=200)


class InvitationAccept(InvitationTokenRequest):
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Display name cannot be blank")
        return cleaned


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: str
    expires_at: datetime
    created_at: datetime


class InvitationCreatedResponse(InvitationResponse):
    invitation_token: str


class InvitationPreviewResponse(BaseModel):
    email: str
    household_name: str
    role: str
    expires_at: datetime
    existing_account: bool


class InvitationAcceptedResponse(BaseModel):
    email: str
    household_id: UUID
    message: str


class HouseholdMemberResponse(BaseModel):
    user_id: UUID
    email: str | None
    display_name: str
    role: str
    joined_at: datetime
