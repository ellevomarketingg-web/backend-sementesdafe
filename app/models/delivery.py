import enum
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.buyer import Buyer
    from app.models.book import Book


class DeliveryStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Delivery(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "deliveries"

    book_id: Mapped[str] = mapped_column(String(36), ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    buyer_id: Mapped[str] = mapped_column(String(36), ForeignKey("buyers.id", ondelete="CASCADE"), nullable=False, index=True)

    channel: Mapped[str] = mapped_column(String(32), default="WHATSAPP", nullable=False)
    status: Mapped[DeliveryStatus] = mapped_column(
        SQLEnum(DeliveryStatus, native_enum=False, length=32),
        default=DeliveryStatus.PENDING,
        nullable=False,
        index=True,
    )

    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    delivery_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    buyer: Mapped["Buyer"] = relationship("Buyer", back_populates="deliveries")
    book: Mapped["Book"] = relationship("Book", back_populates="deliveries")

    def __repr__(self) -> str:
        return f"<Delivery id={self.id} book_id={self.book_id} status={self.status}>"
