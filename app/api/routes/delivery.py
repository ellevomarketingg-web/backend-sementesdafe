import os
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.security import create_download_token
from app.core.logging import logger
from app.models.buyer import Buyer
from app.models.order import Order, OrderStatus
from app.models.book import Book, BookStatus
from app.models.order_bump import OrderBump, OrderBumpStatus
from app.services.book_service import BookService
from app.services.order_bump_service import OrderBumpService
from app.services.evolution_service import evolution_service

router = APIRouter(prefix="/delivery", tags=["Delivery"])


# --- Schemas ---
class CheckBookAccessRequest(BaseModel):
    email: str


class CreateBookDeliveryRequest(BaseModel):
    email: str
    nome_crianca: str
    genero: str = Field("M", description="'M' para Menino ou 'F' para Menina")


class SendBookWhatsAppRequest(BaseModel):
    book_id: str
    telefone: str
    email: Optional[str] = None


class CheckOrderBumpAccessRequest(BaseModel):
    email: str
    product_type: str = Field(..., description="'calendario' ou 'figurinhas'")


class SendOrderBumpWhatsAppRequest(BaseModel):
    email: str
    telefone: str
    product_type: str = Field(..., description="'calendario' ou 'figurinhas'")


# --- Endpoints ---

@router.post("/check-book-access")
async def check_book_access(
    payload: CheckBookAccessRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Verifica se o comprador tem acesso ao livro personalizado e seu status de criação.
    """
    email_norm = payload.email.strip().lower()
    stmt = select(Buyer).where(Buyer.email_normalized == email_norm)
    buyer = (await db.execute(stmt)).scalar_one_or_none()

    if not buyer:
        return {
            "status": "no_purchase",
            "has_access": False,
            "message": "Nenhuma compra confirmada encontrada para este e-mail.",
        }

    # Verifica pedidos pagos
    stmt_orders = select(Order).where(Order.buyer_id == buyer.id, Order.status == OrderStatus.PAID)
    paid_orders = list((await db.execute(stmt_orders)).scalars().all())

    if not paid_orders:
        return {
            "status": "no_purchase",
            "has_access": False,
            "message": "Nenhum pedido com pagamento confirmado para este e-mail.",
        }

    # Verifica livros já gerados ou em processo
    stmt_books = select(Book).where(Book.buyer_id == buyer.id).order_by(Book.created_at.desc())
    books = list((await db.execute(stmt_books)).scalars().all())
    ready_books = [b for b in books if b.status in (BookStatus.READY, BookStatus.DELIVERED)]

    # Se o usuário já gerou seu livro e não tem mais créditos para gerar outro
    if ready_books and buyer.generation_credits == 0:
        target_book = ready_books[0]
        token = create_download_token(book_id=target_book.id, email=email_norm)
        download_url = f"{settings.DOWNLOAD_URL_BASE}/{target_book.id}/download?token={token}"
        return {
            "status": "already_generated",
            "has_access": True,
            "buyer_name": buyer.name,
            "book": {
                "id": target_book.id,
                "child_name": target_book.child_name,
                "download_url": download_url,
                "created_at": target_book.created_at.isoformat() if target_book.created_at else None,
            },
            "credits": 0,
            "can_generate": False,
        }

    # Se tem créditos para gerar (ou compra nova)
    if buyer.generation_credits > 0 or not ready_books:
        return {
            "status": "can_generate",
            "has_access": True,
            "buyer_name": buyer.name,
            "credits": buyer.generation_credits if buyer.generation_credits > 0 else 1,
            "can_generate": True,
            "ready_books": [
                {
                    "id": b.id,
                    "child_name": b.child_name,
                    "download_url": f"{settings.DOWNLOAD_URL_BASE}/{b.id}/download?token={create_download_token(book_id=b.id, email=email_norm)}",
                }
                for b in ready_books
            ],
        }

    return {
        "status": "no_purchase",
        "has_access": False,
        "message": "Nenhum crédito disponível.",
    }


@router.post("/create-book")
async def create_book_delivery(
    payload: CreateBookDeliveryRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Recebe nome da criança e gênero/template, gera o livro em PDF imediatamente
    e retorna o link para download.
    """
    email_norm = payload.email.strip().lower()
    stmt = select(Buyer).where(Buyer.email_normalized == email_norm)
    buyer = (await db.execute(stmt)).scalar_one_or_none()

    if not buyer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comprador não encontrado com este e-mail.",
        )

    # Busca pedido pago
    stmt_orders = select(Order).where(Order.buyer_id == buyer.id, Order.status == OrderStatus.PAID).order_by(Order.created_at.desc())
    paid_orders = list((await db.execute(stmt_orders)).scalars().all())
    if not paid_orders:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum pedido pago disponível para gerar o livro.",
        )

    # Verifica se há créditos ou livro pendente
    if buyer.generation_credits <= 0:
        # Checa se há livro já criado para este pedido que ainda esteja pendente
        stmt_pending = select(Book).where(Book.buyer_id == buyer.id, Book.status == BookStatus.PENDING)
        pending_book = (await db.execute(stmt_pending)).scalar_one_or_none()
        if not pending_book:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Você não possui mais créditos de geração. Adquira um novo livro para continuar.",
            )

    selected_order = paid_orders[0]

    # Atualiza metadados do pedido com gênero/variante
    gender_clean = payload.genero.strip().upper()
    variant_name = "menina" if gender_clean in ("F", "MENINA", "GIRL") else "menino"
    if not selected_order.metadata_info:
        selected_order.metadata_info = {}
    
    # Faz cópia do dict para garantir persistência no SQLAlchemy
    meta = dict(selected_order.metadata_info)
    meta["gender"] = variant_name
    meta["variant"] = variant_name
    meta["child_name"] = payload.nome_crianca.strip()
    selected_order.metadata_info = meta
    await db.commit()

    # Cria ou obtém entidade Book
    child_name_clean = payload.nome_crianca.strip()
    book = await BookService.create_book_for_order(
        session=db,
        order=selected_order,
        child_name=child_name_clean,
    )
    book.child_name = child_name_clean
    await db.commit()

    # Gera o PDF de forma síncrona
    book = await BookService.generate_book(
        session=db,
        book_id=book.id,
        force=True,
    )

    # Emite token de download
    token = create_download_token(book_id=book.id, email=email_norm)
    download_url = f"{settings.DOWNLOAD_URL_BASE}/{book.id}/download?token={token}"

    return {
        "status": "ok",
        "book": {
            "id": book.id,
            "nome_crianca": book.child_name,
            "download_url": download_url,
            "credits_remaining": buyer.generation_credits,
            "pode_gerar_outro": buyer.generation_credits > 0,
        },
    }


