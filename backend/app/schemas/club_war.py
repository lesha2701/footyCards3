from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

from app.models.enums import ClubLogoShape
from app.schemas.club_emblem import ClubEmblemOut


class ClubWarMemberOut(BaseModel):
    user_id: int
    name: str
    games: int
    packs: int
    tasks: int
    points: int
    # «Клубный ринг»: «Мордобой» wins over the other club's members (in points).
    ring_points: int = 0


class ClubWarSideOut(BaseModel):
    club_id: int
    name: str
    logo_shape: ClubLogoShape
    logo_color: str
    emblem: Optional[ClubEmblemOut] = None
    war_rating: int
    score: int
    # Live contributions while the war is on (empty once settled).
    members: list[ClubWarMemberOut]


class ClubWarSummaryOut(BaseModel):
    war_id: int
    opponent_name: str
    my_score: int
    opponent_score: int
    result: Literal["win", "loss", "draw"]
    ended_at: datetime


class ClubWarOut(BaseModel):
    enabled: bool
    # none: no war this week for the club; upcoming: starts_at is the next window.
    state: Literal["none", "upcoming", "active", "finished"]
    starts_at: datetime
    ends_at: datetime
    duration_hours: int
    min_members: int
    member_count: int
    war_rating: int
    win_budget: int
    draw_budget: int
    loss_budget: int
    win_member_coins: int
    war_id: Optional[int] = None
    me: Optional[ClubWarSideOut] = None
    opponent: Optional[ClubWarSideOut] = None
    result: Optional[Literal["win", "loss", "draw"]] = None
    history: list[ClubWarSummaryOut] = []


class ClubWarSweepResult(BaseModel):
    started: int
    settled: int
