from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.enums import MatchDifficulty, MatchResult, MatchStatus
from app.database import Base
from app.models.mixins import utcnow


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    opponent_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    opponent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    difficulty: Mapped[MatchDifficulty] = mapped_column(
        Enum(MatchDifficulty, name="match_difficulty_enum"), nullable=False
    )
    user_team_strength: Mapped[int] = mapped_column(Integer, nullable=False)
    opponent_team_strength: Mapped[int] = mapped_column(Integer, nullable=False)
    user_score: Mapped[int] = mapped_column(Integer, nullable=False)
    opponent_score: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[MatchStatus] = mapped_column(
        Enum(MatchStatus, name="match_status_enum"), default=MatchStatus.finished, nullable=False
    )
    result: Mapped[Optional[MatchResult]] = mapped_column(Enum(MatchResult, name="match_result_enum"), nullable=True)
    reward_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rating_delta: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lineup_id: Mapped[Optional[int]] = mapped_column(ForeignKey("lineups.id", ondelete="SET NULL"), nullable=True)
    server_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    events: Mapped[list["MatchEvent"]] = relationship(back_populates="match", cascade="all, delete-orphan")

    @property
    def pending_shot(self) -> Optional[dict]:
        if self.status != MatchStatus.in_progress or not self.server_state:
            return None
        moments = self.server_state.get("moments", [])
        i = self.server_state.get("next_index", 0)
        if i >= len(moments):
            return None
        moment = moments[i]
        if moment.get("kind") != "shot":
            return None
        if moment["team"] == "opponent" and moment["shot_type"] == "empty_net":
            return None
        return {"team": moment["team"], "shot_type": moment["shot_type"], "seq": i}


class MatchEvent(Base):
    __tablename__ = "match_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True)
    minute: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    team: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    match: Mapped["Match"] = relationship(back_populates="events")
