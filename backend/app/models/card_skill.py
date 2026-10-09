from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, utcnow


class CardSkill(TimestampMixin, Base):
    """Admin-editable state of one skill from the fixed server catalog
    (services/card_skill_catalog.SKILL_DEFINITIONS). The code-side catalog
    owns what a skill DOES and the widest set of positions it can ever fit;
    this row only owns what an admin may tune without a deploy: whether new
    acquisition is open, a narrower position subset, and display order.
    Levels' bonus values and every price live on GameConfig (single source
    of truth for strength/economy)."""

    __tablename__ = "card_skills"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # NULL = every position the server catalog allows; otherwise a subset of it
    # (validated against the catalog on write, never widened past it).
    allowed_positions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Pack drop table for tokens of this skill (used by any pack whose
    # skill_token_drop_chance > 0): relative weight among skills (0 = never
    # drops) and how many tokens one dropped slot gives.
    pack_drop_weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    pack_drop_quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class UserSkillToken(Base):
    """Per-user, per-skill token balance. Rows are created lazily on the
    first grant, so users who never received a token have no rows."""

    __tablename__ = "user_skill_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_code: Mapped[str] = mapped_column(ForeignKey("card_skills.code", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "skill_code", name="uq_user_skill_tokens_user_skill"),
        CheckConstraint("quantity >= 0", name="ck_user_skill_tokens_quantity_non_negative"),
    )


class CardSkillLedger(Base):
    """Append-only journal of every token movement and every skill change on
    a card (grant, assign, upgrade, replace). `idempotency_key` is unique per
    user, which is what makes a retried assign/upgrade/replace or admin
    grant a no-op replay instead of a second charge — same DB-constraint
    approach as pack_openings / card_upgrade_attempts."""

    __tablename__ = "card_skill_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # grant_task | grant_tournament | grant_admin | revoke_admin | assign | upgrade | replace
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    skill_code: Mapped[str] = mapped_column(String(32), nullable=False)
    token_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_balance_after: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    coins_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # SET NULL, not CASCADE: the history of what happened to a card outlives
    # the card itself being sold/consumed later.
    user_card_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True, index=True
    )
    from_skill_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    from_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    to_skill_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    to_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    admin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    related_object_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    related_object_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    __table_args__ = (
        Index(
            "uq_card_skill_ledger_user_idem", "user_id", "idempotency_key", unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"), sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
    )
