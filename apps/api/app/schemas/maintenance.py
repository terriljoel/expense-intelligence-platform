from pydantic import BaseModel, Field


class MaintenanceCounts(BaseModel):
    receipts: int
    receipt_items: int
    receipt_payments: int
    receipt_captures: int
    income_entries: int
    audit_events: int


class MaintenancePreview(BaseModel):
    household_name: str
    confirmation_phrase: str
    counts: MaintenanceCounts


class HouseholdResetRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=300)


class HouseholdResetResponse(BaseModel):
    message: str
    deleted: MaintenanceCounts
    image_objects_deleted: int
    image_objects_not_found: int
    image_delete_failures: int

