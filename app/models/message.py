import enum
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.buyer import Buyer
    from app.models.book import Book
    from app.models.communication_template import CommunicationTemplate


class MessageStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Message(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "messages"

    buyer_id: Mapped[str] = mapped_column(String(36), ForeignKey("buyers.id", ondelete="CASCADE"), nullable=False, index=True)
    book_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("books.id", ondelete="SET NULL"), nullable=True, index=True)
    template_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("communication_templates.id", ondelete="SET NULL"), nullable=True)
    template_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    channel: Mapped[str] = mapped_column(String(32), default="WHATSAPP", nullable=False)
    destination: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[MessageStatus] = mapped_column(
        SQLEnum(MessageStatus, native_enum=False, length=32),
        default=MessageStatus.PENDING,
        nullable=False,
        index=True,
    )

    external_message_id: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    buyer: Mapped["Buyer"] = relationship("Buyer", back_populates="messages")
    book: Mapped[Optional["Book"]] = relationship("Book", back_populates="messages")
    template: Mapped[Optional["CommunicationTemplate"]] = relationship("CommunicationTemplate", back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message id={self.id} status={self.status} destination={self.destination}>"
