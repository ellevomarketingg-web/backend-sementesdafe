import os
import pytest
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.buyer import Buyer
from app.models.order import Order, OrderStatus
from app.models.book import Book, BookStatus
from app.models.verification_code import VerificationCode
from app.services.book_generator import BookGenerator
from app.services.book_service import BookService
from app.core.security import create_download_token


def test_book_pdf_generation_and_header_validation(tmp_path):
    output_pdf = str(tmp_path / "test_book.pdf")
    success = BookGenerator.generate_book_pdf(
        output_path=output_pdf,
        child_name="Samuel",
        buyer_name="Patrícia",
    )
    assert success is True
    assert os.path.exists(output_pdf)
    assert os.path.getsize(output_pdf) > 0
    with open(output_pdf, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-"


def test_book_pdf_generation_boy_and_girl_templates(tmp_path):
    # 1. Menino com nome padrão
    out_menino = str(tmp_path / "menino_samuel.pdf")
    success_m = BookGenerator.generate_book_pdf(
        output_path=out_menino,
        child_name="SAMUEL",
        gender_or_variant="menino",
    )
    assert success_m is True
    assert os.path.exists(out_menino)

    # 2. Menina com nome composto
    out_menina = str(tmp_path / "menina_maria_eduarda.pdf")
    success_f = BookGenerator.generate_book_pdf(
        output_path=out_menina,
        child_name="MARIA EDUARDA",
        gender_or_variant="menina",
    )
    assert success_f is True
    assert os.path.exists(out_menina)

    # 3. Validação de integridade sem perda de texto
    template_menino = BookGenerator.get_template_path("menino")
    template_menina = BookGenerator.get_template_path("menina")

    suspeitas_m = BookGenerator.validar_integridade(template_menino, out_menino, "SAMUEL")
    assert len(suspeitas_m) == 0

    suspeitas_f = BookGenerator.validar_integridade(template_menina, out_menina, "MARIA EDUARDA")
    assert len(suspeitas_f) == 0


def test_book_pdf_generation_patrick_variations(tmp_path):
    template_menino = BookGenerator.get_template_path("menino")
    
    # 1. Menino com nome PATRICK (uppercase)
    out_upper = str(tmp_path / "menino_PATRICK.pdf")
    success_upper = BookGenerator.generate_book_pdf(
        output_path=out_upper,
        child_name="PATRICK",
        gender_or_variant="menino",
    )
    assert success_upper is True
    assert os.path.exists(out_upper)
    suspeitas_upper = BookGenerator.validar_integridade(template_menino, out_upper, "PATRICK")
    assert len(suspeitas_upper) == 0

    # 2. Menino com nome Patrick (titlecase)
    out_title = str(tmp_path / "menino_Patrick.pdf")
    success_title = BookGenerator.generate_book_pdf(
        output_path=out_title,
        child_name="Patrick",
        gender_or_variant="menino",
    )
    assert success_title is True
    assert os.path.exists(out_title)
    suspeitas_title = BookGenerator.validar_integridade(template_menino, out_title, "Patrick")
    assert len(suspeitas_title) == 0


@pytest.mark.asyncio
async def test_book_availability_and_secure_download_flow(client: httpx.AsyncClient, db_session: AsyncSession, admin_headers: dict):
    # 1. Cria comprador e pedido PAID
    buyer = Buyer(
        email="cliente.valido@exemplo.com",
        email_normalized="cliente.valido@exemplo.com",
        name="Patrícia Lima",
        phone="5511988887777",
    )
    db_session.add(buyer)
    await db_session.commit()
    await db_session.refresh(buyer)

    order = Order(
        external_order_id="ext_order_patricia_100",
        buyer_id=buyer.id,
        status=OrderStatus.PAID,
        amount=49.90,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    # 2. Cria e gera o livro
    book = await BookService.create_book_for_order(db_session, order, child_name="Samuel")
    book = await BookService.generate_book(db_session, book.id)
    assert book.status == BookStatus.READY
    assert os.path.exists(book.file_path)

    # 3. Consulta disponibilidade pública por e-mail
    avail_res = await client.post("/api/v1/books/availability", json={"email": "CLIENTE.VALIDO@EXEMPLO.COM"})
    assert avail_res.status_code == 200
    avail_data = avail_res.json()
    assert avail_data["available"] is True
    assert avail_data["requires_verification"] is True
    assert avail_data["delivery_available"] is True

    # 4. Obtém o código 2FA gerado no banco para o teste
    stmt_code = select(VerificationCode).where(VerificationCode.email_normalized == "cliente.valido@exemplo.com")
    verif = (await db_session.execute(stmt_code)).scalar_one_or_none()
    assert verif is not None
    code_generated = verif.code

    # 5. Valida o código 2FA
    verify_res = await client.post(
        "/api/v1/books/verify-code",
        json={"email": "cliente.valido@exemplo.com", "code": code_generated},
    )
    assert verify_res.status_code == 200
    verify_data = verify_res.json()
    assert verify_data["success"] is True
    download_token = verify_data["download_token"]
    assert download_token is not None

    # 6. Tenta download sem token -> Deve dar 401 Unauthorized
    unauth_download = await client.get(f"/api/v1/books/{book.id}/download")
    assert unauth_download.status_code == 401

    # 7. Download com token válido -> Deve retornar 200 OK com cabeçalho PDF
    auth_download = await client.get(f"/api/v1/books/{book.id}/download?token={download_token}")
    assert auth_download.status_code == 200
    assert auth_download.headers["content-type"] == "application/pdf"
    assert len(auth_download.content) > 0
    assert auth_download.content.startswith(b"%PDF-")

    # 8. Download com header administrativo -> Deve permitir também
    admin_download = await client.get(f"/api/v1/books/{book.id}/download", headers=admin_headers)
    assert admin_download.status_code == 200
    assert admin_download.headers["content-type"] == "application/pdf"
