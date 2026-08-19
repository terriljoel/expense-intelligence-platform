from typing import ClassVar, Self

from pydantic import BaseModel, model_validator


class UpdateRequest(BaseModel):
    """Require a non-empty PATCH body and protect explicitly required fields."""

    non_nullable_fields: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="after")
    def require_valid_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be supplied")
        for field_name in self.non_nullable_fields:
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self
