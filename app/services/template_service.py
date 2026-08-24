import re
from typing import List, Dict, Any, Optional, Set
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from app.models.book_template import BookTemplate, TemplateStatus
from app.models.communication_template import CommunicationTemplate
from app.schemas.template import (
    TemplateValidationResult,
    TemplateValidationError,
    BookTemplateCreate,
    CommunicationTemplateCreate,
)
from app.core.logging import logger

ALLOWED_VARIABLES: Set[str] = {
    "buyer_name",
    "buyer_email",
    "buyer_phone",
    "child_name",
    "book_name",
    "book_id",
    "order_id",
    "delivery_url",
    "support_url",
}

VARIABLE_REGEX = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


class TemplateService:
    @staticmethod
    def extract_variables(text: str) -> List[str]:
        """Extrai todas as variáveis {{variavel}} de um texto de forma única preservando ordem."""
        matches = VARIABLE_REGEX.findall(text)
        seen = set()
        result = []
        for m in matches:
            if m not in seen:
                seen.add(m)
                result.append(m)
        return result

    @classmethod
    def validate_variables(
        cls,
        content: str,
        custom_allowed: Optional[List[str]] = None,
    ) -> TemplateValidationResult:
        """Valida se todas as variáveis utilizadas estão no catálogo permitido."""
        found_vars = cls.extract_variables(content)
        allowed = set(custom_allowed) if custom_allowed else ALLOWED_VARIABLES
        
        errors: List[TemplateValidationError] = []
        for var in found_vars:
            if var not in allowed:
                errors.append(
                    TemplateValidationError(
                        variable=var,
                        reason="VARIABLE_NOT_ALLOWED",
                    )
                )

        return TemplateValidationResult(
            valid=len(errors) == 0,
            variables_found=found_vars,
            errors=errors,
        )

    @classmethod
    def render(cls, template_str: str, context: Dict[str, Any]) -> str:
        """Renderiza texto substituindo {{variavel}} pelos valores fornecidos no contexto."""
        def replacer(match: re.Match) -> str:
            var_name = match.group(1).strip()
            val = context.get(var_name)
            return str(val) if val is not None else ""

        return VARIABLE_REGEX.sub(replacer, template_str)

    # ------------------ Book Templates ------------------
    @classmethod
    async def create_book_template(
        cls,
        session: AsyncSession,
        data: BookTemplateCreate,
    ) -> BookTemplate:
        """Cria um novo template de livro com versão incremental se já existir."""
        # Check highest version for this template name
        stmt = (
            select(func.coalesce(func.max(BookTemplate.version), 0))
            .where(BookTemplate.name == data.name)
        )
        max_version = (await session.execute(stmt)).scalar_one()
        new_version = max(data.version, max_version + 1)

        template = BookTemplate(
            name=data.name,
            version=new_version,
            status=TemplateStatus.DRAFT,
            template_data=data.template_data,
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)
        return template

    @classmethod
    async def publish_book_template(
        cls,
        session: AsyncSession,
        template_id: str,
    ) -> BookTemplate:
        """Publica uma versão de template de livro e arquiva as versões publicadas anteriores."""
        template = await session.get(BookTemplate, template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template de livro não encontrado.")

        # Archive previous published versions with same name
        stmt = select(BookTemplate).where(
            BookTemplate.name == template.name,
            BookTemplate.status == TemplateStatus.PUBLISHED,
            BookTemplate.id != template.id,
        )
        prev_published = (await session.execute(stmt)).scalars().all()
        for p in prev_published:
            p.status = TemplateStatus.ARCHIVED

        template.status = TemplateStatus.PUBLISHED
        await session.commit()
        await session.refresh(template)
        return template

    @classmethod
    async def get_published_book_template(
        cls,
        session: AsyncSession,
        name: str = "deus-conhece-seu-nome",
    ) -> Optional[BookTemplate]:
        """Obtém a versão atualmente publicada do template do livro."""
        stmt = (
            select(BookTemplate)
            .where(
                BookTemplate.name == name,
                BookTemplate.status == TemplateStatus.PUBLISHED,
            )
            .order_by(BookTemplate.version.desc())
            .limit(1)
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    # ------------------ Communication Templates ------------------
    @classmethod
    async def create_communication_template(
        cls,
        session: AsyncSession,
        data: CommunicationTemplateCreate,
    ) -> CommunicationTemplate:
        """Cria um novo template de comunicação."""
        # Valida variáveis antes de criar
        validation = cls.validate_variables(data.content)
        if not validation.valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Template contém variáveis inválidas: {[e.variable for e in validation.errors]}",
            )

        stmt = (
            select(func.coalesce(func.max(CommunicationTemplate.version), 0))
            .where(
                CommunicationTemplate.code == data.code,
                CommunicationTemplate.channel == data.channel,
            )
        )
        max_version = (await session.execute(stmt)).scalar_one()
        new_version = max(data.version, max_version + 1)

        template = CommunicationTemplate(
            code=data.code,
            name=data.name,
            channel=data.channel,
            event=data.event,
            version=new_version,
            content=data.content,
            variables=data.variables or {"found": validation.variables_found},
            status=TemplateStatus.DRAFT,
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)
        return template

    @classmethod
    async def publish_communication_template(
        cls,
        session: AsyncSession,
        template_id: str,
    ) -> CommunicationTemplate:
        """Publica template de comunicação garantindo imutabilidade."""
        template = await session.get(CommunicationTemplate, template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template de comunicação não encontrado.")

        # Valida o conteúdo
        validation = cls.validate_variables(template.content)
        if not validation.valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Template inválido para publicação: {[e.variable for e in validation.errors]}",
            )

        # Arquiva versões anteriores publicadas do mesmo código e canal
        stmt = select(CommunicationTemplate).where(
            CommunicationTemplate.code == template.code,
            CommunicationTemplate.channel == template.channel,
            CommunicationTemplate.status == TemplateStatus.PUBLISHED,
            CommunicationTemplate.id != template.id,
        )
        prev_templates = (await session.execute(stmt)).scalars().all()
        for pt in prev_templates:
            pt.status = TemplateStatus.ARCHIVED

        template.status = TemplateStatus.PUBLISHED
        await session.commit()
        await session.refresh(template)
        return template

    @classmethod
    async def get_published_communication_template(
        cls,
        session: AsyncSession,
        code: str,
        channel: str = "WHATSAPP",
    ) -> Optional[CommunicationTemplate]:
        """Busca template publicado para o código e canal solicitados."""
        stmt = (
            select(CommunicationTemplate)
            .where(
                CommunicationTemplate.code == code,
                CommunicationTemplate.channel == channel,
                CommunicationTemplate.status == TemplateStatus.PUBLISHED,
            )
            .order_by(CommunicationTemplate.version.desc())
            .limit(1)
        )
        return (await session.execute(stmt)).scalar_one_or_none()
