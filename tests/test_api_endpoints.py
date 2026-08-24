import pytest
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.buyer import Buyer
from app.models.order import Order, OrderStatus
from app.models.book import Book, BookStatus
from app.services.book_service import BookService


@pytest.mark.asyncio
async def test_admin_buyers_and_orders_endpoints(client: httpx.AsyncClient, db_session: AsyncSession, admin_headers: dict):
    # 1. Cria comprador direto
    buyer = Buyer(
        email="marcos@email.com",
        email_normalized="marcos@email.com",
        name="Marcos Souza",
        phone="5511911112222",
    )
    db_session.add(buyer)
    await db_session.commit()
    await db_session.refresh(buyer)

    # 2. List Buyers (Admin)
    res_buyers = await client.get("/api/v1/buyers", headers=admin_headers)
    assert res_buyers.status_code == 200
    assert len(res_buyers.json()) >= 1

    # 3. Get Buyer by ID
    res_buyer = await client.get(f"/api/v1/buyers/{buyer.id}", headers=admin_headers)
    assert res_buyer.status_code == 200
    assert res_buyer.json()["email_normalized"] == "marcos@email.com"

    # 4. Create Order (Admin)
    order_payload = {
        "external_order_id": "ext_admin_order_123",
        "buyer_id": buyer.id,
        "amount": 59.90,
        "status": "PAID",
        "metadata_info": {"child_name": "Daniel"},
    }
    res_create_order = await client.post("/api/v1/orders", json=order_payload, headers=admin_headers)
    assert res_create_order.status_code == 201
    created_order = res_create_order.json()
    assert created_order["status"] == "PAID"

    # 5. List Orders (Admin)
    res_orders = await client.get("/api/v1/orders", headers=admin_headers)
    assert res_orders.status_code == 200
    assert len(res_orders.json()) >= 1

    # 6. Get Order by ID
    res_get_order = await client.get(f"/api/v1/orders/{created_order['id']}", headers=admin_headers)
    assert res_get_order.status_code == 200


@pytest.mark.asyncio
async def test_book_templates_routes(client: httpx.AsyncClient, admin_headers: dict):
    # 1. Create Book Template
    payload = {
        "name": "deus-conhece-seu-nome-v2",
        "version": 1,
        "template_data": {
            "title": "Deus Conhece o Seu Nome",
            "theme": "pastoral",
        },
    }
    res_create = await client.post("/api/v1/templates/books", json=payload, headers=admin_headers)
    assert res_create.status_code == 201
    tmpl_data = res_create.json()
    assert tmpl_data["status"] == "DRAFT"

    # 2. List Book Templates
    res_list = await client.get("/api/v1/templates/books", headers=admin_headers)
    assert res_list.status_code == 200
    assert len(res_list.json()) >= 1

    # 3. Publish Book Template
    res_publish = await client.post(f"/api/v1/templates/books/{tmpl_data['id']}/publish", headers=admin_headers)
    assert res_publish.status_code == 200
    assert res_publish.json()["status"] == "PUBLISHED"


@pytest.mark.asyncio
async def test_manual_generate_book_and_list_books(client: httpx.AsyncClient, db_session: AsyncSession, admin_headers: dict):
    buyer = Buyer(
        email="lucia@email.com",
        email_normalized="lucia@email.com",
        name="Lucia Ferreira",
        phone="5511944443333",
    )
    db_session.add(buyer)
    await db_session.commit()
    await db_session.refresh(buyer)

    order = Order(
        external_order_id="ext_order_lucia_99",
        buyer_id=buyer.id,
        status=OrderStatus.PAID,
        amount=49.90,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    # Manual generate endpoint (Admin)
    gen_payload = {
        "order_id": order.id,
        "child_name": "Helena",
    }
    res_gen = await client.post("/api/v1/books/generate", json=gen_payload, headers=admin_headers)
    assert res_gen.status_code == 202
    book_data = res_gen.json()
    assert book_data["child_name"] == "Helena"

    # List books (Admin)
    res_books = await client.get("/api/v1/books", headers=admin_headers)
    assert res_books.status_code == 200
    assert len(res_books.json()) >= 1

    # Get single book
    res_book = await client.get(f"/api/v1/books/{book_data['id']}", headers=admin_headers)
    assert res_book.status_code == 200


@pytest.mark.asyncio
async def test_availability_not_found_and_not_paid(client: httpx.AsyncClient, db_session: AsyncSession):
    # 1. Email desconhecido
    res_not_found = await client.post("/api/v1/books/availability", json={"email": "naoexiste@email.com"})
    assert res_not_found.status_code == 200
    data_not_found = res_not_found.json()
    assert data_not_found["available"] is False
    assert data_not_found["reason"] == "BUYER_NOT_FOUND"

    # 2. Comprador com pedido PENDING (não pago)
    buyer = Buyer(
        email="pendente@email.com",
        email_normalized="pendente@email.com",
        name="Pedro Pendente",
    )
    db_session.add(buyer)
    await db_session.commit()
    await db_session.refresh(buyer)

    order = Order(
        external_order_id="order_pending_1",
        buyer_id=buyer.id,
        status=OrderStatus.PENDING,
        amount=49.90,
    )
    db_session.add(order)
    await db_session.commit()

    res_not_paid = await client.post("/api/v1/books/availability", json={"email": "pendente@email.com"})
    assert res_not_paid.status_code == 200
    data_not_paid = res_not_paid.json()
    assert data_not_paid["available"] is False
    assert data_not_paid["reason"] == "ORDER_NOT_PAID"
