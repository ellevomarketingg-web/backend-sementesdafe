from fastapi import APIRouter
from app.api.routes import (
    health,
    buyers,
    orders,
    books,
    order_bumps,
    templates,
    messages,
    webhooks,
    delivery,
)

api_router = APIRouter()

# Health checks
api_router.include_router(health.router)

# Domain routes under /api/v1
api_router.include_router(buyers.router)
api_router.include_router(orders.router)
api_router.include_router(books.router)
api_router.include_router(order_bumps.router)
api_router.include_router(templates.router)
api_router.include_router(messages.router)
api_router.include_router(webhooks.router)
api_router.include_router(delivery.router)

