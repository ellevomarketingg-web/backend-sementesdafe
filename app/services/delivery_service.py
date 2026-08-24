from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.delivery import Delivery, DeliveryStatus
from app.models.book import Book
from app.models.buyer import Buyer
from app.core.logging import logger


class DeliveryService:
    @staticmethod
    async def get_by_id(session: AsyncSession, delivery_id: str) -> Optional[Delivery]:
        return await session.get(Delivery, delivery_id)

    @staticmethod
    async def get_by_book_id(session: AsyncSession, book_id: str) -> List[Delivery]:
        stmt = select(Delivery).where(Delivery.book_id == book_id)
        return list((await session.execute(stmt)).scalars().all())

    @classmethod
    async def create_delivery_record(
        cls,
        session: AsyncSession,
        book: Book,
        buyer: Buyer,
        channel: str = "WHATSAPP",
        delivery_url: Optional[str] = None,
    ) -> Delivery:
        destination = buyer.phone if channel == "WHATSAPP" else buyer.email_normalized
        delivery = Delivery(
            book_id=book.id,
            buyer_id=buyer.id,
            channel=channel,
            destination=destination or "unspecified",
            delivery_url=delivery_url or book.file_url,
            status=DeliveryStatus.PENDING,
            attempts=0,
        )
        session.add(delivery)
        await session.commit()
        await session.refresh(delivery)
        logger.info(f"Registro de entrega criado id={delivery.id} book_id={book.id}")
        return delivery

    @classmethod
    async def mark_delivered(
        cls,
        session: AsyncSession,
        delivery_id: str,
    ) -> Optional[Delivery]:
        delivery = await session.get(Delivery, delivery_id)
        if delivery:
            delivery.status = DeliveryStatus.DELIVERED
            delivery.completed_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(delivery)
        return delivery

    @classmethod
    async def mark_failed(
        cls,
        session: AsyncSession,
        delivery_id: str,
        error: str,
    ) -> Optional[Delivery]:
        delivery = await session.get(Delivery, delivery_id)
        if delivery:
            delivery.status = DeliveryStatus.FAILED
            delivery.last_error = error
            delivery.attempts += 1
            await session.commit()
            await session.refresh(delivery)
        return delivery
