from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import CardSource
from app.models.mixins import utcnow


class UserCard(Base):
    __tablename__ = "user_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Per-player copy number (1, 2, 3... independently for each Player design),
    # assigned atomically from Player.next_serial_number in services/card_creation.py
    # under a row lock on the Player. Unique per player, not globally.
    serial_number: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="RESTRICT"), nullable=False, index=True)

    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    source: Mapped[CardSource] = mapped_column(Enum(CardSource, name="card_source_enum"), nullable=False)
    source_ref_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    is_locked_by_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_locked_in_trade: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_in_lineup: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_in_tactico_squad: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hidden_from_trade: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Diamond-rarity only: rating points earned by feeding this specific
    # copy other cards (see diamond_upgrade_service.py). Lives on the owned
    # card, not Player.rating, so leveling one copy never affects other
    # users' copies of the same diamond player.
    diamond_rating_bonus: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Personal skill of THIS copy (see services/card_skill_service.py). Lives
    # on the owned card row, like diamond_rating_bonus, so it travels with the
    # card on a trade (owner_id changes, the row doesn't) and two copies of
    # the same player are fully independent. NULL/NULL = no skill (every card
    # that existed before the feature).
    skill_code: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("card_skills.code", ondelete="RESTRICT"), nullable=True, index=True
    )
    skill_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    owner: Mapped["User"] = relationship(back_populates="cards")
    player: Mapped["Player"] = relationship(back_populates="cards")

    def is_locked(self) -> bool:
        return self.is_locked_by_admin or self.is_locked_in_trade or self.is_in_lineup or self.is_in_tactico_squad

    __table_args__ = (
        UniqueConstraint("player_id", "serial_number", name="uq_user_cards_player_serial"),
        CheckConstraint(
            "(skill_code IS NULL AND skill_level IS NULL) OR "
            "(skill_code IS NOT NULL AND skill_level IS NOT NULL AND skill_level BETWEEN 1 AND 3)",
            name="ck_user_cards_skill_level",
        ),
    )
