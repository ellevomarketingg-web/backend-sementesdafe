import os
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.logging import logger
from app.core.security import create_download_token, verify_download_token, generate_numeric_code
from app.models.buyer import Buyer
from app.models.order import Order
from app.models.order_bump import OrderBump, OrderBumpStatus
from app.models.verification_code import VerificationCode
from app.schemas.order_bump import (
     OrderBumpCatalogItem,
     OrderBumpItemResponse,
     OrderBumpAvailabilityResponse,
     OrderBumpVerifyResponse,
)
from app.services.communication_service import CommunicationService


class OrderBumpService:
    @staticmethod
    def get_catalog() -> List[OrderBumpCatalogItem]:
        """Retorna todos os order bumps cadastrados no catálogo oficial."""
        return [
            OrderBumpCatalogItem(**item)
            for item in settings.order_bumps_catalog.values()
        ]

    @staticmethod
    def get_catalog_item(product_id: str) -> Optional[Dict[str, Any]]:
        """Retorna metadados do catálogo para um product_id específico."""
        return settings.order_bumps_catalog.get(product_id)

    @classmethod
    def get_or_create_asset_file(cls, product_id: str) -> str:
        """
        Retorna o caminho físico do arquivo do order bump, criando um arquivo de demonstração
        se ainda não existir no disco.
        """
        catalog_info = cls.get_catalog_item(product_id)
        filename = catalog_info["filename"] if catalog_info else f"order_bump_{product_id}.zip"
        
        storage_dir = os.path.abspath(settings.ORDER_BUMP_STORAGE_PATH)
        os.makedirs(storage_dir, exist_ok=True)
        file_path = os.path.join(storage_dir, filename)

        if not os.path.exists(file_path):
            try:
                if filename.endswith(".pdf"):
                    # Cria PDF inicial de demonstração caso ainda não exista
                    import fitz
                    doc = fitz.open()
                    page = doc.new_page(width=595, height=842)
                    page.insert_text(
                        fitz.Point(50, 100),
                        catalog_info["name"] if catalog_info else "Material Cristão",
                        fontsize=20,
                        color=(0.1, 0.2, 0.6),
                    )
                    page.insert_text(
                        fitz.Point(50, 140),
                        "Conteúdo digital oficial liberado com sucesso!",
                        fontsize=14,
                        color=(0.2, 0.2, 0.2),
                    )
                    doc.save(file_path)
                    doc.close()
                else:
                    # Cria arquivo zip / binário inicial
                    import zipfile
                    with zipfile.ZipFile(file_path, "w", zipfile.ZIP_DEFLATED) as zf:
                        zf.writestr(
                            "LEIA-ME.txt",
                            f"Obrigado por adquirir {catalog_info['name'] if catalog_info else 'Order Bump'}!\n"
                            f"Instruções e arquivos inclusos com sucesso.",
                        )
                logger.info(f"Asset provisionado para Order Bump {product_id} em {file_path}")
            except Exception as e:
                logger.error(f"Erro ao provisionar arquivo do order bump {product_id}: {e}")
                # Fallback simples
                with open(file_path, "wb") as f:
                    f.write(b"Conteudo digital Order Bump")

        return file_path

    @classmethod
    async def grant_order_bump_access(
        cls,
        session: AsyncSession,
        buyer: Buyer,
        order: Optional[Order],
        product_id: str,
        product_name: Optional[str] = None,
        product_code: Optional[str] = None,
        metadata_info: Optional[Dict[str, Any]] = None,
    ) -> OrderBump:
        """
        Concede e registra o acesso ao Order Bump para o comprador.
        Idempotente: se já existir para este comprador e pedido/produto, retorna o existente.
        """
        # Checa se já existe registro idêntico para o pedido/comprador
        stmt = (
            select(OrderBump)
            .where(
                OrderBump.buyer_id == buyer.id,
                OrderBump.product_id == product_id,
            )
        )
        if order:
            stmt = stmt.where(OrderBump.order_id == order.id)

        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing:
            logger.info(f"OrderBump {product_id} já concedido para comprador {buyer.id}")
            return existing

        catalog_info = cls.get_catalog_item(product_id)
        name = product_name or (catalog_info["name"] if catalog_info else f"Order Bump {product_id}")
        code = product_code or (catalog_info["code"] if catalog_info else "ORDER_BUMP")

        file_path = cls.get_or_create_asset_file(product_id)

        order_bump = OrderBump(
            buyer_id=buyer.id,
            order_id=order.id if order else None,
            product_id=product_id,
            product_name=name,
            product_code=code,
            status=OrderBumpStatus.UNLOCKED,
            file_path=file_path,
            download_url=f"{settings.ORDER_BUMP_DOWNLOAD_URL_BASE}/download-by-product/{product_id}",
            metadata_info=metadata_info,
        )
        session.add(order_bump)
        await session.commit()
        await session.refresh(order_bump)

        logger.info(f"OrderBump concedido id={order_bump.id} product_id={product_id} para buyer={buyer.email_normalized}")
        return order_bump

    @classmethod
    async def get_buyer_order_bumps(
        cls,
        session: AsyncSession,
        buyer_id: str,
    ) -> List[OrderBump]:
        """Lista todos os order bumps desbloqueados de um comprador."""
        stmt = (
            select(OrderBump)
            .where(
                OrderBump.buyer_id == buyer_id,
                OrderBump.status != OrderBumpStatus.REVOKED,
            )
            .order_by(OrderBump.created_at.desc())
        )
        return list((await session.execute(stmt)).scalars().all())

    @classmethod
    async def check_availability(
        cls,
        session: AsyncSession,
        email_normalized: str,
        product_id: Optional[str] = None,
    ) -> OrderBumpAvailabilityResponse:
        """
        Verifica se um comprador tem acesso a order bumps por e-mail.
        Dispara código 2FA se possuir itens.
        """
        stmt_buyer = select(Buyer).where(Buyer.email_normalized == email_normalized)
        buyer = (await session.execute(stmt_buyer)).scalar_one_or_none()
        if not buyer:
            return OrderBumpAvailabilityResponse(
                has_access=False,
                email=email_normalized,
                order_bumps=[],
                requires_verification=False,
                message="Nenhum registro de compra encontrado para este e-mail.",
            )

        order_bumps = await cls.get_buyer_order_bumps(session, buyer.id)
        if product_id:
            order_bumps = [ob for ob in order_bumps if ob.product_id == product_id]

        if not order_bumps:
            return OrderBumpAvailabilityResponse(
                has_access=False,
                email=email_normalized,
                order_bumps=[],
                requires_verification=False,
                message="Nenhum Order Bump adquirido com este e-mail.",
            )

        # Gera código 2FA
        code_str = generate_numeric_code(6)
        expires = datetime.now(timezone.utc) + timedelta(minutes=settings.VERIFICATION_CODE_EXPIRE_MINUTES)
        verif = VerificationCode(
            email_normalized=email_normalized,
            code=code_str,
            expires_at=expires,
            used=False,
        )
        session.add(verif)
        await session.commit()

        if buyer.phone:
            try:
                await CommunicationService.create_and_dispatch_message(
                    session=session,
                    buyer=buyer,
                    event_code="VERIFICATION_CODE",
                    channel="WHATSAPP",
                    context_override={"order_id": code_str},
                    send_immediately=True,
                )
            except Exception as e:
                logger.error(f"Erro ao enviar código de verificação para Order Bumps: {e}")

        items = [
            OrderBumpItemResponse(
                id=ob.id,
                product_id=ob.product_id,
                product_name=ob.product_name,
                product_code=ob.product_code,
                status=ob.status,
                download_url=ob.download_url,
                unlocked_at=ob.unlocked_at,
                created_at=ob.created_at,
            )
            for ob in order_bumps
        ]

        return OrderBumpAvailabilityResponse(
            has_access=True,
            email=email_normalized,
            order_bumps=items,
            requires_verification=True,
            verification_channel="WHATSAPP" if buyer.phone else "EMAIL",
            message=f"Você possui {len(items)} Order Bump(s) disponível(is). Código de validação enviado.",
        )

    @classmethod
    async def verify_code_and_issue_download(
        cls,
        session: AsyncSession,
        email_normalized: str,
        code: str,
        product_id: Optional[str] = None,
    ) -> OrderBumpVerifyResponse:
        """
        Valida o código 2FA informado e gera tokens de download seguros para os order bumps.
        """
        stmt = (
            select(VerificationCode)
            .where(
                VerificationCode.email_normalized == email_normalized,
                VerificationCode.code == code.strip(),
                VerificationCode.used == False,
            )
            .order_by(VerificationCode.created_at.desc())
            .limit(1)
        )
        verif = (await session.execute(stmt)).scalar_one_or_none()
        if not verif or verif.is_expired:
            return OrderBumpVerifyResponse(
                success=False,
                message="Código inválido ou expirado. Solicite uma nova verificação.",
            )

        verif.used = True
        await session.commit()

        stmt_buyer = select(Buyer).where(Buyer.email_normalized == email_normalized)
        buyer = (await session.execute(stmt_buyer)).scalar_one_or_none()
        if not buyer:
            return OrderBumpVerifyResponse(success=False, message="Comprador não localizado.")

        order_bumps = await cls.get_buyer_order_bumps(session, buyer.id)
        if product_id:
            order_bumps = [ob for ob in order_bumps if ob.product_id == product_id]

        if not order_bumps:
            return OrderBumpVerifyResponse(success=False, message="Nenhum Order Bump liberado para download.")

        # Cria tokens de download para cada order bump
        items = []
        token_geral = None
        for ob in order_bumps:
            token = create_download_token(book_id=ob.product_id, email=email_normalized)
            token_geral = token_geral or token
            download_url = f"{settings.ORDER_BUMP_DOWNLOAD_URL_BASE}/download-by-product/{ob.product_id}?token={token}"
            items.append(
                OrderBumpItemResponse(
                    id=ob.id,
                    product_id=ob.product_id,
                    product_name=ob.product_name,
                    product_code=ob.product_code,
                    status=ob.status,
                    download_url=download_url,
                    download_token=token,
                    unlocked_at=ob.unlocked_at,
                    created_at=ob.created_at,
                )
            )

        return OrderBumpVerifyResponse(
            success=True,
            download_token=token_geral,
            order_bumps=items,
            message="Downloads liberados com sucesso!",
        )
