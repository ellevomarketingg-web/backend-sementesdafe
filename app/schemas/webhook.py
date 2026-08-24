from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, EmailStr, field_validator
from app.utils.email import normalize_email
from app.utils.phone import normalize_phone


class OrderWebhookBuyer(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None

    @field_validator("email", mode="after")
    @classmethod
    def normalize_buyer_email(cls, v: EmailStr) -> str:
        return normalize_email(str(v))

    @field_validator("phone", mode="after")
    @classmethod
    def normalize_buyer_phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_phone(v)


class OrderWebhookOrderData(BaseModel):
    external_order_id: str
    status: str = "PAID"
    amount: float = 0.0
    product_code: str = "DEUS_CONHECE_SEU_NOME"
    product_name: str = "Deus Conhece o Seu Nome"
    paid_at: Optional[datetime] = None


class OrderWebhookPayload(BaseModel):
    event_id: str
    event_type: str = "order.paid"
    order: OrderWebhookOrderData
    buyer: OrderWebhookBuyer
    metadata: Optional[Dict[str, Any]] = None


class EvolutionWebhookPayload(BaseModel):
    event: str
    instance: Optional[str] = None
    data: Dict[str, Any] = {}
    sender: Optional[str] = None


class WebhookProcessingResponse(BaseModel):
    received: bool = True
    status: str
    detail: Optional[str] = None
    event_id: Optional[str] = None
