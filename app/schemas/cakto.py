from datetime import datetime
from typing import Optional, Dict, Any, List, Union
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from app.utils.email import normalize_email
from app.utils.phone import normalize_phone


class CaktoCustomer(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    birthDate: Optional[str] = None
    docNumber: Optional[str] = None

    @field_validator("email", mode="after")
    @classmethod
    def normalize_customer_email(cls, v: EmailStr) -> str:
        return normalize_email(str(v))

    @field_validator("phone", mode="after")
    @classmethod
    def normalize_customer_phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_phone(v)

    model_config = ConfigDict(extra="ignore")


class CaktoOffer(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    price: Optional[float] = None

    model_config = ConfigDict(extra="ignore")


class CaktoProduct(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    short_id: Optional[str] = None
    supportEmail: Optional[str] = None
    type: Optional[str] = None
    invoiceDescription: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class CaktoPix(BaseModel):
    qrcode: Optional[str] = None
    qrcode_text: Optional[str] = None
    expirationDate: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class CaktoCommission(BaseModel):
    id: Optional[str] = None
    amount: Optional[float] = None
    type: Optional[str] = None
    recipientId: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class CaktoOrderData(BaseModel):
    id: str
    refId: Optional[str] = None
    customer: CaktoCustomer
    product: Optional[CaktoProduct] = None
    offer: Optional[CaktoOffer] = None
    offer_type: Optional[str] = None
    affiliate: Optional[Any] = None

    status: str = "paid"
    baseAmount: Optional[float] = None
    discount: Optional[float] = 0.0
    amount: float = 0.0

    paymentMethod: Optional[str] = None
    installments: Optional[int] = 1
    couponCode: Optional[str] = None
    checkoutUrl: Optional[str] = None

    reason: Optional[str] = None
    refund_reason: Optional[str] = None

    commissions: Optional[List[Dict[str, Any]]] = None
    fees: Optional[Dict[str, Any]] = None

    pix: Optional[CaktoPix] = None

    # Order bumps e itens adicionais
    order_bumps: Optional[List[Dict[str, Any]]] = None
    orderBumps: Optional[List[Dict[str, Any]]] = None
    items: Optional[List[Dict[str, Any]]] = None

    paidAt: Optional[Union[datetime, str]] = None
    createdAt: Optional[Union[datetime, str]] = None

    model_config = ConfigDict(extra="ignore")


class CaktoWebhookPayload(BaseModel):
    secret: str
    event: str
    data: CaktoOrderData

    model_config = ConfigDict(extra="ignore")


class CaktoWebhookResponse(BaseModel):
    received: bool = True
    status: str
    detail: Optional[str] = None
    event_id: Optional[str] = None
