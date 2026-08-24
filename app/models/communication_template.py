from typing import Dict, Any, List, TYPE_CHECKING
from sqlalchemy import String, Integer, Text, Enum as SQLEnum, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.book_template import TemplateStatus

if TYPE_CHECKING:
    from app.models.message import Message


class CommunicationTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "communication_templates"

    code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), default="WHATSAPP", nullable=False)
    event: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[TemplateStatus] = mapped_column(
        SQLEnum(TemplateStatus, native_enum=False, length=32),
        default=TemplateStatus.DRAFT,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("code", "channel", "version", name="uq_comm_template_code_channel_version"),
    )

    # Relationships
    messages: Mapped[List["Message"]] = relationship("Message", back_populates="template")

    def __repr__(self) -> str:
        return f"<CommunicationTemplate id={self.id} code={self.code} v={self.version} status={self.status}>"
