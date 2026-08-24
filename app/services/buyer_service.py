from typing import Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.buyer import Buyer
from app.schemas.buyer import BuyerCreate, BuyerUpdate
from app.utils.email import normalize_email
from app.utils.phone import normalize_phone
from app.core.logging import logger


class BuyerService:
    @staticmethod
    async def get_by_id(session: AsyncSession, buyer_id: str) -> Optional[Buyer]:
        return await session.get(Buyer, buyer_id)

    @staticmethod
    async def get_by_email(session: AsyncSession, email: str) -> Optional[Buyer]:
        email_norm = normalize_email(email)
        stmt = select(Buyer).where(Buyer.email_normalized == email_norm)
        return (await session.execute(stmt)).scalar_one_or_none()

    @classmethod
    async def create(cls, session: AsyncSession, data: BuyerCreate) -> Buyer:
        email_norm = normalize_email(data.email)
        phone_norm = normalize_phone(data.phone)
        
        buyer = Buyer(
            email=data.email,
            email_normalized=email_norm,
            name=data.name,
            phone=phone_norm,
        )
        session.add(buyer)
        await session.commit()
        await session.refresh(buyer)
        logger.info(f"Comprador criado id={buyer.id} email={email_norm}")
        return buyer

    @classmethod
    async def get_or_create(
        cls,
        session: AsyncSession,
        email: str,
        name: str,
        phone: Optional[str] = None,
    ) -> Tuple[Buyer, bool]:
        """Retorna (buyer, created: bool)."""
        email_norm = normalize_email(email)
        phone_norm = normalize_phone(phone)
        
        existing = await cls.get_by_email(session, email_norm)
        if existing:
            # Atualiza telefone ou nome se novos forem fornecidos
            updated = False
            if phone_norm and not existing.phone:
                existing.phone = phone_norm
                updated = True
            if name and (existing.name != name):
                existing.name = name
                updated = True
            if updated:
                await session.commit()
                await session.refresh(existing)
            return existing, False

        buyer = Buyer(
            email=email,
            email_normalized=email_norm,
            name=name,
            phone=phone_norm,
        )
        session.add(buyer)
        await session.commit()
        await session.refresh(buyer)
        logger.info(f"Novo comprador registrado id={buyer.id} email={email_norm}")
        return buyer, True
