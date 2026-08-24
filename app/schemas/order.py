from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict
from app.models.order import OrderStatus
from app.schemas.buyer import BuyerResponse


class OrderBase(BaseModel):
    external_order_id: str
    product_code: str = "DEUS_CONHECE_SEU_NOME"
    product_name: str = "Deus Conhece o Seu Nome"
    amount: float
    metadata_info: Optional[Dict[str, Any]] = None


class OrderCreate(OrderBase):
    buyer_id: str
    status: OrderStatus = OrderStatus.PENDING


class OrderUpdateStatus(BaseModel):
    status: OrderStatus
    paid_at: Optional[datetime] = None


class OrderResponse(OrderBase):
    id: str
    buyer_id: str
    status: OrderStatus
    paid_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
