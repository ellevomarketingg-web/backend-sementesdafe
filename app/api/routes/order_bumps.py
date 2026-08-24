import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.security import verify_download_token, verify_admin_api_key
from app.core.logging import logger
from app.models.order_bump import OrderBump, OrderBumpStatus
from app.schemas.order_bump import (
    OrderBumpCatalogItem,
    OrderBumpAvailabilityRequest,
    OrderBumpAvailabilityResponse,
    OrderBumpVerifyRequest,
    OrderBumpVerifyResponse,
    OrderBumpItemResponse,
)
from app.services.order_bump_service import OrderBumpService

router = APIRouter(prefix="/order-bumps", tags=["Order Bumps"])


@router.get("/catalog", response_model=List[OrderBumpCatalogItem])
async def get_order_bumps_catalog():
    """
    Retorna o catálogo público com todos os Order Bumps oficiais disponíveis.
    Útil para o Front-End exibir informações, títulos e descrições das ofertas.
    """
    return OrderBumpService.get_catalog()


@router.post("/availability", response_model=OrderBumpAvailabilityResponse)
async def check_order_bumps_availability(
    payload: OrderBumpAvailabilityRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Verifica se o comprador possui Order Bumps liberados para o e-mail informado.
    Dispara código de verificação 2FA (WhatsApp/Email) para liberação de download seguro.
    """
    return await OrderBumpService.check_availability(
        session=db,
        email_normalized=payload.email,
        product_id=payload.product_id,
    )


@router.post("/verify-code", response_model=OrderBumpVerifyResponse)
async def verify_order_bumps_code(
    payload: OrderBumpVerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Valida o código de segurança (2FA) e emite tokens e URLs assinadas para download dos Order Bumps.
    """
    return await OrderBumpService.verify_code_and_issue_download(
        session=db,
        email_normalized=payload.email,
        code=payload.code,
        product_id=payload.product_id,
    )


@router.get("/download-by-product/{product_id}")
async def download_order_bump_by_product_id(
    product_id: str,
    token: Optional[str] = Query(None, description="Token temporário assinado de download"),
    x_admin_api_key: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Download seguro do arquivo do Order Bump pelo ID do produto da Cakto.
    Exige token assinado válido ou credencial administrativa.
    """
    # 1. Validação de Autorização
    is_admin = verify_admin_api_key(x_admin_api_key)
    valid_token = False

    if token:
        payload = verify_download_token(token)
        if payload and (payload.get("sub") == product_id or payload.get("email")):
            valid_token = True

    if not is_admin and not valid_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Acesso não autorizado. Forneça um token de download válido ou autenticação administrativa.",
        )

    # 2. Localização do arquivo do Order Bump
    catalog_info = OrderBumpService.get_catalog_item(product_id)
    file_path = OrderBumpService.get_or_create_asset_file(product_id)

    if not file_path or not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo do Order Bump não encontrado no servidor.",
        )

    filename = catalog_info["filename"] if catalog_info else f"order_bump_{product_id}.zip"
    content_type = catalog_info["content_type"] if catalog_info else "application/octet-stream"

    return FileResponse(
        path=file_path,
        media_type=content_type,
        filename=filename,
    )


@router.get("/{order_bump_id}/download")
async def download_order_bump_by_id(
    order_bump_id: str,
    token: Optional[str] = Query(None, description="Token temporário assinado de download"),
    x_admin_api_key: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Download seguro do arquivo do Order Bump pelo ID da entidade interna OrderBump.
    Exige token assinado válido ou credencial administrativa.
    """
    order_bump = await db.get(OrderBump, order_bump_id)
    if not order_bump:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order Bump não encontrado.")

    is_admin = verify_admin_api_key(x_admin_api_key)
    valid_token = False

    if token:
        payload = verify_download_token(token)
        if payload and (payload.get("sub") == order_bump.product_id or payload.get("sub") == order_bump.id or payload.get("email")):
            valid_token = True

    if not is_admin and not valid_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Acesso não autorizado. Forneça um token de download válido ou autenticação administrativa.",
        )

    file_path = order_bump.file_path or OrderBumpService.get_or_create_asset_file(order_bump.product_id)
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Arquivo físico do Order Bump não encontrado no servidor.",
        )

    catalog_info = OrderBumpService.get_catalog_item(order_bump.product_id)
    filename = catalog_info["filename"] if catalog_info else f"order_bump_{order_bump.product_id}.zip"
    content_type = catalog_info["content_type"] if catalog_info else "application/octet-stream"

    # Incrementa contador de downloads
    order_bump.download_count += 1
    order_bump.status = OrderBumpStatus.DOWNLOADED
    await db.commit()

    return FileResponse(
        path=file_path,
        media_type=content_type,
        filename=filename,
    )