@router.post("/send-book-whatsapp")
async def send_book_whatsapp(
    payload: SendBookWhatsAppRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Envia o PDF do livro personalizado diretamente para o WhatsApp do comprador.
    """
    book = await db.get(Book, payload.book_id)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Livro não encontrado.")

    if not book.file_path or not os.path.exists(book.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo do livro não encontrado no servidor. Gere o livro antes de enviar.",
        )

    phone = payload.telefone.strip()
    child_name = book.child_name or "sua criança"

    # 1. Mensagem receptiva
    receptive_msg = (
        f"Olá! ❤️ Aqui está o livro personalizado de *{child_name}* — Deus Conhece o Seu Nome! ✨\n\n"
        f"Esperamos que esta história fortaleça os laços de fé e amor na sua casa! Que Deus abençoe sua família! 🙏📖"
    )
    await evolution_service.send_text(phone=phone, message=receptive_msg)

    # 2. Envio do PDF oficial gerado
    filename = f"Deus_Conhece_o_Seu_Nome_{child_name}.pdf".replace(" ", "_")
    doc_res = await evolution_service.send_document(
        phone=phone,
        document_url_or_base64=book.file_path,
        filename=filename,
        caption=f"📖 Livro Personalizado de {child_name}",
    )

    return {
        "status": "ok",
        "message": "Livro enviado com sucesso pelo WhatsApp!",
        "details": doc_res,
    }


@router.post("/check-order-bump-access")
async def check_order_bump_access(
    payload: CheckOrderBumpAccessRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Verifica se o e-mail possui acesso aos Order Bumps (Calendário ou Figurinhas).
    """
    email_norm = payload.email.strip().lower()
    stmt = select(Buyer).where(Buyer.email_normalized == email_norm)
    buyer = (await db.execute(stmt)).scalar_one_or_none()

    if not buyer:
        return {
            "status": "no_access",
            "has_access": False,
            "message": "Nenhum registro de compra encontrado para este e-mail.",
        }

    buyer_bumps = await OrderBumpService.get_buyer_order_bumps(db, buyer.id)
    product_type = payload.product_type.strip().lower()

    if product_type == "calendario":
        # Checa por ID ou por código do produto
        has_cal = any(
            ob.product_id == settings.CAKTO_ORDER_BUMP_CALENDAR_ID
            or ob.product_code == "CHRISTIAN_CALENDAR"
            or "calendario" in (ob.product_name or "").lower()
            for ob in buyer_bumps
        )
        if not has_cal:
            return {
                "status": "no_access",
                "has_access": False,
                "message": "Você ainda não possui acesso ao Calendário Cristão Infantil.",
            }

        token = create_download_token(book_id=settings.CAKTO_ORDER_BUMP_CALENDAR_ID, email=email_norm)
        return {
            "status": "ok",
            "has_access": True,
            "product_type": "calendario",
            "product_name": "Calendário Cristão Infantil — Datas Especiais com Deus",
            "download_url": f"{settings.ORDER_BUMP_DOWNLOAD_URL_BASE}/download-by-product/{settings.CAKTO_ORDER_BUMP_CALENDAR_ID}?token={token}",
        }

    elif product_type == "figurinhas":
        has_stickers = any(
            ob.product_id == settings.CAKTO_ORDER_BUMP_STICKERS_ID
            or ob.product_code == "STICKERS_PACK"
            or "figurinhas" in (ob.product_name or "").lower()
            for ob in buyer_bumps
        )
        if not has_stickers:
            return {
                "status": "no_access",
                "has_access": False,
                "message": "Você ainda não possui acesso ao Pack de Figurinhas Cristãs.",
            }

        return {
            "status": "ok",
            "has_access": True,
            "product_type": "figurinhas",
            "product_name": "Pack de Figurinhas Cristãs para WhatsApp",
            "sticker_links": [
                "https://sticker.ly/s/PBUUGL",
                "https://sticker.ly/s/VXE7UB",
                "https://sticker.ly/s/BE9L1J",
                "https://sticker.ly/s/OS5AOB",
            ],
        }

    return {
        "status": "invalid_product",
        "has_access": False,
        "message": f"Tipo de produto '{payload.product_type}' inválido.",
    }


@router.post("/send-order-bump-whatsapp")
async def send_order_bump_whatsapp(
    payload: SendOrderBumpWhatsAppRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Envia o conteúdo do Order Bump via WhatsApp (Calendário ou Figurinhas).
    """
    email_norm = payload.email.strip().lower()
    stmt = select(Buyer).where(Buyer.email_normalized == email_norm)
    buyer = (await db.execute(stmt)).scalar_one_or_none()

    if not buyer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comprador não encontrado com este e-mail.",
        )

    product_type = payload.product_type.strip().lower()
    phone = payload.telefone.strip()

    if product_type == "calendario":
        # Garante ou localiza o arquivo do calendário
        file_path = OrderBumpService.get_or_create_asset_file(settings.CAKTO_ORDER_BUMP_CALENDAR_ID)
        
        # 1. Mensagem receptiva
        receptive_msg = (
            "Olá! ❤️ Aqui está o seu *Calendário Cristão Infantil — Datas Especiais com Deus*! 🎄✨\n\n"
            "Que cada mês traga momentos preciosos de conexão e fé para sua família! 🙏"
        )
        await evolution_service.send_text(phone=phone, message=receptive_msg)

        # 2. Envio do PDF do Calendário
        doc_res = await evolution_service.send_document(
            phone=phone,
            document_url_or_base64=file_path,
            filename="Calendario_Cristao_Infantil.pdf",
            caption="🎄 Calendário Cristão Infantil",
        )
        return {
            "status": "ok",
            "message": "Calendário enviado com sucesso por WhatsApp!",
            "details": doc_res,
        }

    elif product_type == "figurinhas":
        # 1. Mensagem receptiva
        receptive_msg = (
            "Olá! ❤️ Que bom ter você aqui! Vamos te enviar o seu exclusivo *Pack de Figurinhas Cristãs para WhatsApp*! ✨"
        )
        await evolution_service.send_text(phone=phone, message=receptive_msg)

        # 2. Mensagem exata de instrução
        trigger_msg = 'Responda com "OK" para eu te enviar o pack de figurinhas.'
        await evolution_service.send_text(phone=phone, message=trigger_msg)

        return {
            "status": "ok",
            "message": "Instruções enviadas com sucesso por WhatsApp!",
        }

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Tipo de produto '{payload.product_type}' inválido.",
    )
