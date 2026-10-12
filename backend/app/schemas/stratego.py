from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

from app.models.enums import MatchResult, StrategoMatchStatus, StrategoOpponentType

StrategoRole = Literal["cup", "wall", "star", "tackler", "provocateur", "speedster", "regular"]


class StrategoCardOut(BaseModel):
    """Snapshot of the card behind a piece — taken at match start, so a
    finished match still renders after the card is sold or traded."""

    user_card_id: Optional[int] = None
    player_id: int
    display_name: str
    position: str
    image_path: Optional[str] = None
    rarity: str
    rating: int


class StrategoSquadSlotOut(BaseModel):
    slot: str
    role: StrategoRole
    card: Optional[StrategoCardOut] = None
    # Positions that fit this role (None = any position). A non-fitting card
    # is accepted only when the player owns no fitting card at all.
    eligible_positions: Optional[list[str]] = None


class StrategoSquadOut(BaseModel):
    board_size: int
    slots: list[str]
    card_slots: list[StrategoSquadSlotOut]
    # slot -> [row, col] relative to the owner: row 0 = front, row 1 = back.
    layout: dict[str, list[int]]
    is_complete: bool
    cards_needed: int
    options: list[StrategoCardOut]


class StrategoSquadSetRequest(BaseModel):
    cards: dict[str, int]
    layout: dict[str, list[int]]


class StrategoInfoOut(BaseModel):
    board_size: int
    wall_count: int
    regular_count: int
    move_limit: int
    move_timeout_hours: int
    challenge_expiry_hours: int
    max_auto_moves: int
    reward_win: int
    reward_draw: int
    reward_loss: int
    daily_limit: int
    rewarded_today: int


class StrategoPieceOut(BaseModel):
    """A piece as seen by the viewer. For a hidden enemy piece only id,
    position and the public `moved` flag are filled in."""

    id: int
    mine: bool
    row: int
    col: int
    hidden: bool
    revealed: bool
    moved: bool
    role: Optional[StrategoRole] = None
    power: Optional[int] = None
    card: Optional[StrategoCardOut] = None


class StrategoCombatPieceOut(BaseModel):
    id: int
    mine: bool
    role: StrategoRole
    power: int
    card: Optional[StrategoCardOut] = None


class StrategoCombatOut(BaseModel):
    attacker: StrategoCombatPieceOut
    defender: StrategoCombatPieceOut
    survivor: Literal["attacker", "defender", "both"]


class StrategoMoveOut(BaseModel):
    ply: int
    mine: bool
    piece_id: int
    from_cell: list[int]
    to_cell: list[int]
    auto: bool
    combat: Optional[StrategoCombatOut] = None


class StrategoMatchOut(BaseModel):
    id: int
    opponent_type: StrategoOpponentType
    opponent_name: str
    opponent_user_id: Optional[int] = None
    status: StrategoMatchStatus
    viewer_side: Literal["user", "opponent"]
    board_size: int
    move_limit: int
    ply: int
    my_turn: bool
    deadline: Optional[datetime] = None
    my_auto_moves: int = 0
    max_auto_moves: int = 0
    pieces: list[StrategoPieceOut]
    lost_mine: list[StrategoCombatPieceOut]
    lost_opponent: list[StrategoCombatPieceOut]
    history: list[StrategoMoveOut]
    result: Optional[MatchResult] = None
    win_reason: Optional[str] = None
    reward_coins: int = 0
    # Only filled in once the match is over — mid-match it would leak the
    # total power of the opponent's hidden pieces.
    my_strength: Optional[int] = None
    opponent_strength: Optional[int] = None
    created_at: datetime
    expires_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


class StrategoMoveRequest(BaseModel):
    from_row: int
    from_col: int
    to_row: int
    to_col: int


class StrategoChallengeRequest(BaseModel):
    receiver_id: int


class StrategoSearchStatusOut(BaseModel):
    status: Literal["not_searching", "searching", "matched", "timeout"]
    match_id: Optional[int] = None
    created_at: Optional[datetime] = None
