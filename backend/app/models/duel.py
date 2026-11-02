"""Flank duels of «Карьера тренера» (services/duel_service.py).

  * PlayerRivalry — a known matchup set by the admin, by person_key (all
    versions of a footballer share it): «Мендеш гасит Ямаля» = attacker
    Ямаль, defender Мендеш, level -3. Positive = the attacker has the edge.
  * DuelHistory — every career match adds the flank duels it played: one
    global row per (attacker, defender) pair. The counts are capped
    (duel_service.save_log), so old results fade and recent ones matter.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, utcnow


class PlayerRivalry(TimestampMixin, Base):
    __tablename__ = "player_rivalries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attacker_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    defender_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # Names as the admin picked them (for the list; the keys decide).
    attacker_name: Mapped[str] = mapped_column(String(128), nullable=False)
    defender_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # -3..+3: negative = the defender dominates the attacker.
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    __table_args__ = (UniqueConstraint("attacker_key", "defender_key", name="uq_player_rivalries_pair"),)


class DuelHistory(Base):
    __tablename__ = "duel_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attacker_key: Mapped[str] = mapped_column(String(128), nullable=False)
    defender_key: Mapped[str] = mapped_column(String(128), nullable=False)
    attacker_wins: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    defender_wins: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("attacker_key", "defender_key", name="uq_duel_history_pair"),)
