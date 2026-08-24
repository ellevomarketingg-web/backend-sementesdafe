import os
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.deps import get_admin_user
from app.models.book import Book, BookStatus
from app.models.order import Order, OrderStatus
from app.schemas.book import (
    BookResponse,
    BookGenerateRequest,
    BookAvailabilityRequest,
    BookAvailabilityResponse,
    BookVerifyCodeRequest,
    BookVerifyCodeResponse,
)
from app.services.book_service import BookService
from app.workers.queue import job_queue
from app.workers.book_worker import process_book_generation_job
from app.core.security import verify_download_token, verify_admin_api_key
from app.core.logging import logger

router = APIRouter(prefix="/books", tags=["Books"])


@router.post("/generate", response_model=BookResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_book(
    payload: BookGenerateRequest,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_user),
):
    """
    Inicia o processamento assíncrono de geração de livro para um pedido pago (Apenas Admin / Webhook).
    """
    order = await db.get(Order, payload.order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido não encontrado.")

    if order.status != OrderStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas pedidos com status PAID podem ter livros gerados.",
        )

    # Cria ou busca o livro
    book = await BookService.create_book_for_order(
        session=db,
        order=order,
        child_name=payload.child_name or "",
    )

    # Enfileira processamento assíncrono
    await job_queue.enqueue(process_book_generation_job, book.id)

    return book


@router.get("", response_model=List[BookResponse])
async def list_books(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_user),
):
    """Lista todos os livros (Apenas Admin)."""
    stmt = select(Book).offset(skip).limit(limit).order_by(Book.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{book_id}", response_model=BookResponse)
async def get_book(
    book_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_user),
):
    """Obtém detalhes do livro por ID (Apenas Admin)."""
    book = await BookService.get_by_id(db, book_id)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Livro não encontrado.")
    return book


@router.post("/availability", response_model=BookAvailabilityResponse)
async def check_book_availability(
    payload: BookAvailabilityRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint público para verificação de disponibilidade de livro por e-mail.
    Não vaza dados sensíveis diretamente; dispara código 2FA de autorização.
    """
    return await BookService.check_availability(db, payload.email)


@router.post("/verify-code", response_model=BookVerifyCodeResponse)
async def verify_book_code(
    payload: BookVerifyCodeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Valida código de 6 dígitos recebido pelo comprador e libera o token temporário de download.
    """
    return await BookService.verify_code_and_issue_download(
        session=db,
        email_normalized=payload.email,
        code=payload.code,
    )


@router.get("/{book_id}/download")
async def download_book(
    book_id: str,
    token: Optional[str] = Query(None, description="Token temporário assinado de download"),
    x_admin_api_key: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Download seguro do arquivo PDF do livro.
    Exige token assinado válido ou credencial administrativa.
    """
    # 1. Validação de autorização
    is_admin = verify_admin_api_key(x_admin_api_key)
    valid_token = False

    if token:
        payload = verify_download_token(token)
        if payload and payload.get("sub") == book_id:
            valid_token = True

    if not is_admin and not valid_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Acesso não autorizado. Forneça um token de download válido ou autenticação administrativa.",
        )

    # 2. Localização e validação do livro
    book = await BookService.get_by_id(db, book_id)
    if not book:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Livro não encontrado.")

    if book.status not in (BookStatus.READY, BookStatus.DELIVERING, BookStatus.DELIVERED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"O livro ainda não está pronto para download. Status atual: {book.status}",
        )

    if not book.file_path or not os.path.exists(book.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo físico do livro não foi encontrado no servidor.",
        )

    filename = f"Deus_Conhece_o_Seu_Nome_{book.child_name or 'Personalizado'}.pdf".replace(" ", "_")

    return FileResponse(
        path=book.file_path,
        media_type="application/pdf",
        filename=filename,
    )
