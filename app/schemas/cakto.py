from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List, Union
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from app.utils.email import normalize_email
from app.utils.phone import normalize_phone


class CaktoCustomer(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    docType: Optional[str] = None
    docNumber: Optional[str] = None
    birthDate: Optional[Union[date, datetime, str]] = None

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
    image: Optional[str] = None
    price: Optional[Decimal] = None

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
    qrCode: Optional[str] = None
    qrcode: Optional[str] = None
    qrcode_text: Optional[str] = None
    expirationDate: Optional[Union[datetime, str]] = None

    model_config = ConfigDict(extra="ignore")


class CaktoCard(BaseModel):
    brand: Optional[str] = None
    holderName: Optional[str] = None
    lastDigits: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class CaktoBoleto(BaseModel):
    barcode: Optional[str] = None
    boletoUrl: Optional[str] = None
    expirationDate: Optional[Union[date, datetime, str]] = None

    model_config = ConfigDict(extra="ignore")


class CaktoPicPay(BaseModel):
    qrCode: Optional[str] = None
    paymentURL: Optional[str] = None
    expirationDate: Optional[Union[datetime, str]] = None

    model_config = ConfigDict(extra="ignore")


class CaktoCommission(BaseModel):
    id: Optional[str] = None
    type: Optional[str] = None
    user: Optional[str] = None
    percentage: Optional[Decimal] = None
    totalAmount: Optional[Decimal] = None
    amount: Optional[Decimal] = None
    recipientId: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class CaktoAddress(BaseModel):
    street: Optional[str] = None
    number: Optional[str] = None
    complement: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipCode: Optional[str] = None
    country: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class CaktoShipping(BaseModel):
    price: Optional[Decimal] = None
    trackingCode: Optional[str] = None
    status: Optional[str] = None
    carrier: Optional[str] = None

    model_config = ConfigDict(extra="ignore")


class CaktoSubscription(BaseModel):
    id: Optional[str] = None
    offer: Optional[Union[str, CaktoOffer]] = None
    amount: Optional[Union[Decimal, str]] = None
    orders: Optional[List[str]] = None
    status: Optional[str] = None
    product: Optional[Union[str, CaktoProduct]] = None
    customer: Optional[CaktoCustomer] = None
    createdAt: Optional[Union[datetime, str]] = None
    updatedAt: Optional[Union[datetime, str]] = None
    canceledAt: Optional[Union[datetime, str]] = None
    next_payment_date: Optional[Union[datetime, str]] = None
    retention: Optional[str] = None
    trial_days: Optional[int] = None
    max_retries: Optional[int] = None
    parent_order: Optional[str] = None
    paymentMethod: Optional[str] = None
    current_period: Optional[int] = None
    retry_interval: Optional[int] = None
    recurrence_period: Optional[int] = None
    quantity_recurrences: Optional[int] = None
    paid_payments_quantity: Optional[int] = None

    model_config = ConfigDict(extra="ignore")


class CaktoOrderData(BaseModel):
    id: str
    refId: Optional[str] = None
    fbc: Optional[str] = None
    fbp: Optional[str] = None
    sck: Optional[str] = None
    customer: CaktoCustomer
    product: Optional[CaktoProduct] = None
    offer: Optional[CaktoOffer] = None
    offer_type: Optional[str] = None
    affiliate: Optional[Union[str, Dict[str, Any]]] = None

    checkout: Optional[Union[int, str]] = None
    checkoutUrl: Optional[str] = None

    status: str = "paid"
    baseAmount: Optional[Decimal] = None
    discount: Optional[Decimal] = Decimal("0.00")
    amount: Decimal = Decimal("0.00")

    fees: Optional[Union[Decimal, Dict[str, Any]]] = None

    pix: Optional[CaktoPix] = None
    card: Optional[CaktoCard] = None
    boleto: Optional[CaktoBoleto] = None
    picpay: Optional[CaktoPicPay] = None
    address: Optional[Union[CaktoAddress, Dict[str, Any]]] = None
    shipping: Optional[Union[CaktoShipping, Dict[str, Any]]] = None

    paymentMethod: Optional[str] = None
    paymentMethodName: Optional[str] = None
    installments: Optional[int] = 1
    couponCode: Optional[str] = None

    reason: Optional[str] = None
    refund_reason: Optional[str] = None

    commissions: Optional[List[CaktoCommission]] = None
    subscription: Optional[CaktoSubscription] = None
    subscription_period: Optional[int] = None
    parent_order: Optional[str] = None

    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_term: Optional[str] = None
    utm_content: Optional[str] = None

    due_date: Optional[Union[datetime, str]] = None
    paidAt: Optional[Union[datetime, str]] = None
    createdAt: Optional[Union[datetime, str]] = None
    canceledAt: Optional[Union[datetime, str]] = None
    refundedAt: Optional[Union[datetime, str]] = None
    chargedbackAt: Optional[Union[datetime, str]] = None

    # Order bumps e itens adicionais
    order_bumps: Optional[List[Dict[str, Any]]] = None
    orderBumps: Optional[List[Dict[str, Any]]] = None
    items: Optional[List[Dict[str, Any]]] = None

    model_config = ConfigDict(extra="ignore")


class CaktoWebhookPayload(BaseModel):
    secret: str = Field(..., repr=False)
    event: str
    data: CaktoOrderData

    model_config = ConfigDict(extra="ignore")


class CaktoWebhookResponse(BaseModel):
    received: bool = True
    status: str
    detail: Optional[str] = None
    event_id: Optional[str] = None
