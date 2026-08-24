import pytest
import httpx
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.buyer import Buyer
from app.models.order import Order, OrderStatus
from app.models.book import Book, BookStatus
from app.models.order_bump import OrderBump, OrderBumpStatus
from app.core.config import settings


@pytest.mark.asyncio
async def test_delivery_check_book_access_scenarios(client: httpx.AsyncClient, db_session: AsyncSession):
    # 1. Comprador inexistente
    res_not_found = await client.post("/api/v1/delivery/check-book-access", json={"email": "desconhecido@email.com"})
    assert res_not_found.status_code == 200
    assert res_not_found.json()["status"] == "no_purchase"

    # 2. Comprador com pedido pendente (não pago)
    buyer1 = Buyer(
        email="pendente@teste.com",
        email_normalized="pendente@teste.com",
        name="Pendente Silva",
        generation_credits=0,
    )
    db_session.add(buyer1)
    await db_session.commit()
    await db_session.refresh(buyer1)

    order_pending = Order(
        external_order_id="ext_ord_pend_1",
        buyer_id=buyer1.id,
        status=OrderStatus.PENDING,
        amount=27.00,
    )
    db_session.add(order_pending)
    await db_session.commit()

    res_pend = await client.post("/api/v1/delivery/check-book-access", json={"email": "pendente@teste.com"})
    assert res_pend.status_code == 200
    assert res_pend.json()["status"] == "no_purchase"

    # 3. Comprador com compra aprovada e créditos para gerar (can_generate)
    buyer2 = Buyer(
        email="novacompra@teste.com",
        email_normalized="novacompra@teste.com",
        name="Renata Lima",
        generation_credits=1,
    )
    db_session.add(buyer2)
    await db_session.commit()
    await db_session.refresh(buyer2)

    order_paid = Order(
        external_order_id="ext_ord_paid_2",
        buyer_id=buyer2.id,
        status=OrderStatus.PAID,
        amount=27.00,
    )
    db_session.add(order_paid)
    await db_session.commit()

    res_new = await client.post("/api/v1/delivery/check-book-access", json={"email": "novacompra@teste.com"})
    assert res_new.status_code == 200
    data_new = res_new.json()
    assert data_new["status"] == "can_generate"
    assert data_new["can_generate"] is True
    assert data_new["credits"] == 1

    # 4. Comprador que já gerou o livro e tem 0 créditos (already_generated)
    buyer3 = Buyer(
        email="jagerou@teste.com",
        email_normalized="jagerou@teste.com",
        name="Claudio Ramos",
        generation_credits=0,
    )
    db_session.add(buyer3)
    await db_session.commit()
    await db_session.refresh(buyer3)

    order_paid3 = Order(
        external_order_id="ext_ord_paid_3",
        buyer_id=buyer3.id,
        status=OrderStatus.PAID,
        amount=27.00,
    )
    db_session.add(order_paid3)
    await db_session.commit()
    await db_session.refresh(order_paid3)

    book_ready = Book(
        buyer_id=buyer3.id,
        order_id=order_paid3.id,
        child_name="Mateus",
        status=BookStatus.READY,
        file_path="/tmp/fake_book.pdf",
    )
    db_session.add(book_ready)
    await db_session.commit()

    res_gen = await client.post("/api/v1/delivery/check-book-access", json={"email": "jagerou@teste.com"})
    assert res_gen.status_code == 200
    data_gen = res_gen.json()
    assert data_gen["status"] == "already_generated"
    assert data_gen["can_generate"] is False
    assert data_gen["book"]["child_name"] == "Mateus"
    assert "download?token=" in data_gen["book"]["download_url"]


@pytest.mark.asyncio
async def test_delivery_create_book_and_whatsapp_flow(client: httpx.AsyncClient, db_session: AsyncSession):
    buyer = Buyer(
        email="fabricio@teste.com",
        email_normalized="fabricio@teste.com",
        name="Fabricio Santos",
        phone="11988887777",
        generation_credits=1,
    )
    db_session.add(buyer)
    await db_session.commit()
    await db_session.refresh(buyer)

    order = Order(
        external_order_id="ext_ord_fab_100",
        buyer_id=buyer.id,
        status=OrderStatus.PAID,
        amount=27.00,
    )
    db_session.add(order)
    await db_session.commit()

    # Criação do livro passando nome e modelo Menino
    payload = {
        "email": "fabricio@teste.com",
        "nome_crianca": "Benício",
        "genero": "M",
    }
    res_create = await client.post("/api/v1/delivery/create-book", json=payload)
    assert res_create.status_code == 200
    data_book = res_create.json()
    assert data_book["status"] == "ok"
    assert data_book["book"]["nome_crianca"] == "Benício"
    assert "token=" in data_book["book"]["download_url"]
    book_id = data_book["book"]["id"]

    # Envio via WhatsApp
    with patch("app.services.evolution_service.evolution_service.send_text", new_callable=AsyncMock) as mock_send_text, \
         patch("app.services.evolution_service.evolution_service.send_document", new_callable=AsyncMock) as mock_send_doc:
        mock_send_text.return_value = {"success": True, "external_message_id": "wamid_123"}
        mock_send_doc.return_value = {"success": True, "external_message_id": "wamid_456"}

        res_wa = await client.post(
            "/api/v1/delivery/send-book-whatsapp",
            json={
                "book_id": book_id,
                "telefone": "11988887777",
            },
        )
        assert res_wa.status_code == 200
        assert res_wa.json()["status"] == "ok"
        assert mock_send_text.called
        assert mock_send_doc.called


