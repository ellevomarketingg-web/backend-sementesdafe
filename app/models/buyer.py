from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import String, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.book import Book
    from app.models.message import Message
    from app.models.delivery import Delivery
    from app.models.order_bump import OrderBump


class Buyer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "buyers"

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    generation_credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    orders: Mapped[List["Order"]] = relationship("Order", back_populates="buyer", cascade="all, delete-orphan")
    books: Mapped[List["Book"]] = relationship("Book", back_populates="buyer", cascade="all, delete-orphan")
    order_bumps: Mapped[List["OrderBump"]] = relationship("OrderBump", back_populates="buyer", cascade="all, delete-orphan")
    messages: Mapped[List["Message"]] = relationship("Message", back_populates="buyer", cascade="all, delete-orphan")
    deliveries: Mapped[List["Delivery"]] = relationship("Delivery", back_populates="buyer", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Buyer id={self.id} email={self.email_normalized} name={self.name}>"
