import os
import pytest
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.buyer import Buyer
from app.models.order import Order, OrderStatus
from app.models.order_bump import OrderBump, OrderBumpStatus
from app.models.verification_code import VerificationCode
from app.core.config import settings
from app.services.order_bump_service import OrderBumpService


@pytest.mark.asyncio
async def test_order_bumps_catalog_endpoint(client: httpx.AsyncClient):
    """Testa que o catálogo de order bumps retorna os 2 itens oficiais configurados."""
    response = await client.get("/api/v1/order-bumps/catalog")
    assert response.status_code == 200
    catalog = response.json()
    assert len(catalog) == 2

    ids = [item["id"] for item in catalog]
    assert settings.CAKTO_ORDER_BUMP_STICKERS_ID in ids
    assert settings.CAKTO_ORDER_BUMP_CALENDAR_ID in ids

    stickers = next(item for item in catalog if item["id"] == settings.CAKTO_ORDER_BUMP_STICKERS_ID)
    assert stickers["name"] == "💬 Pack de Figurinhas Cristãs para WhatsApp"
    assert stickers["code"] == "STICKERS_PACK"

    calendar = next(item for item in catalog if item["id"] == settings.CAKTO_ORDER_BUMP_CALENDAR_ID)
    assert calendar["name"] == "🎄 Calendário Cristão Infantil — Datas Especiais com Deus"
    assert calendar["code"] == "CHRISTIAN_CALENDAR"


