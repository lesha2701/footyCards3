from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin


class PersonalSquad(TimestampMixin, Base):
    """One of 5 fixed saved squads per user used ONLY by player tournaments —
    separate from Card Arena `Lineup` and Тактико squads. Templates 2-5 are
    lazily created by personal_squad_service._ensure_templates."""

    __tablename__ = "personal_squads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    template_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="Шаблон 1")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    formation: Mapped[str] = mapped_column(String(16), nullable=False, default="4-3-3", server_default="4-3-3")
    mentality: Mapped[str] = mapped_column(String(16), nullable=False, default="BALANCED", server_default="BALANCED")
    playstyle: Mapped[str] = mapped_column(String(16), nullable=False, default="CENTRAL_PLAY", server_default="CENTRAL_PLAY")
    user_coach_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_coach_cards.id", ondelete="SET NULL"), nullable=True
    )
    user_stadium_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_stadium_cards.id", ondelete="SET NULL"), nullable=True
    )

    cards: Mapped[list["PersonalSquadCard"]] = relationship(back_populates="squad", cascade="all, delete-orphan")
    user_coach_card: Mapped["UserCoachCard | None"] = relationship(lazy="joined")
    user_stadium_card: Mapped["UserStadiumCard | None"] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("user_id", "template_index", name="uq_personal_squad_user_template"),
        Index(
            "uq_personal_squad_one_active_per_user", "user_id", unique=True,
            postgresql_where=text("is_active"), sqlite_where=text("is_active"),
        ),
    )


class PersonalSquadCard(Base):
    __tablename__ = "personal_squad_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    squad_id: Mapped[int] = mapped_column(ForeignKey("personal_squads.id", ondelete="CASCADE"), nullable=False, index=True)
    user_card_id: Mapped[int] = mapped_column(ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False, index=True)
    slot_code: Mapped[str] = mapped_column(String(16), nullable=False)

    squad: Mapped["PersonalSquad"] = relationship(back_populates="cards")
    user_card: Mapped["UserCard"] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("squad_id", "user_card_id", name="uq_personal_squad_card_once"),
        UniqueConstraint("squad_id", "slot_code", name="uq_personal_squad_slot_once"),
    )
