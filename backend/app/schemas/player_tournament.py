from typing import Optional

from pydantic import BaseModel


class PlayerTournamentApplyResult(BaseModel):
    queued: bool
    tournament_id: Optional[int] = None
    queue_position: Optional[int] = None
    queue_size: int = 16


class PlayerTournamentCurrentOut(BaseModel):
    status: str  # "not_queued" | "queued" | "active" | "completed"
    queue_position: Optional[int] = None
    queue_size: int = 16
    tournament_id: Optional[int] = None
    can_apply: bool = False
