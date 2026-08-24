import pytest
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.buyer import Buyer
from app.models.order import Order, OrderStatus
from app.models.book import Book
from app.models.message import Message, MessageStatus
from app.models.delivery import Delivery, DeliveryStatus


@pytest.mark.asyncio
async def test_order_webhook_flow_and_idempotency(client: httpx.AsyncClient, db_session: AsyncSession):
    webhook_payload = {
        "event_id": "evt_mp_checkout_998877",
        "event_type": "order.paid",
        "order": {
            "external_order_id": "mp_order_123456",
            "status": "PAID",
            "amount": 49.90,
            "product_code": "DEUS_CONHECE_SEU_NOME",
            "product_name": "Deus Conhece o Seu Nome",
        },
        "buyer": {
            "email": "Comprador.Teste@Gmail.com",
            "name": "Carlos Eduardo",
            "phone": "(11) 98765-4321",
        },
        "metadata": {
            "child_name": "Lucas",
        },
    }

    # 1. Primeira chamada -> deve processar e criar as entidades
    res1 = await client.post("/api/v1/webhooks/orders", json=webhook_payload)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] == "PROCESSED"

    # Verifica se comprador foi criado com email normalizado
    stmt_buyer = select(Buyer).where(Buyer.email_normalized == "comprador.teste@gmail.com")
    buyer = (await db_session.execute(stmt_buyer)).scalar_one_or_none()
    assert buyer is not None
    assert buyer.name == "Carlos Eduardo"
    assert buyer.phone == "5511987654321"

    # Verifica pedido
    stmt_order = select(Order).where(Order.external_order_id == "mp_order_123456")
    order = (await db_session.execute(stmt_order)).scalar_one_or_none()
    assert order is not None
    assert order.status == OrderStatus.PAID

    # Verifica livro criado
    stmt_book = select(Book).where(Book.order_id == order.id)
    book = (await db_session.execute(stmt_book)).scalar_one_or_none()
    assert book is not None
    assert book.child_name == "Lucas"

    # 2. Segunda chamada com mesmo event_id -> deve retornar ALREADY_PROCESSED e não duplicar registros
    res2 = await client.post("/api/v1/webhooks/orders", json=webhook_payload)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "ALREADY_PROCESSED"

    # Contagem de compradores e livros
    stmt_all_buyers = select(Buyer)
    buyers = (await db_session.execute(stmt_all_buyers)).scalars().all()
    assert len(buyers) == 1

    stmt_all_books = select(Book)
    books = (await db_session.execute(stmt_all_books)).scalars().all()
    assert len(books) == 1


@pytest.mark.asyncio
async def test_evolution_webhook_message_status_update(client: httpx.AsyncClient, db_session: AsyncSession):
    # 1. Cria comprador, pedido, livro e mensagem prévia
    buyer = Buyer(
        email="mae@email.com",
        email_normalized="mae@email.com",
        name="Camila",
        phone="5511999990000",
    )
    db_session.add(buyer)
    await db_session.commit()
    await db_session.refresh(buyer)

    order = Order(
        external_order_id="order_camila_1",
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
        child_name="Beatriz",
    )
    db_session.add(book)
    await db_session.commit()
    await db_session.refresh(book)

    msg = Message(
        buyer_id=buyer.id,
        book_id=book.id,
        destination="5511999990000",
        content="Olá Camila, seu livro está pronto!",
        status=MessageStatus.SENT,
        external_message_id="evo_msg_abc_999",
    )
    db_session.add(msg)

    delivery = Delivery(
        book_id=book.id,
        buyer_id=buyer.id,
        destination="5511999990000",
        status=DeliveryStatus.PENDING,
    )
    db_session.add(delivery)
    await db_session.commit()

    # 2. Envia webhook da Evolution informando entrega
    evo_payload = {
        "event": "messages.delivered",
        "instance": "deus-conhece-nome",
        "data": {
            "key": {
                "id": "evo_msg_abc_999",
            },
            "status": "DELIVERY_ACK",
        },
    }
    res = await client.post("/api/v1/webhooks/evolution", json=evo_payload)
    assert res.status_code == 200
    assert res.json()["status"] == "PROCESSED"

    # 3. Verifica se Message e Delivery foram atualizados para DELIVERED
    await db_session.refresh(msg)
    await db_session.refresh(delivery)
    assert msg.status == MessageStatus.DELIVERED
    assert delivery.status == DeliveryStatus.DELIVERED
