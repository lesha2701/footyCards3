from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class FreePackStatusOut(BaseModel):
    available: bool
    available_at: Optional[datetime] = None
