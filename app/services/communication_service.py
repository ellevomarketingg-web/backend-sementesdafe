import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.models.message import Message, MessageStatus
from app.models.buyer import Buyer
from app.models.book import Book
from app.models.communication_template import CommunicationTemplate
from app.models.book_template import TemplateStatus
from app.services.template_service import TemplateService
from app.services.evolution_service import evolution_service
from app.core.config import settings
from app.core.logging import logger

DEFAULT_COMMUNICATION_TEMPLATES = [
    {
        "code": "PURCHASE_CONFIRMED",
        "name": "Confirmação de Pagamento",
        "event": "order.paid",
        "channel": "WHATSAPP",
        "content": (
            "Olá, {{buyer_name}}! ❤️\n\n"
            "Seu pedido *{{order_id}}* do livro *{{book_name}}* foi confirmado com sucesso!\n\n"
            "Já estamos preparando o livro personalizado para {{child_name}}. Assim que estiver pronto, te avisamos por aqui! ✨"
        ),
    },
    {
        "code": "BOOK_READY",
        "name": "Livro Pronto para Download",
        "event": "book.ready",
        "channel": "WHATSAPP",
        "content": (
            "Olá, {{buyer_name}}! ❤️\n\n"
            "O livro personalizado *{{book_name}}* de {{child_name}} já está pronto!\n\n"
            "Você pode acessar e baixar o PDF no link abaixo:\n"
            "{{delivery_url}}\n\n"
            "Que esta leitura seja uma grande bênção na sua casa! 🙏"
        ),
    },
    {
        "code": "VERIFICATION_CODE",
        "name": "Código de Verificação 2FA",
        "event": "auth.verification",
        "channel": "WHATSAPP",
        "content": (
            "Olá, {{buyer_name}}!\n\n"
            "Seu código de acesso para consultar seu livro é: *{{order_id}}*\n\n"
            "Este código é válido por 15 minutos."
        ),
    },
]


class CommunicationService:
    """Orquestrador de templates, mensagens e canais de comunicação."""

    @classmethod
    async def ensure_default_templates(cls, session: AsyncSession) -> None:
        """Garante a existência de templates padrão publicados no banco."""
        for item in DEFAULT_COMMUNICATION_TEMPLATES:
            stmt = select(CommunicationTemplate).where(
                CommunicationTemplate.code == item["code"],
                CommunicationTemplate.channel == item["channel"],
            )
            exists = (await session.execute(stmt)).scalar_one_or_none()
            if not exists:
                validation = TemplateService.validate_variables(item["content"])
                tmpl = CommunicationTemplate(
                    code=item["code"],
                    name=item["name"],
                    channel=item["channel"],
                    event=item["event"],
                    version=1,
                    content=item["content"],
                    variables={"found": validation.variables_found},
                    status=TemplateStatus.PUBLISHED,
                )
                session.add(tmpl)
        await session.commit()

    @classmethod
    async def create_and_dispatch_message(
        cls,
        session: AsyncSession,
        buyer: Buyer,
        event_code: str,
        channel: str = "WHATSAPP",
        book: Optional[Book] = None,
        context_override: Optional[Dict[str, Any]] = None,
        send_immediately: bool = False,
    ) -> Message:
        """
        Localiza template, monta variáveis de contexto, cria registro de Message
        e opcionalmente dispara via Evolution API.
        """
        # Garante templates
        await cls.ensure_default_templates(session)

        # Busca template publicado
        template = await TemplateService.get_published_communication_template(
            session, code=event_code, channel=channel
        )
        if not template:
            # Fallback para qualquer versão do código
            stmt = (
                select(CommunicationTemplate)
                .where(
                    CommunicationTemplate.code == event_code,
                    CommunicationTemplate.channel == channel,
                )
                .order_by(CommunicationTemplate.version.desc())
                .limit(1)
            )
            template = (await session.execute(stmt)).scalar_one_or_none()

        if not template:
            raise HTTPException(
                status_code=404,
                detail=f"Nenhum template de comunicação encontrado para código '{event_code}' no canal '{channel}'.",
            )

        # Monta dicionário de variáveis de contexto
        context = {
            "buyer_name": buyer.name,
            "buyer_email": buyer.email,
            "buyer_phone": buyer.phone or "",
            "child_name": (book.child_name if book and book.child_name else (buyer.name.split()[0] if buyer.name else "sua criança")),
            "book_name": "Deus Conhece o Seu Nome",
            "book_id": str(book.id) if book else "",
            "order_id": str(book.order_id) if book and book.order_id else "",
            "delivery_url": (f"{settings.DOWNLOAD_URL_BASE}/{book.id}/download" if book else ""),
            "support_url": "https://deusconheceoseunome.com.br/suporte",
        }
        if context_override:
            context.update(context_override)

        # Renderiza conteúdo
        rendered_content = TemplateService.render(template.content, context)

        # Destinatário
        destination = buyer.phone if channel == "WHATSAPP" else buyer.email_normalized
        if not destination:
            destination = "unspecified"

        message = Message(
            buyer_id=buyer.id,
            book_id=book.id if book else None,
            template_id=template.id,
            template_version=template.version,
            channel=channel,
            destination=destination,
            content=rendered_content,
            status=MessageStatus.PENDING,
            attempts=0,
        )
        session.add(message)
        await session.commit()
        await session.refresh(message)

        logger.info(
            f"Mensagem criada id={message.id} canal={channel} evento={event_code} dest={destination}"
        )

        if send_immediately and channel == "WHATSAPP" and buyer.phone:
            await cls.process_send_message(session, message)

        return message

    @classmethod
    async def process_send_message(cls, session: AsyncSession, message: Message) -> Message:
        """Executa a chamada na Evolution API e atualiza status da mensagem."""
        if message.status in (MessageStatus.SENT, MessageStatus.DELIVERED):
            return message

        message.status = MessageStatus.PROCESSING
        message.attempts += 1
        await session.commit()

        if message.channel == "WHATSAPP":
            res = await evolution_service.send_text(
                phone=message.destination,
                message=message.content,
            )
            if res.get("success"):
                message.status = MessageStatus.SENT
                message.external_message_id = res.get("external_message_id")
                message.sent_at = datetime.now(timezone.utc)
                message.error_message = None
            else:
                message.status = MessageStatus.FAILED
                message.error_message = res.get("error")
        else:
            # Outros canais (mock / simulação de envio)
            message.status = MessageStatus.SENT
            message.sent_at = datetime.now(timezone.utc)

        await session.commit()
        await session.refresh(message)
        return message

    @classmethod
    async def retry_message(cls, session: AsyncSession, message_id: str) -> Message:
        """Reprocessa uma mensagem que falhou."""
        message = await session.get(Message, message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Mensagem não encontrada.")

        return await cls.process_send_message(session, message)
