import enum
from datetime import datetime
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from sqlalchemy import String, Numeric, DateTime, ForeignKey, Enum as SQLEnum, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.buyer import Buyer
    from app.models.book import Book
    from app.models.order_bump import OrderBump


class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"
    CHARGEBACK = "CHARGEBACK"


class Order(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "orders"

    external_order_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    buyer_id: Mapped[str] = mapped_column(String(36), ForeignKey("buyers.id", ondelete="CASCADE"), nullable=False, index=True)
    product_code: Mapped[str] = mapped_column(String(64), default="DEUS_CONHECE_SEU_NOME", nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), default="Deus Conhece o Seu Nome", nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0, nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        SQLEnum(OrderStatus, native_enum=False, length=32),
        default=OrderStatus.PENDING,
        nullable=False,
        index=True,
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_info: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Relationships
    buyer: Mapped["Buyer"] = relationship("Buyer", back_populates="orders")
    books: Mapped[List["Book"]] = relationship("Book", back_populates="order", cascade="all, delete-orphan")
    order_bumps: Mapped[List["OrderBump"]] = relationship("OrderBump", back_populates="order", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Order id={self.id} external_id={self.external_order_id} status={self.status}>"
