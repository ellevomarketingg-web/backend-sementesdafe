import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from app.models.book import Book, BookStatus
from app.models.order import Order, OrderStatus
from app.models.buyer import Buyer
from app.models.verification_code import VerificationCode
from app.schemas.book import (
    BookAvailabilityResponse,
    BookVerifyCodeResponse,
)
from app.services.book_generator import BookGenerator
from app.services.order_service import OrderService
from app.services.template_service import TemplateService
from app.services.communication_service import CommunicationService
from app.services.delivery_service import DeliveryService
from app.core.security import (
    create_download_token,
    verify_download_token,
    generate_numeric_code,
)
from app.core.config import settings
from app.core.logging import logger


from app.schemas.order_bump import OrderBumpItemResponse
from app.services.order_bump_service import OrderBumpService


class BookService:
    @staticmethod
    async def get_by_id(session: AsyncSession, book_id: str) -> Optional[Book]:
        return await session.get(Book, book_id)

    @staticmethod
    async def get_by_order_id(session: AsyncSession, order_id: str) -> Optional[Book]:
        stmt = select(Book).where(Book.order_id == order_id)
        return (await session.execute(stmt)).scalar_one_or_none()

    @classmethod
    async def create_book_for_order(
        cls,
        session: AsyncSession,
        order: Order,
        child_name: str = "",
        template_id: Optional[str] = None,
    ) -> Book:
        """
        Cria registro de livro em PENDING para uma compra confirmada.
        Garante idempotência: se já existir livro para este pedido, retorna o existente.
        """
        existing = await cls.get_by_order_id(session, order.id)
        if existing:
            logger.info(f"Livro já existente para order_id={order.id}, book_id={existing.id}")
            return existing

        # Busca template publicado padrão se não fornecido
        template = None
        if template_id:
            template = await session.get(template_id)
        if not template:
            template = await TemplateService.get_published_book_template(session)

        book = Book(
            buyer_id=order.buyer_id,
            order_id=order.id,
            template_id=template.id if template else None,
            template_version=template.version if template else 1,
            child_name=child_name or (order.metadata_info.get("child_name") if order.metadata_info else "") or "",
            status=BookStatus.PENDING,
        )
        session.add(book)
        await session.commit()
        await session.refresh(book)
        logger.info(f"Livro criado id={book.id} para order_id={order.id} status={book.status}")
        return book

    @classmethod
    async def generate_book(
        cls,
        session: AsyncSession,
        book_id: str,
        force: bool = False,
    ) -> Book:
        """
        Executa a geração do livro em PDF e atualiza estados.
        Idempotente: se já READY e não force, retorna imediatamente.
        """
        book = await cls.get_by_id(session, book_id)
        if not book:
            raise HTTPException(status_code=404, detail="Livro não encontrado.")

        if book.status == BookStatus.READY and not force and book.file_path and os.path.exists(book.file_path):
            logger.info(f"Livro {book.id} já está READY e gerado.")
            return book

        buyer = await session.get(Buyer, book.buyer_id)
        order = await session.get(Order, book.order_id)

        # Regra: só gera se a compra estiver PAID
        if not order or order.status != OrderStatus.PAID:
            book.status = BookStatus.FAILED
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não é possível gerar livro para pedido não pago.",
            )

        book.status = BookStatus.GENERATING
        book.generation_started_at = datetime.now(timezone.utc)
        await session.commit()

        # Diretório de destino
        output_dir = os.path.abspath(settings.STORAGE_PATH)
        os.makedirs(output_dir, exist_ok=True)
        pdf_path = os.path.join(output_dir, f"book_{book.id}.pdf")

        # Extrai variante/gênero se fornecido nos metadados
        gender_or_variant = None
        if order and order.metadata_info:
            gender_or_variant = (
                order.metadata_info.get("gender")
                or order.metadata_info.get("variant")
                or order.metadata_info.get("tipo")
                or (order.metadata_info.get("data", {}).get("offer", {}).get("name") if isinstance(order.metadata_info.get("data"), dict) else None)
            )

        # Geração do arquivo PDF
        success = BookGenerator.generate_book_pdf(
            output_path=pdf_path,
            child_name=book.child_name or (buyer.name if buyer else "Criança"),
            buyer_name=buyer.name if buyer else "",
            gender_or_variant=gender_or_variant,
        )

        if success:
            # Consome 1 crédito do comprador se houver créditos disponíveis
            if buyer and buyer.generation_credits > 0:
                buyer.generation_credits -= 1
                logger.info(
                    f"1 crédito consumido para geração do livro {book.id}. Saldo restante do comprador {buyer.email_normalized}: {buyer.generation_credits}"
                )

            book.status = BookStatus.READY
            book.file_path = pdf_path
            book.file_url = f"{settings.DOWNLOAD_URL_BASE}/{book.id}/download"
            book.generated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(book)

            logger.info(f"Livro {book.id} gerado com sucesso!")

            # Cria registro de entrega
            if buyer:
                delivery = await DeliveryService.create_delivery_record(
                    session=session,
                    book=book,
                    buyer=buyer,
                    channel="WHATSAPP",
                    delivery_url=book.file_url,
                )

                # Dispara notificação BOOK_READY via CommunicationService
                try:
                    await CommunicationService.create_and_dispatch_message(
                        session=session,
                        buyer=buyer,
                        event_code="BOOK_READY",
                        channel="WHATSAPP",
                        book=book,
                        send_immediately=True,
                    )
                except Exception as e:
                    logger.error(f"Erro ao disparar comunicação BOOK_READY: {e}")
        else:
            book.status = BookStatus.FAILED
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Falha ao gerar arquivo PDF do livro.",
            )

        return book

    @classmethod
    async def check_availability(
        cls,
        session: AsyncSession,
        email_normalized: str,
    ) -> BookAvailabilityResponse:
        """
        Verifica disponibilidade de créditos de geração, livros e order bumps para um e-mail.
        """
        # 1. Localiza comprador
        stmt = select(Buyer).where(Buyer.email_normalized == email_normalized)
        buyer = (await session.execute(stmt)).scalar_one_or_none()
        if not buyer:
            return BookAvailabilityResponse(
                available=False,
                credits=0,
                can_generate=False,
                reason="BUYER_NOT_FOUND",
                message="Nenhuma conta ou compra localizada com esse e-mail.",
                order_bumps=[],
            )

        # 2. Localiza livros e order bumps do comprador
        stmt_books = select(Book).where(Book.buyer_id == buyer.id).order_by(Book.created_at.desc())
        books = (await session.execute(stmt_books)).scalars().all()
        ready_books = [b for b in books if b.status in (BookStatus.READY, BookStatus.DELIVERED)]
        pending_books = [b for b in books if b.status in (BookStatus.PENDING, BookStatus.GENERATING)]

        buyer_order_bumps = await OrderBumpService.get_buyer_order_bumps(session, buyer.id)
        order_bump_items = [
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
            for ob in buyer_order_bumps
        ]

        # 3. Caso o comprador possua créditos de geração (> 0)
        if buyer.generation_credits > 0:
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

            target_book = ready_books[0] if ready_books else (pending_books[0] if pending_books else None)

            if buyer.phone:
                try:
                    await CommunicationService.create_and_dispatch_message(
                        session=session,
                        buyer=buyer,
                        event_code="VERIFICATION_CODE",
                        channel="WHATSAPP",
                        book=target_book,
                        context_override={"order_id": code_str},
                        send_immediately=True,
                    )
                except Exception as e:
                    logger.error(f"Erro ao enviar código de verificação via WhatsApp: {e}")

            return BookAvailabilityResponse(
                available=True,
                credits=buyer.generation_credits,
                can_generate=True,
                requires_verification=True,
                verification_channel="WHATSAPP" if buyer.phone else "EMAIL",
                book_id=target_book.id if target_book else None,
                status=target_book.status if target_book else None,
                delivery_available=len(ready_books) > 0,
                message=f"Você possui {buyer.generation_credits} crédito(s) de geração disponível(is).",
                order_bumps=order_bump_items,
            )

        # 4. Caso o comprador possua 0 créditos, mas já tenha livros gerados prontos para download
        if ready_books:
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
                        book=ready_books[0],
                        context_override={"order_id": code_str},
                        send_immediately=True,
                    )
                except Exception as e:
                    logger.error(f"Erro ao enviar código de verificação via WhatsApp: {e}")

            return BookAvailabilityResponse(
                available=True,
                credits=0,
                can_generate=False,
                requires_verification=True,
                verification_channel="WHATSAPP" if buyer.phone else "EMAIL",
                book_id=ready_books[0].id,
                status=BookStatus.READY,
                delivery_available=True,
                message="Você possui 0 créditos de geração restantes, mas possui livro(s) pronto(s) para download.",
                order_bumps=order_bump_items,
            )

        # 5. Caso o comprador possua Order Bumps desbloqueados (mesmo sem livro pronto ou créditos de livro)
        if order_bump_items:
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
                    logger.error(f"Erro ao enviar código de verificação via WhatsApp: {e}")

            return BookAvailabilityResponse(
                available=True,
                credits=0,
                can_generate=False,
                requires_verification=True,
                verification_channel="WHATSAPP" if buyer.phone else "EMAIL",
                delivery_available=True,
                message="Você possui Order Bump(s) liberado(s) para download.",
                order_bumps=order_bump_items,
            )

        # 6. Caso esteja gerando no momento
        if pending_books:
            return BookAvailabilityResponse(
                available=False,
                credits=0,
                can_generate=False,
                reason="BOOK_GENERATING",
                message="O livro está sendo preparado. Tente novamente em alguns instantes.",
                order_bumps=order_bump_items,
            )

        # 7. Sem créditos e sem livros
        stmt_order = select(Order).where(Order.buyer_id == buyer.id)
        orders = (await session.execute(stmt_order)).scalars().all()
        if orders and all(o.status != OrderStatus.PAID for o in orders):
            return BookAvailabilityResponse(
                available=False,
                credits=0,
                can_generate=False,
                reason="ORDER_NOT_PAID",
                message="Existe um pedido, mas o pagamento ainda não foi confirmado.",
                order_bumps=[],
            )

        return BookAvailabilityResponse(
            available=False,
            credits=0,
            can_generate=False,
            reason="NO_CREDITS_OR_PURCHASE",
            message="Você não possui créditos de geração ou livros disponíveis. Realize uma compra na Cakto para obter créditos.",
            order_bumps=[],
        )

    @classmethod
    async def verify_code_and_issue_download(
        cls,
        session: AsyncSession,
        email_normalized: str,
        code: str,
    ) -> BookVerifyCodeResponse:
        """
        Valida o código 2FA informado e emite tokens temporários assinados para download do livro e order bumps.
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
            return BookVerifyCodeResponse(
                success=False,
                message="Código inválido ou expirado. Solicite uma nova verificação.",
            )

        # Marca código como usado
        verif.used = True
        await session.commit()

        # Localiza o comprador
        buyer = await session.execute(
            select(Buyer).where(Buyer.email_normalized == email_normalized)
        )
        buyer_obj = buyer.scalar_one_or_none()
        if not buyer_obj:
            return BookVerifyCodeResponse(success=False, message="Comprador não encontrado.")

        # Localiza order bumps do comprador
        buyer_order_bumps = await OrderBumpService.get_buyer_order_bumps(session, buyer_obj.id)
        order_bump_items = []
        for ob in buyer_order_bumps:
            ob_token = create_download_token(book_id=ob.product_id, email=email_normalized)
            ob_download_url = f"{settings.ORDER_BUMP_DOWNLOAD_URL_BASE}/download-by-product/{ob.product_id}?token={ob_token}"
            order_bump_items.append(
                OrderBumpItemResponse(
                    id=ob.id,
                    product_id=ob.product_id,
                    product_name=ob.product_name,
                    product_code=ob.product_code,
                    status=ob.status,
                    download_url=ob_download_url,
                    download_token=ob_token,
                    unlocked_at=ob.unlocked_at,
                    created_at=ob.created_at,
                )
            )

        # Localiza o livro
        paid_orders = await OrderService.get_paid_orders_for_buyer(session, buyer_obj.id)
        book = None
        if paid_orders:
            book = await cls.get_by_order_id(session, paid_orders[0].id)

        if book and book.file_path:
            token = create_download_token(book_id=book.id, email=email_normalized)
            download_url = f"{settings.DOWNLOAD_URL_BASE}/{book.id}/download?token={token}"
            return BookVerifyCodeResponse(
                success=True,
                download_token=token,
                download_url=download_url,
                book_id=book.id,
                order_bumps=order_bump_items,
                message="Autorização concedida! Utilize os links para baixar seus materiais.",
            )

        if order_bump_items:
            return BookVerifyCodeResponse(
                success=True,
                download_token=order_bump_items[0].download_token,
                order_bumps=order_bump_items,
                message="Autorização concedida para seus Order Bumps!",
            )

        return BookVerifyCodeResponse(
            success=False,
            message="Nenhum material disponível para download.",
        )
