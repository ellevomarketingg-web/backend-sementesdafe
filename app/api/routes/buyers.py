from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.deps import get_admin_user
from app.models.buyer import Buyer
from app.schemas.buyer import BuyerResponse
from app.services.buyer_service import BuyerService

router = APIRouter(prefix="/buyers", tags=["Buyers"])


@router.get("", response_model=List[BuyerResponse])
async def list_buyers(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_user),
):
    """Lista compradores cadastrados (Apenas Admin)."""
    stmt = select(Buyer).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{buyer_id}", response_model=BuyerResponse)
async def get_buyer(
    buyer_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_user),
):
    """Obtém detalhes do comprador por ID (Apenas Admin)."""
    buyer = await BuyerService.get_by_id(db, buyer_id)
    if not buyer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comprador não encontrado.")
    return buyer
