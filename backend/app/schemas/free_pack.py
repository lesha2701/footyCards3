from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.card import UserCardOut


class FreePackStatusOut(BaseModel):
    available: bool
    available_at: Optional[datetime] = None


class FreePackClaimOut(BaseModel):
    granted_pack_name: Optional[str] = None
    granted_card: Optional[UserCardOut] = None
    new_balance: int
    next_available_at: datetime
