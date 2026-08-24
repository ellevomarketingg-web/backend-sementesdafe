from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from app.models.order_bump import OrderBumpStatus
from app.utils.email import normalize_email


class OrderBumpCatalogItem(BaseModel):
    id: str
    name: str
    code: str
    filename: str
    content_type: str
    description: str


class OrderBumpItemResponse(BaseModel):
    id: str
    product_id: str
    product_name: str
    product_code: str
    status: OrderBumpStatus
    download_url: Optional[str] = None
    download_token: Optional[str] = None
    unlocked_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrderBumpAvailabilityRequest(BaseModel):
    email: EmailStr
    product_id: Optional[str] = None

    @field_validator("email", mode="after")
    @classmethod
    def normalize(cls, v: EmailStr) -> str:
        return normalize_email(str(v))


class OrderBumpAvailabilityResponse(BaseModel):
    has_access: bool
    email: str
    order_bumps: List[OrderBumpItemResponse] = []
    requires_verification: bool = False
    verification_channel: Optional[str] = None
    message: Optional[str] = None


class OrderBumpVerifyRequest(BaseModel):
    email: EmailStr
    code: str
    product_id: Optional[str] = None

    @field_validator("email", mode="after")
    @classmethod
    def normalize(cls, v: EmailStr) -> str:
        return normalize_email(str(v))


class OrderBumpVerifyResponse(BaseModel):
    success: bool
    download_token: Optional[str] = None
    order_bumps: List[OrderBumpItemResponse] = []
    message: Optional[str] = None
