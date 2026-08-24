from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.deps import get_admin_user
from app.models.order import Order, OrderStatus
from app.schemas.order import OrderCreate, OrderResponse
from app.services.order_service import OrderService
from app.services.book_service import BookService

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_user),
):
    """Cria um pedido manualmente (Apenas Admin)."""
    order = await OrderService.create_or_update_from_webhook(
        session=db,
        external_order_id=payload.external_order_id,
        buyer_id=payload.buyer_id,
        amount=payload.amount,
        status=payload.status,
        product_code=payload.product_code,
        product_name=payload.product_name,
        metadata_info=payload.metadata_info,
    )

    # Se status for PAID, cria livro automaticamente
    if order.status == OrderStatus.PAID:
        await BookService.create_book_for_order(db, order)

    return order


@router.get("", response_model=List[OrderResponse])
async def list_orders(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_user),
):
    """Lista pedidos (Apenas Admin)."""
    stmt = select(Order).offset(skip).limit(limit).order_by(Order.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_user),
):
    """Obtém detalhes do pedido por ID (Apenas Admin)."""
    order = await OrderService.get_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido não encontrado.")
    return order
