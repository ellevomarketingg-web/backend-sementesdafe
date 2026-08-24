import asyncio
from app.core.database import AsyncSessionLocal
from app.models.message import Message, MessageStatus
from app.services.communication_service import CommunicationService
from app.core.logging import logger

MAX_ATTEMPTS = 4
BACKOFF_DELAYS = [60, 300, 900, 1800]  # 1m, 5m, 15m, 30m


async def process_message_dispatch_job(message_id: str) -> None:
    """Worker task para envio de mensagens com retry e backoff exponencial."""
    logger.info(f"[MessageWorker] Iniciando disparo da mensagem id={message_id}")
    async with AsyncSessionLocal() as session:
        message = await session.get(Message, message_id)
        if not message:
            logger.error(f"[MessageWorker] Mensagem {message_id} não encontrada.")
            return

        if message.status in (MessageStatus.SENT, MessageStatus.DELIVERED):
            logger.info(f"[MessageWorker] Mensagem {message_id} já enviada.")
            return

        await CommunicationService.process_send_message(session, message)

        if message.status == MessageStatus.FAILED and message.attempts < MAX_ATTEMPTS:
            delay = BACKOFF_DELAYS[min(message.attempts - 1, len(BACKOFF_DELAYS) - 1)]
            logger.warning(
                f"[MessageWorker] Tentativa {message.attempts} falhou para mensagem {message_id}. Reagendando em {delay}s."
            )
            # Agenda retry
            asyncio.create_task(_schedule_retry(message_id, delay))


async def _schedule_retry(message_id: str, delay: int) -> None:
    await asyncio.sleep(delay)
    await process_message_dispatch_job(message_id)
