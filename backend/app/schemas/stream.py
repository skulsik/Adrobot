from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class OfferAdd(BaseModel):
    offer_id: int = Field(gt=0)


class OfferUpdate(BaseModel):
    share: Decimal | None = Field(default=None, ge=0, le=100, multiple_of=1)
    is_fixed: bool | None = None

    @model_validator(mode="after")
    def validate_fields(self):
        if self.share is None and self.is_fixed is None:
            raise ValueError("At least one field must be provided")
        return self
