from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class VerificationCode(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "verification_codes"

    email_normalized: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return True
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > expires

    def __repr__(self) -> str:
        return f"<VerificationCode email={self.email_normalized} used={self.used}>"
