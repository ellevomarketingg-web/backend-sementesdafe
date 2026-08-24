"""Schemas Pydantic para validação e serialização de dados."""

from app.schemas.buyer import BuyerBase, BuyerCreate, BuyerUpdate, BuyerResponse
from app.schemas.order import OrderBase, OrderCreate, OrderUpdateStatus, OrderResponse
from app.schemas.book import (
    BookBase,
    BookCreate,
    BookResponse,
    BookGenerateRequest,
    BookAvailabilityRequest,
    BookAvailabilityResponse,
    BookVerifyCodeRequest,
    BookVerifyCodeResponse,
)
from app.schemas.template import (
    BookTemplateCreate,
    BookTemplateResponse,
    CommunicationTemplateCreate,
    CommunicationTemplateResponse,
    TemplateValidationResult,
    TemplateValidationError,
    CommunicationTemplatePreviewRequest,
    CommunicationTemplatePreviewResponse,
)
from app.schemas.message import MessageBase, MessageCreate, MessageResponse, MessageRetryResponse
from app.schemas.delivery import DeliveryBase, DeliveryCreate, DeliveryResponse
from app.schemas.webhook import (
    OrderWebhookPayload,
    EvolutionWebhookPayload,
    WebhookProcessingResponse,
)
from app.schemas.cakto import (
    CaktoWebhookPayload,
    CaktoOrderData,
    CaktoCustomer,
    CaktoProduct,
    CaktoOffer,
    CaktoPix,
    CaktoWebhookResponse,
)

__all__ = [
    "BuyerBase",
    "BuyerCreate",
    "BuyerUpdate",
    "BuyerResponse",
    "OrderBase",
    "OrderCreate",
    "OrderUpdateStatus",
    "OrderResponse",
    "BookBase",
    "BookCreate",
    "BookResponse",
    "BookGenerateRequest",
    "BookAvailabilityRequest",
    "BookAvailabilityResponse",
    "BookVerifyCodeRequest",
    "BookVerifyCodeResponse",
    "BookTemplateCreate",
    "BookTemplateResponse",
    "CommunicationTemplateCreate",
    "CommunicationTemplateResponse",
    "TemplateValidationResult",
    "TemplateValidationError",
    "CommunicationTemplatePreviewRequest",
    "CommunicationTemplatePreviewResponse",
    "MessageBase",
    "MessageCreate",
    "MessageResponse",
    "MessageRetryResponse",
    "DeliveryBase",
    "DeliveryCreate",
    "DeliveryResponse",
    "OrderWebhookPayload",
    "EvolutionWebhookPayload",
    "WebhookProcessingResponse",
    "CaktoWebhookPayload",
    "CaktoOrderData",
    "CaktoCustomer",
    "CaktoProduct",
    "CaktoOffer",
    "CaktoPix",
    "CaktoWebhookResponse",
]
