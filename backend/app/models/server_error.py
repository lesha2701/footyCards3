from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class ServerError(Base):
    """One unhandled exception behind a 500 (error_log_service). The bot
    sends the admins a daily digest of these and prunes old rows."""

    __tablename__ = "server_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    error: Mapped[str] = mapped_column(String(255), nullable=False)  # «ExceptionType: message», cut
    traceback: Mapped[str] = mapped_column(Text, nullable=False, default="")