@pytest.mark.asyncio
async def test_cakto_webhook_with_embedded_order_bumps(client: httpx.AsyncClient, db_session: AsyncSession):
    """
    Testa compra aprovada na Cakto com o produto principal + 2 order bumps embutidos.
    Deve conceder 1 crédito de livro + 2 registros de OrderBump desbloqueados.
    """
    buyer_email = "comprador.completo@gmail.com"
    payload = {
        "secret": settings.CAKTO_WEBHOOK_SECRET,
        "event": "purchase_approved",
        "data": {
            "id": "cakto_order_with_bumps_1001",
            "customer": {
                "name": "Renata Vasconcelos",
                "email": buyer_email,
                "phone": "5511977776666",
            },
            "product": {
                "id": settings.CAKTO_PRODUCT_ID,
                "name": "Deus Conhece o Seu Nome",
            },
            "status": "paid",
            "amount": 79.70,
            "order_bumps": [
                {
                    "product": {
                        "id": settings.CAKTO_ORDER_BUMP_STICKERS_ID,
                        "name": "💬 Pack de Figurinhas Cristãs para WhatsApp",
                    },
                    "amount": 14.90,
                },
                {
                    "product": {
                        "id": settings.CAKTO_ORDER_BUMP_CALENDAR_ID,
                        "name": "🎄 Calendário Cristão Infantil — Datas Especiais com Deus",
                    },
                    "amount": 14.90,
                },
            ],
            "paidAt": "2026-08-24T18:00:00-03:00",
        },
    }

    # 1. Envia webhook
    res = await client.post("/api/v1/webhooks/cakto", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "accepted"

    # 2. Verifica Comprador e Crédito de Livro
    stmt_buyer = select(Buyer).where(Buyer.email_normalized == buyer_email)
    buyer = (await db_session.execute(stmt_buyer)).scalar_one_or_none()
    assert buyer is not None
    assert buyer.generation_credits == 1

    # 3. Verifica OrderBumps persistidos no banco
    stmt_bumps = select(OrderBump).where(OrderBump.buyer_id == buyer.id)
    bumps = (await db_session.execute(stmt_bumps)).scalars().all()
    assert len(bumps) == 2
    bump_pids = {b.product_id for b in bumps}
    assert settings.CAKTO_ORDER_BUMP_STICKERS_ID in bump_pids
    assert settings.CAKTO_ORDER_BUMP_CALENDAR_ID in bump_pids

    # 4. Front-End consulta disponibilidade geral (via /books/availability)
    res_avail = await client.post("/api/v1/books/availability", json={"email": buyer_email})
    assert res_avail.status_code == 200
    data_avail = res_avail.json()
    assert data_avail["available"] is True
    assert data_avail["credits"] == 1
    assert len(data_avail["order_bumps"]) == 2

    # 5. Front-End consulta disponibilidade específica de order bumps (via /order-bumps/availability)
    res_ob_avail = await client.post("/api/v1/order-bumps/availability", json={"email": buyer_email})
    assert res_ob_avail.status_code == 200
    data_ob_avail = res_ob_avail.json()
    assert data_ob_avail["has_access"] is True
    assert len(data_ob_avail["order_bumps"]) == 2

    # 6. Validação com código 2FA e liberação de download
    stmt_code = select(VerificationCode).where(VerificationCode.email_normalized == buyer_email)
    verif = (await db_session.execute(stmt_code)).scalars().first()
    assert verif is not None

    res_verify = await client.post(
        "/api/v1/order-bumps/verify-code",
        json={"email": buyer_email, "code": verif.code},
    )
    assert res_verify.status_code == 200
    data_verify = res_verify.json()
    assert data_verify["success"] is True
    assert len(data_verify["order_bumps"]) == 2

    # 7. Download do Order Bump com token assinado
    stickers_item = next(b for b in data_verify["order_bumps"] if b["product_id"] == settings.CAKTO_ORDER_BUMP_STICKERS_ID)
    dl_res = await client.get(f"/api/v1/order-bumps/download-by-product/{settings.CAKTO_ORDER_BUMP_STICKERS_ID}?token={stickers_item['download_token']}")
    assert dl_res.status_code == 200
    assert len(dl_res.content) > 0


@pytest.mark.asyncio
async def test_cakto_webhook_individual_order_bump_purchase(client: httpx.AsyncClient, db_session: AsyncSession):
    """
    Testa compra aprovada na Cakto contendo apenas um Order Bump como produto principal da transação.
    """
    buyer_email = "comprador.so_figurinha@gmail.com"
    payload = {
        "secret": settings.CAKTO_WEBHOOK_SECRET,
        "event": "purchase_approved",
        "data": {
            "id": "cakto_order_only_bump_2002",
            "customer": {
                "name": "Lucas Gabriel",
                "email": buyer_email,
                "phone": "5511966665555",
            },
            "product": {
                "id": settings.CAKTO_ORDER_BUMP_STICKERS_ID,
                "name": "💬 Pack de Figurinhas Cristãs para WhatsApp",
            },
            "status": "paid",
            "amount": 14.90,
            "paidAt": "2026-08-24T18:00:00-03:00",
        },
    }

    # 1. Processa webhook
    res = await client.post("/api/v1/webhooks/cakto", json=payload)
    assert res.status_code == 200
    assert res.json()["status"] == "accepted"

    # 2. Comprador criado sem créditos de livro (já que não comprou o livro), mas com o order bump
    stmt_buyer = select(Buyer).where(Buyer.email_normalized == buyer_email)
    buyer = (await db_session.execute(stmt_buyer)).scalar_one_or_none()
    assert buyer is not None
    assert buyer.generation_credits == 0

    stmt_bumps = select(OrderBump).where(OrderBump.buyer_id == buyer.id)
    bumps = (await db_session.execute(stmt_bumps)).scalars().all()
    assert len(bumps) == 1
    assert bumps[0].product_id == settings.CAKTO_ORDER_BUMP_STICKERS_ID

    # 3. Consulta de disponibilidade via /order-bumps/availability com product_id específico
    res_avail = await client.post(
        "/api/v1/order-bumps/availability",
        json={"email": buyer_email, "product_id": settings.CAKTO_ORDER_BUMP_STICKERS_ID},
    )
    assert res_avail.status_code == 200
    assert res_avail.json()["has_access"] is True

    # 4. Consulta de disponibilidade para produto não adquirido -> has_access = False
    res_not_bought = await client.post(
        "/api/v1/order-bumps/availability",
        json={"email": buyer_email, "product_id": settings.CAKTO_ORDER_BUMP_CALENDAR_ID},
    )
    assert res_not_bought.status_code == 200
    assert res_not_bought.json()["has_access"] is False


@pytest.mark.asyncio
async def test_order_bump_download_security(client: httpx.AsyncClient, db_session: AsyncSession, admin_headers: dict):
    """
    Testa segurança de download de Order Bump:
    - Sem token -> 401 Unauthorized
    - Token inválido -> 401 Unauthorized
    - Com Header de Admin -> 200 OK
    """
    prod_id = settings.CAKTO_ORDER_BUMP_CALENDAR_ID

    # 1. Download sem token
    unauth = await client.get(f"/api/v1/order-bumps/download-by-product/{prod_id}")
    assert unauth.status_code == 401

    # 2. Download com token inválido
    bad_token = await client.get(f"/api/v1/order-bumps/download-by-product/{prod_id}?token=invalid.jwt.token")
    assert bad_token.status_code == 401

    # 3. Download com Admin Header
    admin_dl = await client.get(f"/api/v1/order-bumps/download-by-product/{prod_id}", headers=admin_headers)
    assert admin_dl.status_code == 200
    assert admin_dl.headers["content-type"] == "application/pdf"
