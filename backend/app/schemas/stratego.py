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
    is_my_player: bool = False
    # Card skill that counts in Stratego fights (attack or defence bonus).
    skill_name: Optional[str] = None
    skill_level: Optional[int] = None
    skill_kind: Optional[Literal["atk", "def"]] = None
    skill_bonus: int = 0


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
    # max_legendary / max_diamond / min_rare / min_common for the UI counters.
    rarity_limits: dict[str, int] = {}
    # Highest rarity allowed on a Подкатчик slot (kept for older clients).
    tackler_max_rarity: str = "diamond"
    # Highest rarity per capped role (tackler / provocateur / speedster).
    role_max_rarity: dict[str, str] = {}
    # Rarity rules the current picks break (empty = valid); blocks play.
    violations: list[str] = []
    options: list[StrategoCardOut]


class StrategoSquadSetRequest(BaseModel):
    cards: dict[str, int]
    layout: dict[str, list[int]]


class StrategoInfoOut(BaseModel):
    board_size: int
    wall_count: int
    regular_count: int
    tackler_count: int
    speedster_count: int
    move_limit: int
    move_timeout_hours: int
    challenge_expiry_hours: int
    max_auto_moves: int
    reward_win: int
    reward_draw: int
    reward_loss: int
    daily_limit: int
    rewarded_today: int
    max_legendary: int = 0
    max_diamond: int = 0
    min_rare: int = 0
    min_common: int = 0
    my_player_xp: int = 0
    tackler_max_rarity: str = "diamond"
    role_max_rarity: dict[str, str] = {}
    easy_reward_pct: int = 100
    live_move_seconds: int = 60
    skill_bonus_per_level: int = 0
    puzzle_reward: int = 0


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


class StrategoPuzzleBriefOut(BaseModel):
    code: str
    title: str
    description: str
    moves: int


class StrategoMatchOut(BaseModel):
    id: int
    mode: Literal["normal", "puzzle", "tutorial"] = "normal"
    difficulty: Optional[Literal["easy", "normal", "hard"]] = None
    # Matchmaking matches are played live (seconds per move, not hours).
    live: bool = False
    # Viewer's private marks on opponent pieces: piece_id -> tag.
    notes: dict[int, str] = {}
    # Two-square rule: the [from, to] pair the viewer may not play next.
    blocked_move: Optional[list[list[int]]] = None
    puzzle: Optional[StrategoPuzzleBriefOut] = None
    opponent_type: StrategoOpponentType
    opponent_name: str
    opponent_user_id: Optional[int] = None
    status: StrategoMatchStatus
    viewer_side: Literal["user", "opponent"]
    board_size: int
    # Impassable puddle cells, in the viewer's coordinates.
    lakes: list[list[int]] = []
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
    rating_delta: int = 0
    stake_coins: int = 0
    # XP «Мой игрок» earned in this match (0 if not fielded).
    my_player_xp: int = 0
    # Only filled in once the match is over — mid-match it would leak the
    # total power of the opponent's hidden pieces.
    my_strength: Optional[int] = None
    opponent_strength: Optional[int] = None
    created_at: datetime
    expires_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


class StrategoBotMatchRequest(BaseModel):
    difficulty: Literal["easy", "hard"] = "hard"


class StrategoNoteRequest(BaseModel):
    piece_id: int
    # None clears the mark.
    tag: Optional[Literal["cup", "wall", "star", "strong", "weak", "speedster"]] = None


class StrategoPuzzleOut(BaseModel):
    code: str
    title: str
    description: str
    moves: int
    reward: int
    solved_today: bool
    solved_total: int
    active_match_id: Optional[int] = None


class StrategoMoveRequest(BaseModel):
    from_row: int
    from_col: int
    to_row: int
    to_col: int


class StrategoChallengeRequest(BaseModel):
    receiver_id: int


class StrategoOpenChallengeRequest(BaseModel):
    stake_coins: int = 0


class StrategoOpenChallengePreviewOut(BaseModel):
    id: int
    creator_name: str
    stake_coins: int
    status: StrategoMatchStatus
    is_own_challenge: bool


class StrategoStatsOut(BaseModel):
    stratego_rating: int
    stratego_rank: Optional[int] = None


class StrategoSearchStatusOut(BaseModel):
    status: Literal["not_searching", "searching", "matched", "timeout"]
    match_id: Optional[int] = None
    created_at: Optional[datetime] = None
