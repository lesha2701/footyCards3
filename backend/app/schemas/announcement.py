from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AnnouncementOut(BaseModel):
    text: Optional[str] = None
    updated_at: Optional[datetime] = None


class AnnouncementUpdate(BaseModel):
    # Empty/whitespace-only text clears the banner.
    text: str = Field(max_length=500)
