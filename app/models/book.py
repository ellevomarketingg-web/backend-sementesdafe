import enum
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.buyer import Buyer
    from app.models.order import Order
    from app.models.book_template import BookTemplate
    from app.models.message import Message
    from app.models.delivery import Delivery


class BookStatus(str, enum.Enum):
    PENDING = "PENDING"
    GENERATING = "GENERATING"
    READY = "READY"
    DELIVERING = "DELIVERING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Book(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "books"

    buyer_id: Mapped[str] = mapped_column(String(36), ForeignKey("buyers.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id: Mapped[str] = mapped_column(String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    template_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("book_templates.id", ondelete="SET NULL"), nullable=True)
    template_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    child_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    
    status: Mapped[BookStatus] = mapped_column(
        SQLEnum(BookStatus, native_enum=False, length=32),
        default=BookStatus.PENDING,
        nullable=False,
        index=True,
    )
    
    file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    file_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    
    generation_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    buyer: Mapped["Buyer"] = relationship("Buyer", back_populates="books")
    order: Mapped["Order"] = relationship("Order", back_populates="books")
    template: Mapped[Optional["BookTemplate"]] = relationship("BookTemplate", back_populates="books")
    messages: Mapped[List["Message"]] = relationship("Message", back_populates="book", cascade="all, delete-orphan")
    deliveries: Mapped[List["Delivery"]] = relationship("Delivery", back_populates="book", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Book id={self.id} buyer_id={self.buyer_id} status={self.status}>"
