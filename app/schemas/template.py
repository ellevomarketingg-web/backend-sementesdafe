from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict
from app.models.book_template import TemplateStatus


# Book Template Schemas
class BookTemplateBase(BaseModel):
    name: str = "deus-conhece-seu-nome"
    template_data: Dict[str, Any]


class BookTemplateCreate(BookTemplateBase):
    version: int = 1


class BookTemplateResponse(BookTemplateBase):
    id: str
    version: int
    status: TemplateStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Communication Template Schemas
class CommunicationTemplateBase(BaseModel):
    code: str
    name: str
    channel: str = "WHATSAPP"
    event: str
    content: str
    variables: Dict[str, Any] = {}


class CommunicationTemplateCreate(CommunicationTemplateBase):
    version: int = 1


class CommunicationTemplateResponse(CommunicationTemplateBase):
    id: str
    version: int
    status: TemplateStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Validation & Preview Schemas
class TemplateValidationError(BaseModel):
    variable: str
    reason: str


class TemplateValidationResult(BaseModel):
    valid: bool
    variables_found: List[str]
    errors: List[TemplateValidationError] = []


class CommunicationTemplatePreviewRequest(BaseModel):
    variables: Dict[str, Any]


class CommunicationTemplatePreviewResponse(BaseModel):
    rendered_content: str
    variables_used: Dict[str, Any]
