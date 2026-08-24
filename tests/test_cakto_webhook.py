import pytest
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.buyer import Buyer
from app.models.order import Order, OrderStatus
from app.models.book import Book
from app.core.config import settings

# Payload oficial baseado na documentação da Cakto com o ID de produto oficial
CAKTO_PURCHASE_APPROVED_PAYLOAD = {
    "secret": settings.CAKTO_WEBHOOK_SECRET,
    "event": "purchase_approved",
    "data": {
        "id": "a9a957b9-62eb-4581-8594-5544ad5fa428",
        "refId": "ref_cakto_998877",
        "customer": {
            "name": "Mariana Ribeiro Santos",
            "birthDate": "1992-05-14",
            "email": "MARIANA.RIBEIRO@GMAIL.COM",
            "phone": "(21) 98765-4321",
            "docNumber": "12345678909",
        },
        "affiliate": None,
        "offer": {
            "id": "off_12345",
            "name": "Oferta Principal Livro",
            "price": 49.90,
        },
        "offer_type": "main",
        "product": {
            "name": "Deus Conhece o Seu Nome",
            "id": "d4c39c54-735b-416f-bbdf-47752679b492",
            "short_id": "DEUS_CONHECE_SEU_NOME",
            "supportEmail": "suporte@deusconheceoseunome.com.br",
            "type": "digital",
            "invoiceDescription": "Livro Digital Personalizado",
        },
        "checkoutUrl": "https://pay.cakto.com.br/checkout/123",
        "status": "paid",
        "baseAmount": 59.90,
        "discount": 10.00,
        "amount": 49.90,
        "commissions": [
            {
                "id": "comm_1",
                "amount": 5.00,
                "type": "platform",
                "recipientId": "rec_001",
            }
        ],
        "fees": {
            "gateway_fee": 1.99,
        },
        "couponCode": "BEMVINDO10",
        "reason": None,
        "refund_reason": None,
        "paymentMethod": "pix",
        "installments": 1,
        "pix": {
            "qrcode": "https://api.cakto.com.br/pix/qrcode.png",
            "qrcode_text": "00020126580014br.gov.bcb.pix...",
            "expirationDate": "2026-08-24T18:00:00-03:00",
        },
        "paidAt": "2026-08-24T15:00:00-03:00",
        "createdAt": "2026-08-24T14:55:00-03:00",
    },
}


@pytest.mark.asyncio
async def test_cakto_webhook_purchase_approved_flow(client: httpx.AsyncClient, db_session: AsyncSession):
    """Testa o fluxo completo de compra aprovada da Cakto com concessão de crédito."""
    response = await client.post("/api/v1/webhooks/cakto", json=CAKTO_PURCHASE_APPROVED_PAYLOAD)
    assert response.status_code == 200
    data = response.json()
    assert data["received"] is True
    assert data["status"] == "accepted"
    assert data["event_id"] == "a9a957b9-62eb-4581-8594-5544ad5fa428"

    # Verifica comprador com email, telefone e crédito concedido
    stmt_buyer = select(Buyer).where(Buyer.email_normalized == "mariana.ribeiro@gmail.com")
    buyer = (await db_session.execute(stmt_buyer)).scalar_one_or_none()
    assert buyer is not None
    assert buyer.name == "Mariana Ribeiro Santos"
    assert buyer.phone == "5521987654321"
    assert buyer.generation_credits == 1

    # Verifica pedido
    stmt_order = select(Order).where(Order.external_order_id == "a9a957b9-62eb-4581-8594-5544ad5fa428")
    order = (await db_session.execute(stmt_order)).scalar_one_or_none()
    assert order is not None
    assert order.status == OrderStatus.PAID
    assert float(order.amount) == 49.90
    assert order.metadata_info["data"]["couponCode"] == "BEMVINDO10"

    # Verifica livro criado
    stmt_book = select(Book).where(Book.order_id == order.id)
    book = (await db_session.execute(stmt_book)).scalar_one_or_none()
    assert book is not None
    assert book.child_name == "Mariana"


