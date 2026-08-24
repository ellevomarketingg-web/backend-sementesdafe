import enum
from typing import Dict, Any, List, TYPE_CHECKING
from sqlalchemy import String, Integer, Enum as SQLEnum, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.book import Book


class TemplateStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class BookTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "book_templates"

    name: Mapped[str] = mapped_column(String(128), default="deus-conhece-seu-nome", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[TemplateStatus] = mapped_column(
        SQLEnum(TemplateStatus, native_enum=False, length=32),
        default=TemplateStatus.DRAFT,
        nullable=False,
    )
    template_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_book_template_name_version"),
    )

    # Relationships
    books: Mapped[List["Book"]] = relationship("Book", back_populates="template")

    def __repr__(self) -> str:
        return f"<BookTemplate id={self.id} name={self.name} v={self.version} status={self.status}>"
