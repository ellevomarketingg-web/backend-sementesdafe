from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from app.models.book import BookStatus
from app.utils.email import normalize_email
from app.schemas.order_bump import OrderBumpItemResponse


class BookBase(BaseModel):
    child_name: str = ""
    template_version: int = 1


class BookCreate(BookBase):
    buyer_id: str
    order_id: str
    template_id: Optional[str] = None


class BookGenerateRequest(BaseModel):
    order_id: Optional[str] = None
    buyer_id: Optional[str] = None
    email: Optional[EmailStr] = None
    child_name: Optional[str] = None
    gender: Optional[str] = None
    force_regenerate: bool = False


class BookResponse(BookBase):
    id: str
    buyer_id: str
    order_id: str
    template_id: Optional[str]
    status: BookStatus
    file_url: Optional[str]
    generation_started_at: Optional[datetime]
    generated_at: Optional[datetime]
    delivered_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BookAvailabilityRequest(BaseModel):
    email: EmailStr

    @field_validator("email", mode="after")
    @classmethod
    def normalize(cls, v: EmailStr) -> str:
        return normalize_email(str(v))


class BookAvailabilityResponse(BaseModel):
    available: bool
    credits: int = 0
    can_generate: bool = False
    requires_verification: bool = False
    verification_channel: Optional[str] = None
    book_id: Optional[str] = None
    status: Optional[BookStatus] = None
    delivery_available: bool = False
    reason: Optional[str] = None
    message: Optional[str] = None
    order_bumps: List[OrderBumpItemResponse] = []


class BookVerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str

    @field_validator("email", mode="after")
    @classmethod
    def normalize(cls, v: EmailStr) -> str:
        return normalize_email(str(v))


class BookVerifyCodeResponse(BaseModel):
    success: bool
    download_token: Optional[str] = None
    download_url: Optional[str] = None
    book_id: Optional[str] = None
    order_bumps: List[OrderBumpItemResponse] = []
    message: Optional[str] = None
