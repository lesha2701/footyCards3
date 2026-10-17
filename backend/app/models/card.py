from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, BigInteger, Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
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
    # The owner's own «замок» (migration 0161): protects this copy from being
    # sold or burned as material — it still plays in squads and can be traded.
    is_user_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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
    # «Звёзды карточки» (services/card_star_service.py): duplicates of the
    # same player fed into THIS copy. star_progress = duplicates banked toward
    # the next star; star_rating_bonus = rating the earned stars add, fixed at
    # the moment each star was claimed (like diamond_rating_bonus, so a later
    # admin retune never rewrites already-earned stars). Travels with the row
    # on a trade. Never set on diamond cards (they have their own upgrade).
    stars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    star_progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    star_rating_bonus: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # «Академия» (services/path_service.py), path cards only: levels gained
    # on the path, the stage reached (0 = Новичок … 4 = Легенда) and the rating
    # those levels add — fixed on the row when each level is gained, like
    # diamond_rating_bonus. The rest of the progress is in card_paths.
    path_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    path_stage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    path_rating_bonus: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # «Академия» prestige (services/path_prestige_service.py): tier 0..max
    # bought with duplicates of the same player — status, not power. The top
    # tier gets a global «Икона» number (unique) and one talent reforge,
    # which overrides the design's talent for THIS copy only.
    prestige: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prestige_icon_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, unique=True)
    talent_override: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("path_talents.code", ondelete="RESTRICT"), nullable=True
    )
    talent_reforged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    owner: Mapped["User"] = relationship(back_populates="cards")
    player: Mapped["Player"] = relationship(back_populates="cards")

    def has_star_investment(self) -> bool:
        return bool(self.stars or self.star_progress)

    def has_path_progress(self) -> bool:
        return bool(self.path_level or self.path_stage or self.prestige)

    def is_locked(self) -> bool:
        return self.is_locked_by_admin or self.is_locked_in_trade or self.is_in_lineup or self.is_in_tactico_squad

    def can_burn(self) -> bool:
        """May this copy be destroyed as material (stars, diamond feeding,
        prestige)? Never while it's locked, in a squad, or under the owner's
        own «замок»."""
        return not self.is_locked() and not self.is_user_locked

    __table_args__ = (
        UniqueConstraint("player_id", "serial_number", name="uq_user_cards_player_serial"),
        CheckConstraint(
            "(skill_code IS NULL AND skill_level IS NULL) OR "
            "(skill_code IS NOT NULL AND skill_level IS NOT NULL AND skill_level BETWEEN 1 AND 3)",
            name="ck_user_cards_skill_level",
        ),
        CheckConstraint(
            "stars >= 0 AND star_progress >= 0 AND star_rating_bonus >= 0", name="ck_user_cards_stars_non_negative",
        ),
        CheckConstraint(
            "path_level >= 0 AND path_stage >= 0 AND path_rating_bonus >= 0", name="ck_user_cards_path_non_negative",
        ),
    )


class CardStarLedger(Base):
    """Append-only journal of every «Звёзды карточек» operation: feeding
    duplicates into a copy and claiming stars. `idempotency_key` is unique
    per user, which is what makes a retried feed/claim a replay instead of a
    second charge — same DB-constraint approach as card_skill_ledger."""

    __tablename__ = "card_star_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # SET NULL: the history outlives the card being sold/consumed later.
    user_card_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # feed | claim
    cards_consumed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consumed_card_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    stars_before: Mapped[int] = mapped_column(Integer, nullable=False)
    stars_after: Mapped[int] = mapped_column(Integer, nullable=False)
    progress_before: Mapped[int] = mapped_column(Integer, nullable=False)
    progress_after: Mapped[int] = mapped_column(Integer, nullable=False)
    coins_spent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rating_bonus_after: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_card_star_ledger_user_key"),)
