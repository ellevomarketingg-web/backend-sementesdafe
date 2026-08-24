import enum
from datetime import datetime, timezone
from typing import Optional, Dict, Any, TYPE_CHECKING
from sqlalchemy import String, ForeignKey, Enum as SQLEnum, JSON, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.buyer import Buyer
    from app.models.order import Order


class OrderBumpStatus(str, enum.Enum):
    UNLOCKED = "UNLOCKED"
    DOWNLOADED = "DOWNLOADED"
    REVOKED = "REVOKED"


class OrderBump(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "order_bumps"

    buyer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("buyers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=True, index=True
    )
    product_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[OrderBumpStatus] = mapped_column(
        SQLEnum(OrderBumpStatus, native_enum=False, length=32),
        default=OrderBumpStatus.UNLOCKED,
        nullable=False,
        index=True,
    )
    file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    download_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unlocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    metadata_info: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Relationships
    buyer: Mapped["Buyer"] = relationship("Buyer", back_populates="order_bumps")
    order: Mapped[Optional["Order"]] = relationship("Order", back_populates="order_bumps")

    def __repr__(self) -> str:
        return f"<OrderBump id={self.id} product_id={self.product_id} status={self.status}>"
