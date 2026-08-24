from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.models.delivery import DeliveryStatus


class DeliveryBase(BaseModel):
    book_id: str
    buyer_id: str
    channel: str = "WHATSAPP"
    destination: str
    delivery_url: Optional[str] = None


class DeliveryCreate(DeliveryBase):
    pass


class DeliveryResponse(DeliveryBase):
    id: str
    status: DeliveryStatus
    attempts: int
    last_error: Optional[str]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
