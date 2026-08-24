from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.order import Order, OrderStatus
from app.schemas.order import OrderCreate
from app.core.logging import logger


class OrderService:
    @staticmethod
    async def get_by_id(session: AsyncSession, order_id: str) -> Optional[Order]:
        return await session.get(Order, order_id)

    @staticmethod
    async def get_by_external_id(session: AsyncSession, external_id: str) -> Optional[Order]:
        stmt = select(Order).where(Order.external_order_id == external_id)
        return (await session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def get_paid_orders_for_buyer(session: AsyncSession, buyer_id: str) -> List[Order]:
        stmt = select(Order).where(
            Order.buyer_id == buyer_id,
            Order.status == OrderStatus.PAID,
        ).order_by(Order.created_at.desc())
        return list((await session.execute(stmt)).scalars().all())

    @classmethod
    async def create_or_update_from_webhook(
        cls,
        session: AsyncSession,
        external_order_id: str,
        buyer_id: str,
        amount: float,
        status: OrderStatus,
        product_code: str = "DEUS_CONHECE_SEU_NOME",
        product_name: str = "Deus Conhece o Seu Nome",
        paid_at: Optional[datetime] = None,
        metadata_info: Optional[dict] = None,
    ) -> Order:
        order = await cls.get_by_external_id(session, external_order_id)
        if order:
            order.status = status
            order.amount = amount
            if status == OrderStatus.PAID and not order.paid_at:
                order.paid_at = paid_at or datetime.now(timezone.utc)
            if metadata_info:
                order.metadata_info = metadata_info
            await session.commit()
            await session.refresh(order)
            logger.info(f"Pedido atualizado id={order.id} status={order.status}")
            return order

        order = Order(
            external_order_id=external_order_id,
            buyer_id=buyer_id,
            product_code=product_code,
            product_name=product_name,
            amount=amount,
            status=status,
            paid_at=paid_at or (datetime.now(timezone.utc) if status == OrderStatus.PAID else None),
            metadata_info=metadata_info,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        logger.info(f"Novo pedido criado id={order.id} external_id={external_order_id} status={status}")
        return order
