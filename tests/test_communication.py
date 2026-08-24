import pytest
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.buyer import Buyer
from app.models.order import Order, OrderStatus
from app.models.book import Book
from app.models.message import Message, MessageStatus
from app.services.communication_service import CommunicationService


@pytest.mark.asyncio
async def test_communication_service_dispatch_and_retry(client: httpx.AsyncClient, db_session: AsyncSession, admin_headers: dict):
    # 1. Cria comprador e livro
    buyer = Buyer(
        email="fernanda@email.com",
        email_normalized="fernanda@email.com",
        name="Fernanda Rocha",
        phone="5511977776666",
    )
    db_session.add(buyer)
    await db_session.commit()
    await db_session.refresh(buyer)

    order = Order(
        external_order_id="order_fernanda_200",
        buyer_id=buyer.id,
        status=OrderStatus.PAID,
        amount=49.90,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    book = Book(
        buyer_id=buyer.id,
        order_id=order.id,
        child_name="Mateus",
    )
    db_session.add(book)
    await db_session.commit()
    await db_session.refresh(book)

    # 2. Dispara comunicação BOOK_READY
    msg = await CommunicationService.create_and_dispatch_message(
        session=db_session,
        buyer=buyer,
        event_code="BOOK_READY",
        channel="WHATSAPP",
        book=book,
        send_immediately=True,
    )
    assert msg.id is not None
    assert msg.status == MessageStatus.SENT
    assert "Fernanda Rocha" in msg.content
    assert "Mateus" in msg.content
    assert msg.external_message_id is not None

    # 3. Testa endpoint de listagem de mensagens (Admin)
    list_res = await client.get("/api/v1/messages", headers=admin_headers)
    assert list_res.status_code == 200
    messages = list_res.json()
    assert len(messages) >= 1

    # 4. Testa endpoint de retry
    retry_res = await client.post(f"/api/v1/messages/{msg.id}/retry", headers=admin_headers)
    assert retry_res.status_code == 200
    assert retry_res.json()["status"] == "ENQUEUED"