@pytest.mark.asyncio
async def test_delivery_order_bumps_access_and_whatsapp(client: httpx.AsyncClient, db_session: AsyncSession):
    buyer = Buyer(
        email="amanda@teste.com",
        email_normalized="amanda@teste.com",
        name="Amanda Oliveira",
        phone="21977776666",
    )
    db_session.add(buyer)
    await db_session.commit()
    await db_session.refresh(buyer)

    # 1. Sem acesso
    res_no_access = await client.post(
        "/api/v1/delivery/check-order-bump-access",
        json={"email": "amanda@teste.com", "product_type": "calendario"},
    )
    assert res_no_access.status_code == 200
    assert res_no_access.json()["status"] == "no_access"

    # Concede Calendário e Figurinhas
    ob_cal = OrderBump(
        buyer_id=buyer.id,
        product_id=settings.CAKTO_ORDER_BUMP_CALENDAR_ID,
        product_name="Calendário Cristão Infantil",
        product_code="CHRISTIAN_CALENDAR",
        status=OrderBumpStatus.UNLOCKED,
    )
    ob_stickers = OrderBump(
        buyer_id=buyer.id,
        product_id=settings.CAKTO_ORDER_BUMP_STICKERS_ID,
        product_name="Pack de Figurinhas Cristãs",
        product_code="STICKERS_PACK",
        status=OrderBumpStatus.UNLOCKED,
    )
    db_session.add_all([ob_cal, ob_stickers])
    await db_session.commit()

    # 2. Check Acesso Calendário
    res_cal = await client.post(
        "/api/v1/delivery/check-order-bump-access",
        json={"email": "amanda@teste.com", "product_type": "calendario"},
    )
    assert res_cal.status_code == 200
    data_cal = res_cal.json()
    assert data_cal["status"] == "ok"
    assert data_cal["has_access"] is True
    assert "token=" in data_cal["download_url"]

    # 3. Check Acesso Figurinhas
    res_stickers = await client.post(
        "/api/v1/delivery/check-order-bump-access",
        json={"email": "amanda@teste.com", "product_type": "figurinhas"},
    )
    assert res_stickers.status_code == 200
    data_stickers = res_stickers.json()
    assert data_stickers["status"] == "ok"
    assert data_stickers["has_access"] is True
    assert len(data_stickers["sticker_links"]) == 4
    assert "https://sticker.ly/s/PBUUGL" in data_stickers["sticker_links"]

    # 4. WhatsApp Calendário
    with patch("app.services.evolution_service.evolution_service.send_text", new_callable=AsyncMock) as mock_send_text, \
         patch("app.services.evolution_service.evolution_service.send_document", new_callable=AsyncMock) as mock_send_doc:
        mock_send_text.return_value = {"success": True}
        mock_send_doc.return_value = {"success": True}

        res_send_cal = await client.post(
            "/api/v1/delivery/send-order-bump-whatsapp",
            json={
                "email": "amanda@teste.com",
                "telefone": "21977776666",
                "product_type": "calendario",
            },
        )
        assert res_send_cal.status_code == 200
        assert res_send_cal.json()["status"] == "ok"
        assert mock_send_text.called
        assert mock_send_doc.called

    # 5. WhatsApp Figurinhas (envia texto receptivo + 'Responda com "OK" para eu te enviar o pack de figurinhas.')
    with patch("app.services.evolution_service.evolution_service.send_text", new_callable=AsyncMock) as mock_send_text:
        mock_send_text.return_value = {"success": True}

        res_send_stk = await client.post(
            "/api/v1/delivery/send-order-bump-whatsapp",
            json={
                "email": "amanda@teste.com",
                "telefone": "21977776666",
                "product_type": "figurinhas",
            },
        )
        assert res_send_stk.status_code == 200
        assert res_send_stk.json()["status"] == "ok"
        # Verifica se a mensagem de instrução esperada foi enviada
        calls = [call_args.kwargs.get("message") or call_args.args[1] for call_args in mock_send_text.call_args_list]
        assert any('Responda com "OK" para eu te enviar o pack de figurinhas.' in str(c) for c in calls)