@pytest.mark.asyncio
async def test_cakto_webhook_unrelated_product_ignored(client: httpx.AsyncClient):
    """Testa que produto não configurado é ignorado com 200 OK sem gerar créditos."""
    other_product_payload = dict(CAKTO_PURCHASE_APPROVED_PAYLOAD)
    other_product_payload["data"] = dict(CAKTO_PURCHASE_APPROVED_PAYLOAD["data"])
    other_product_payload["data"]["id"] = "order_other_prod_111"
    other_product_payload["data"]["product"] = {
        "id": "outro_produto_qualquer",
        "name": "Outro Curso Online",
    }

    response = await client.post("/api/v1/webhooks/cakto", json=other_product_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ignored"


@pytest.mark.asyncio
async def test_cakto_webhook_invalid_secret(client: httpx.AsyncClient):
    """Testa rejeição com 401 ao enviar secret inválido."""
    bad_payload = dict(CAKTO_PURCHASE_APPROVED_PAYLOAD)
    bad_payload["secret"] = "wrong-secret-token"

    response = await client.post("/api/v1/webhooks/cakto", json=bad_payload)
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid secret"


@pytest.mark.asyncio
async def test_cakto_webhook_ignored_event(client: httpx.AsyncClient):
    """Testa retorno 200 OK com 'ignored' para eventos desconhecidos/não tratados."""
    refund_payload = {
        "secret": settings.CAKTO_WEBHOOK_SECRET,
        "event": "purchase_chargeback",
        "data": {
            "id": "order_chargeback_123",
            "customer": {
                "name": "Cliente Chargeback",
                "email": "chargeback@email.com",
            },
            "status": "chargeback",
            "amount": 49.90,
        },
    }

    response = await client.post("/api/v1/webhooks/cakto", json=refund_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["received"] is True
    assert data["status"] == "ignored"


@pytest.mark.asyncio
async def test_cakto_webhook_idempotency(client: httpx.AsyncClient, db_session: AsyncSession):
    """Testa idempotência: reenvio do mesmo webhook retorna 200 OK duplicate sem recriar livro."""
    payload = dict(CAKTO_PURCHASE_APPROVED_PAYLOAD)
    payload["data"] = dict(CAKTO_PURCHASE_APPROVED_PAYLOAD["data"])
    payload["data"]["id"] = "order_idempotency_unique_uuid"

    # 1. Primeira chamada -> Processa
    res1 = await client.post("/api/v1/webhooks/cakto", json=payload)
    assert res1.status_code == 200
    assert res1.json()["status"] == "accepted"

    # 2. Segunda chamada com mesmo ID -> Retorna duplicate
    res2 = await client.post("/api/v1/webhooks/cakto", json=payload)
    assert res2.status_code == 200
    assert res2.json()["status"] == "duplicate"

    # Contagem de livros no banco
    stmt_order = select(Order).where(Order.external_order_id == "order_idempotency_unique_uuid")
    order = (await db_session.execute(stmt_order)).scalar_one_or_none()
    assert order is not None

    stmt_books = select(Book).where(Book.order_id == order.id)
    books = (await db_session.execute(stmt_books)).scalars().all()
    assert len(books) == 1


@pytest.mark.asyncio
async def test_cakto_webhook_credit_card_without_pix(client: httpx.AsyncClient, db_session: AsyncSession):
    """Testa compra aprovada por cartão de crédito sem objeto pix (opcional)."""
    cc_payload = {
        "secret": settings.CAKTO_WEBHOOK_SECRET,
        "event": "purchase_approved",
        "data": {
            "id": "order_cc_9999",
            "customer": {
                "name": "Rodrigo Silva",
                "email": "rodrigo@email.com",
            },
            "product": {
                "id": "d4c39c54-735b-416f-bbdf-47752679b492",
                "name": "Deus Conhece o Seu Nome",
            },
            "status": "paid",
            "amount": 59.90,
            "paymentMethod": "credit_card",
            "installments": 3,
            "pix": None,
        },
    }

    response = await client.post("/api/v1/webhooks/cakto/purchase-approved", json=cc_payload)
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"

    stmt_order = select(Order).where(Order.external_order_id == "order_cc_9999")
    order = (await db_session.execute(stmt_order)).scalar_one_or_none()
    assert order is not None
    assert order.status == OrderStatus.PAID


@pytest.mark.asyncio
async def test_cakto_credits_grant_consumption_and_repurchase_flow(
    client: httpx.AsyncClient, db_session: AsyncSession
):
    """
    Testa o ciclo completo de créditos:
    1. Compra aprovada na Cakto -> Comprador ganha 1 crédito.
    2. Consulta disponibilidade -> Retorna available=True, credits=1, can_generate=True.
    3. Geração do livro -> Consome 1 crédito, saldo fica 0.
    4. Consulta disponibilidade -> available=True (livro para download), credits=0, can_generate=False.
    5. Nova compra aprovada na Cakto -> Ganha +1 crédito (total=1), permitindo nova geração.
    """
    buyer_email = "ciclo.credito@gmail.com"

    # 1. Primeira compra aprovada
    compra1 = dict(CAKTO_PURCHASE_APPROVED_PAYLOAD)
    compra1["data"] = dict(CAKTO_PURCHASE_APPROVED_PAYLOAD["data"])
    compra1["data"]["id"] = "cakto_order_credit_001"
    compra1["data"]["customer"] = {
        "name": "Aline Costa",
        "email": buyer_email,
        "phone": "5511999998888",
    }

    res_c1 = await client.post("/api/v1/webhooks/cakto", json=compra1)
    assert res_c1.status_code == 200

    # Verifica saldo inicial de 1 crédito
    stmt_b = select(Buyer).where(Buyer.email_normalized == buyer_email)
    buyer = (await db_session.execute(stmt_b)).scalar_one()
    assert buyer.generation_credits == 1

    # 2. Consulta disponibilidade
    res_avail1 = await client.post("/api/v1/books/availability", json={"email": buyer_email})
    assert res_avail1.status_code == 200
    data_avail1 = res_avail1.json()
    assert data_avail1["available"] is True
    assert data_avail1["credits"] == 1
    assert data_avail1["can_generate"] is True

    # 3. Geração do livro
    from app.services.book_service import BookService
    stmt_book = select(Book).where(Book.buyer_id == buyer.id)
    book = (await db_session.execute(stmt_book)).scalar_one()
    await BookService.generate_book(db_session, book.id)

    await db_session.refresh(buyer)
    assert buyer.generation_credits == 0

    # 4. Consulta disponibilidade após geração (0 créditos restantes, mas livro pronto)
    res_avail2 = await client.post("/api/v1/books/availability", json={"email": buyer_email})
    assert res_avail2.status_code == 200
    data_avail2 = res_avail2.json()
    assert data_avail2["available"] is True
    assert data_avail2["credits"] == 0
    assert data_avail2["can_generate"] is False
    assert data_avail2["delivery_available"] is True

    # 5. Nova compra aprovada na Cakto (Recompra)
    compra2 = dict(CAKTO_PURCHASE_APPROVED_PAYLOAD)
    compra2["data"] = dict(CAKTO_PURCHASE_APPROVED_PAYLOAD["data"])
    compra2["data"]["id"] = "cakto_order_credit_002"
    compra2["data"]["customer"] = {
        "name": "Aline Costa",
        "email": buyer_email,
        "phone": "5511999998888",
    }

    res_c2 = await client.post("/api/v1/webhooks/cakto", json=compra2)
    assert res_c2.status_code == 200

    # Verifica que ganhou +1 crédito novamente
    await db_session.refresh(buyer)
    assert buyer.generation_credits == 1

    # 6. Consulta disponibilidade após recompra
    res_avail3 = await client.post("/api/v1/books/availability", json={"email": buyer_email})
    assert res_avail3.status_code == 200
    data_avail3 = res_avail3.json()
    assert data_avail3["available"] is True
    assert data_avail3["credits"] == 1
    assert data_avail3["can_generate"] is True

