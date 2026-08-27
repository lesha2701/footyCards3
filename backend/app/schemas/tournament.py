from typing import Optional

from pydantic import BaseModel


class TournamentApplyResult(BaseModel):
    queued: bool
    tournament_id: Optional[int] = None
    queue_position: Optional[int] = None
