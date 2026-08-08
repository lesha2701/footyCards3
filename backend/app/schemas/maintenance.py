from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class MaintenanceStatusOut(BaseModel):
    active: bool
    until: Optional[datetime] = None
