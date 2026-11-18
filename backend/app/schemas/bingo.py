from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import BingoGoalType
from app.schemas.pack import PackOpenResult


class BingoGoalOut(BaseModel):
    goal_type: BingoGoalType
    target_value: int
    current_value: int
    is_completed: bool


class BingoCardCellOut(BaseModel):
    metric: str
    label: str
    path: Optional[str] = None
    target: int
    value: int
    done: bool
    free: bool = False


class BingoCardOut(BaseModel):
    """The player's own 3×3 card (cells row by row, the centre free)."""
    cells: list[BingoCardCellOut]
    lines: list[list[int]]
    lines_done: list[int]
    lines_claimed: list[int]
    full_done: bool
    full_claimed: bool
    line_coins: int
    full_coins: int
    full_pack_name: Optional[str] = None
    # Coins waiting in POST /bingo/card/claim right now.
    claimable_coins: int = 0
    can_claim: bool = False
    # A closed line: the community reward is open to this player.
    community_eligible: bool = False


class BingoCurrentOut(BaseModel):
    is_enabled: bool
    week_number: Optional[int] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    goals: list[BingoGoalOut] = []
    all_goals_completed: bool = False
    # The reward, visible throughout the week so players know what they're
    # working toward — not just revealed once everything is done.
    reward_coins: int = 0
    reward_pack_id: Optional[int] = None
    reward_pack_name: Optional[str] = None
    reward_pack_image_path: Optional[str] = None
    # Whether the requesting user has already claimed this week's reward —
    # claiming is manual (POST /bingo/claim), never automatic.
    has_claimed: bool = False
    card: Optional[BingoCardOut] = None


class BingoClaimResult(BaseModel):
    coins_granted: int
    granted_pack: Optional[PackOpenResult] = None
    new_balance: int


class BingoStatsPreviewItem(BaseModel):
    goal_type: BingoGoalType
    trailing_7d_count: int


class BingoGoalDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    goal_type: BingoGoalType
    target_value: int
    is_active: bool


class BingoGoalDefinitionCreate(BaseModel):
    goal_type: BingoGoalType
    target_value: int = Field(ge=1)
    is_active: bool = True


class BingoGoalDefinitionUpdate(BaseModel):
    target_value: Optional[int] = Field(default=None, ge=1)
    is_active: Optional[bool] = None


class BingoStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    is_enabled: bool
    started_at: Optional[datetime] = None


class BingoStateUpdate(BaseModel):
    is_enabled: bool
