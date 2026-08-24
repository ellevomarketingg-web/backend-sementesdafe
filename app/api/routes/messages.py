from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.deps import get_admin_user
from app.models.message import Message
from app.models.buyer import Buyer
from app.schemas.message import MessageResponse, MessageCreate, MessageRetryResponse
from app.services.communication_service import CommunicationService
from app.workers.queue import job_queue
from app.workers.message_worker import process_message_dispatch_job

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.post("", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message(
    payload: MessageCreate,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_user),
):
    """Cria e enfileira uma mensagem manualmente (Apenas Admin)."""
    buyer = await db.get(Buyer, payload.buyer_id)
    if not buyer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comprador não encontrado.")

    message = Message(
        buyer_id=payload.buyer_id,
        book_id=payload.book_id,
        template_id=payload.template_id,
        template_version=payload.template_version,
        channel=payload.channel,
        destination=payload.destination,
        content=payload.content,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    await job_queue.enqueue(process_message_dispatch_job, message.id)
    return message


@router.get("", response_model=List[MessageResponse])
async def list_messages(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_user),
):
    """Lista mensagens de comunicação (Apenas Admin)."""
    stmt = select(Message).offset(skip).limit(limit).order_by(Message.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{message_id}", response_model=MessageResponse)
async def get_message(
    message_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_user),
):
    """Obtém detalhes da mensagem (Apenas Admin)."""
    message = await db.get(Message, message_id)
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mensagem não encontrada.")
    return message


@router.post("/{message_id}/retry", response_model=MessageRetryResponse)
async def retry_message(
    message_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_user),
):
    """Reprocessa o envio de uma mensagem com falha (Apenas Admin)."""
    message = await db.get(Message, message_id)
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mensagem não encontrada.")

    await job_queue.enqueue(process_message_dispatch_job, message.id)
    return MessageRetryResponse(
        message_id=message.id,
        status="ENQUEUED",
        detail="Mensagem enfileirada para reprocessamento.",
    )
