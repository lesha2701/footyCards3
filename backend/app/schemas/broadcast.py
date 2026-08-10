from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UpdateBroadcastStatusOut(BaseModel):
    broadcast_at: Optional[datetime] = None


class AdminBroadcastCreate(BaseModel):
    message: str = Field(min_length=1, max_length=1024)


class AdminBroadcastOut(BaseModel):
    recipients: int
    broadcast_at: datetime
