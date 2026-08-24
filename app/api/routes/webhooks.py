import hmac
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Header, Request, status, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.config import settings
from app.core.security import verify_webhook_signature
from app.core.logging import logger
from app.models.processed_event import ProcessedEvent
from app.models.order import OrderStatus
from app.models.message import Message, MessageStatus
from app.models.delivery import Delivery, DeliveryStatus
from app.schemas.webhook import (
    OrderWebhookPayload,
    EvolutionWebhookPayload,
    WebhookProcessingResponse,
)
from app.schemas.cakto import (
    CaktoWebhookPayload,
    CaktoWebhookResponse,
)
from app.services.buyer_service import BuyerService
from app.services.order_service import OrderService
from app.services.book_service import BookService
from app.services.order_bump_service import OrderBumpService
from app.services.communication_service import CommunicationService
from app.workers.queue import job_queue
from app.workers.book_worker import process_book_generation_job

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/orders", response_model=WebhookProcessingResponse, status_code=status.HTTP_200_OK)
async def handle_order_webhook(
    payload: OrderWebhookPayload,
    request: Request,
    x_signature: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Webhook para recebimento e processamento de compras com verificação de idempotência.
    """
    # 1. Checagem de Idempotência (event_id único)
    stmt = select(ProcessedEvent).where(ProcessedEvent.event_id == payload.event_id)
    existing_event = (await db.execute(stmt)).scalar_one_or_none()
    if existing_event:
        logger.info(f"Evento {payload.event_id} já processado anteriormente. Ignorando execução duplicada.")
        return WebhookProcessingResponse(
            received=True,
            status="ALREADY_PROCESSED",
            detail="Evento já processado anteriormente com sucesso.",
            event_id=payload.event_id,
        )

    # 2. Busca ou cria Comprador
    buyer, _ = await BuyerService.get_or_create(
        session=db,
        email=payload.buyer.email,
        name=payload.buyer.name,
        phone=payload.buyer.phone,
    )

    # 3. Parse e atualização do Pedido
    order_status = OrderStatus.PAID if payload.order.status.upper() == "PAID" else OrderStatus.PENDING
    order = await OrderService.create_or_update_from_webhook(
        session=db,
        external_order_id=payload.order.external_order_id,
        buyer_id=buyer.id,
        amount=payload.order.amount,
        status=order_status,
        product_code=payload.order.product_code,
        product_name=payload.order.product_name,
        paid_at=payload.order.paid_at,
        metadata_info=payload.metadata,
    )

    # 4. Registra evento de idempotência
    processed = ProcessedEvent(
        event_id=payload.event_id,
        event_type=payload.event_type,
        payload=payload.model_dump(mode="json"),
    )
    db.add(processed)
    await db.commit()

    # 5. Se o pedido for pago, cria o livro e enfileira geração
    if order.status == OrderStatus.PAID:
        child_name = (payload.metadata.get("child_name") if payload.metadata else "") or ""
        book = await BookService.create_book_for_order(
            session=db,
            order=order,
            child_name=child_name,
        )

        # Dispara comunicação PURCHASE_CONFIRMED
        if buyer.phone:
            try:
                await CommunicationService.create_and_dispatch_message(
                    session=db,
                    buyer=buyer,
                    event_code="PURCHASE_CONFIRMED",
                    channel="WHATSAPP",
                    book=book,
                    send_immediately=True,
                )
            except Exception as e:
                logger.error(f"Erro ao disparar mensagem de confirmação de compra: {e}")

        # Enfileira geração assíncrona do PDF
        await job_queue.enqueue(process_book_generation_job, book.id)

    return WebhookProcessingResponse(
        received=True,
        status="PROCESSED",
        detail="Compra processada e livro enfileirado com sucesso.",
        event_id=payload.event_id,
    )


@router.post("/evolution", response_model=WebhookProcessingResponse, status_code=status.HTTP_200_OK)
async def handle_evolution_webhook(
    payload: EvolutionWebhookPayload,
    db: AsyncSession = Depends(get_db),
):
    """
    Webhook para recebimento de status de mensagens da Evolution API (WhatsApp).
    Correlaciona external_message_id com a entidade Message.
    """
    event_name = payload.event.lower()
    data = payload.data or {}
    
    # Extrai external_id
    external_id = (
        data.get("key", {}).get("id")
        or data.get("id")
        or data.get("messageId")
        or (data.get("messages", [{}])[0].get("key", {}).get("id") if isinstance(data.get("messages"), list) and data.get("messages") else None)
    )

    if not external_id:
        return WebhookProcessingResponse(
            received=True,
            status="IGNORED",
            detail="Nenhum identificador de mensagem encontrado no payload.",
        )

    # Localiza mensagem no banco
    stmt = select(Message).where(Message.external_message_id == external_id)
    message = (await db.execute(stmt)).scalar_one_or_none()
    
    if not message:
        logger.info(f"Mensagem externa {external_id} não vinculada a nenhum registro interno.")
        return WebhookProcessingResponse(
            received=True,
            status="MESSAGE_NOT_FOUND",
            detail=f"external_id {external_id} não localizado.",
        )

    # Atualiza status conforme o evento
    if "delivered" in event_name or "read" in event_name or data.get("status") in ("DELIVERY_ACK", "READ"):
        message.status = MessageStatus.DELIVERED
        # Atualiza entrega se houver livro associado
        if message.book_id:
            stmt_del = select(Delivery).where(Delivery.book_id == message.book_id)
            delivery = (await db.execute(stmt_del)).scalar_one_or_none()
            if delivery:
                delivery.status = DeliveryStatus.DELIVERED
                delivery.completed_at = datetime.now(timezone.utc)

    elif "failed" in event_name or data.get("status") == "ERROR":
        message.status = MessageStatus.FAILED
        message.error_message = str(data.get("error") or data.get("reason") or "Falha reportada pelo webhook")
        if message.book_id:
            stmt_del = select(Delivery).where(Delivery.book_id == message.book_id)
            delivery = (await db.execute(stmt_del)).scalar_one_or_none()
            if delivery:
                delivery.status = DeliveryStatus.FAILED
                delivery.last_error = message.error_message

    elif "sent" in event_name or data.get("status") == "SENT":
        message.status = MessageStatus.SENT

    await db.commit()
    logger.info(f"Mensagem {message.id} atualizada para {message.status} via webhook Evolution.")

    return WebhookProcessingResponse(
        received=True,
        status="PROCESSED",
        detail=f"Mensagem {message.id} atualizada para {message.status}.",
    )


@router.post("/cakto", response_model=CaktoWebhookResponse, status_code=status.HTTP_200_OK)
@router.post("/cakto/purchase-approved", response_model=CaktoWebhookResponse, status_code=status.HTTP_200_OK)
async def handle_cakto_webhook(
    payload: CaktoWebhookPayload,
    db: AsyncSession = Depends(get_db),
):
    """
    Webhook oficial para processamento de pagamentos da Cakto (purchase_approved).
    Suporta o produto principal (Livro Personalizado) e Order Bumps (Figurinhas WhatsApp, Calendário).
    """
    # 1. Validação de Segurança (secret com compare_digest)
    if not hmac.compare_digest(payload.secret, settings.CAKTO_WEBHOOK_SECRET):
        logger.warning(f"[CaktoWebhook] Tentativa com secret inválido para pedido id={payload.data.id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid secret",
        )

    # 2. Identificação do Evento
    if payload.event != "purchase_approved":
        logger.info(f"[CaktoWebhook] Evento '{payload.event}' recebido e ignorado com 200 OK.")
        return CaktoWebhookResponse(
            received=True,
            status="ignored",
            detail=f"Evento '{payload.event}' ignorado.",
            event_id=payload.data.id,
        )

    # 3. Validação do Produto / Order Bumps
    incoming_product_id = payload.data.product.id if payload.data.product else ""
    is_main_book = bool(settings.CAKTO_PRODUCT_ID and incoming_product_id == settings.CAKTO_PRODUCT_ID)
    is_order_bump_main = incoming_product_id in settings.order_bumps_catalog

    # Extrai order bumps adicionais do payload
    embedded_bumps = payload.data.order_bumps or payload.data.orderBumps or payload.data.items or []
    has_recognized_embedded_bumps = any(
        (
            item.get("product", {}).get("id")
            or item.get("id")
            or item.get("product_id")
        ) in settings.order_bumps_catalog
        for item in embedded_bumps
        if isinstance(item, dict)
    )

    if not is_main_book and not is_order_bump_main and not has_recognized_embedded_bumps:
        logger.info(
            f"[CaktoWebhook] Produto '{incoming_product_id}' ignorado (não configurado no catálogo)."
        )
        return CaktoWebhookResponse(
            received=True,
            status="ignored",
            detail=f"Produto '{incoming_product_id}' não configurado no catálogo de produtos e order bumps.",
            event_id=payload.data.id,
        )

    # 4. Idempotência (data.id da Cakto)
    event_id = payload.data.id
    stmt = select(ProcessedEvent).where(ProcessedEvent.event_id == event_id)
    existing_event = (await db.execute(stmt)).scalar_one_or_none()
    if existing_event:
        logger.info(f"[CaktoWebhook] Pedido {event_id} já processado anteriormente. Retornando 'duplicate'.")
        return CaktoWebhookResponse(
            received=True,
            status="duplicate",
            detail="Pedido já processado anteriormente.",
            event_id=event_id,
        )

    # 5. Criação / Atualização do Comprador e Crédito de Geração
    customer = payload.data.customer
    buyer, _ = await BuyerService.get_or_create(
        session=db,
        email=customer.email,
        name=customer.name,
        phone=customer.phone,
    )

    is_paid = payload.data.status.lower() == "paid"
    order_status = OrderStatus.PAID if is_paid else OrderStatus.PENDING

    if is_paid and is_main_book:
        buyer.generation_credits += 1
        logger.info(
            f"[CaktoWebhook] +1 crédito concedido ao comprador {buyer.email_normalized} (total: {buyer.generation_credits})"
        )

    # Parse paidAt se fornecido
    paid_at = None
    if payload.data.paidAt:
        if isinstance(payload.data.paidAt, datetime):
            paid_at = payload.data.paidAt
        elif isinstance(payload.data.paidAt, str):
            try:
                paid_at = datetime.fromisoformat(payload.data.paidAt.replace("Z", "+00:00"))
            except Exception:
                paid_at = datetime.now(timezone.utc)

    # Informações do Produto
    product_name = payload.data.product.name if payload.data.product and payload.data.product.name else "Deus Conhece o Seu Nome"
    product_code = (
        (payload.data.product.short_id if payload.data.product else None)
        or (payload.data.product.id if payload.data.product else None)
        or "DEUS_CONHECE_SEU_NOME"
    )

    # Salva payload bruto completo em metadata_info para auditoria e relatórios
    order = await OrderService.create_or_update_from_webhook(
        session=db,
        external_order_id=payload.data.id,
        buyer_id=buyer.id,
        amount=payload.data.amount,
        status=order_status,
        product_code=product_code,
        product_name=product_name,
        paid_at=paid_at,
        metadata_info=payload.model_dump(mode="json"),
    )

    # 6. Processamento dos Order Bumps se compra paga
    if is_paid:
        # Se o produto principal for um order bump
        if is_order_bump_main:
            await OrderBumpService.grant_order_bump_access(
                session=db,
                buyer=buyer,
                order=order,
                product_id=incoming_product_id,
                product_name=product_name,
                metadata_info=payload.data.model_dump(mode="json"),
            )

        # Se houver order bumps embutidos na compra
        for bump_item in embedded_bumps:
            if not isinstance(bump_item, dict):
                continue
            bump_pid = (
                bump_item.get("product", {}).get("id")
                or bump_item.get("id")
                or bump_item.get("product_id")
            )
            if bump_pid in settings.order_bumps_catalog:
                bump_pname = bump_item.get("product", {}).get("name") or bump_item.get("name")
                await OrderBumpService.grant_order_bump_access(
                    session=db,
                    buyer=buyer,
                    order=order,
                    product_id=bump_pid,
                    product_name=bump_pname,
                    metadata_info=bump_item,
                )

    # 7. Gravação Atômica do Evento de Idempotência
    processed = ProcessedEvent(
        event_id=event_id,
        event_type=payload.event,
        payload=payload.model_dump(mode="json"),
    )
    db.add(processed)
    await db.commit()

    # 8. Processamento Assíncrono do Livro Principal se aplicável
    if order.status == OrderStatus.PAID and is_main_book:
        child_name = customer.name.split()[0] if customer.name else "Criança"
        book = await BookService.create_book_for_order(
            session=db,
            order=order,
            child_name=child_name,
        )

        # Dispara mensagem WhatsApp se telefone existir
        if buyer.phone:
            try:
                await CommunicationService.create_and_dispatch_message(
                    session=db,
                    buyer=buyer,
                    event_code="PURCHASE_CONFIRMED",
                    channel="WHATSAPP",
                    book=book,
                    send_immediately=True,
                )
            except Exception as e:
                logger.error(f"[CaktoWebhook] Erro ao disparar WhatsApp de confirmação: {e}")

        # Enfileira geração assíncrona do PDF
        await job_queue.enqueue(process_book_generation_job, book.id)

    logger.info(f"[CaktoWebhook] Venda aprovada {event_id} aceita e processada com sucesso.")
    return CaktoWebhookResponse(
        received=True,
        status="accepted",
        detail="Venda aprovada e produtos liberados com sucesso.",
        event_id=event_id,
    )

