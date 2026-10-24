import enum
from typing import Optional

from pydantic import BaseModel

from app.schemas.badge import BadgeOut


class RankingMetric(str, enum.Enum):
    arena_rating = "arena_rating"
    matches_won = "matches_won"
    cards_count = "cards_count"
    unique_players = "unique_players"
    referral_count = "referral_count"
    tactics_rating = "tactics_rating"
    penalty_rating = "penalty_rating"
    stratego_rating = "stratego_rating"
    stratego_puzzles = "stratego_puzzles"
    mordoboi_rating = "mordoboi_rating"
    kontra_rating = "kontra_rating"
    league_rating = "league_rating"
    academy_prestige = "academy_prestige"
    academy_level = "academy_level"
    base_level = "base_level"
    # This week only (Monday to Sunday, local time) — the «Топ недели»
    # nominations for activity rather than standing.
    games_week = "games_week"
    stars_week = "stars_week"
    referrals_week = "referrals_week"


class RankingEntry(BaseModel):
    rank: int
    user_id: int
    display_name: str
    avatar_url: Optional[str]
    value: int
    active_badge: Optional[BadgeOut] = None


class RankingOut(BaseModel):
    metric: RankingMetric
    top: list[RankingEntry]
    me: Optional[RankingEntry] = None
