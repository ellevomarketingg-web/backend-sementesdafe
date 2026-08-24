from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.models.message import MessageStatus


class MessageBase(BaseModel):
    buyer_id: str
    book_id: Optional[str] = None
    template_id: Optional[str] = None
    channel: str = "WHATSAPP"
    destination: str
    content: str


class MessageCreate(MessageBase):
    template_version: int = 1


class MessageResponse(MessageBase):
    id: str
    template_version: int
    status: MessageStatus
    external_message_id: Optional[str]
    attempts: int
    error_message: Optional[str]
    scheduled_at: Optional[datetime]
    sent_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageRetryResponse(BaseModel):
    message_id: str
    status: str
    detail: str
