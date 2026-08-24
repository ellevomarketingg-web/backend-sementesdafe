from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.api.deps import get_admin_user
from app.models.book_template import BookTemplate
from app.models.communication_template import CommunicationTemplate
from app.schemas.template import (
    BookTemplateCreate,
    BookTemplateResponse,
    CommunicationTemplateCreate,
    CommunicationTemplateResponse,
    TemplateValidationResult,
    CommunicationTemplatePreviewRequest,
    CommunicationTemplatePreviewResponse,
)
from app.services.template_service import TemplateService

router = APIRouter(prefix="/templates", tags=["Templates"])


# ================= Book Templates =================
@router.post("/books", response_model=BookTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_book_template(
    payload: BookTemplateCreate,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_user),
):
    """Cria nova versão de template de livro (Apenas Admin)."""
    return await TemplateService.create_book_template(db, payload)


@router.get("/books", response_model=List[BookTemplateResponse])
async def list_book_templates(
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_user),
):
    """Lista templates de livro cadastrados (Apenas Admin)."""
    stmt = select(BookTemplate).order_by(BookTemplate.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/books/{template_id}/publish", response_model=BookTemplateResponse)
async def publish_book_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_user),
):
    """Publica uma versão de template de livro tornando-a ativa (Apenas Admin)."""
    return await TemplateService.publish_book_template(db, template_id)


# ================= Communication Templates =================
@router.post("/messages", response_model=CommunicationTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_communication_template(
    payload: CommunicationTemplateCreate,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_user),
):
    """Cria nova versão de template de comunicação (Apenas Admin)."""
    return await TemplateService.create_communication_template(db, payload)


@router.get("/messages", response_model=List[CommunicationTemplateResponse])
async def list_communication_templates(
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_user),
):
    """Lista templates de mensagens de comunicação (Apenas Admin)."""
    stmt = select(CommunicationTemplate).order_by(CommunicationTemplate.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/messages/{template_id}/validate", response_model=TemplateValidationResult)
async def validate_communication_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_user),
):
    """Valida as variáveis utilizadas no conteúdo do template (Apenas Admin)."""
    template = await db.get(CommunicationTemplate, template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template não encontrado.")
    return TemplateService.validate_variables(template.content)


@router.post("/messages/{template_id}/publish", response_model=CommunicationTemplateResponse)
async def publish_communication_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_user),
):
    """Publica template de comunicação tornando-o ativo e imutável (Apenas Admin)."""
    return await TemplateService.publish_communication_template(db, template_id)


@router.post("/messages/{template_id}/preview", response_model=CommunicationTemplatePreviewResponse)
async def preview_communication_template(
    template_id: str,
    payload: CommunicationTemplatePreviewRequest,
    db: AsyncSession = Depends(get_db),
    _admin: str = Depends(get_admin_user),
):
    """Renderiza um preview do template com as variáveis informadas (Apenas Admin)."""
    template = await db.get(CommunicationTemplate, template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template não encontrado.")

    rendered = TemplateService.render(template.content, payload.variables)
    return CommunicationTemplatePreviewResponse(
        rendered_content=rendered,
        variables_used=payload.variables,
    )
