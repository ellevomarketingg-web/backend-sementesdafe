from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from app.utils.email import normalize_email
from app.utils.phone import normalize_phone


class BuyerBase(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None

    @field_validator("email", mode="after")
    @classmethod
    def validate_email_str(cls, v: EmailStr) -> str:
        return normalize_email(str(v))

    @field_validator("phone", mode="after")
    @classmethod
    def validate_phone_str(cls, v: Optional[str]) -> Optional[str]:
        return normalize_phone(v)


class BuyerCreate(BuyerBase):
    pass


class BuyerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None


class BuyerResponse(BuyerBase):
    id: str
    email_normalized: str
    generation_credits: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
