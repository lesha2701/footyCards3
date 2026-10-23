from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class AntifraudAccountOut(BaseModel):
    id: int
    username: Optional[str] = None
    telegram_id: int
    balance: int
    registered: datetime
    last_seen: Optional[datetime] = None
    is_banned: bool
    stars_paid: int


class AntifraudHubOut(AntifraudAccountOut):
    senders: int
    coins_in: int
    coins_out: int


class AntifraudFarmOut(AntifraudAccountOut):
    coins_sent: int
    hubs: int
    is_hub: bool


class AntifraudSummaryOut(BaseModel):
    total: int
    not_banned: int
    not_banned_unpaid: int
    coins: int


class AntifraudBurstOut(BaseModel):
    hour: datetime
    registered: int
    farm_accounts: int


class AntifraudScanOut(BaseModel):
    min_senders: int
    days: int
    burst_min: int
    hubs: List[AntifraudHubOut]
    hubs_summary: AntifraudSummaryOut
    farms: List[AntifraudFarmOut]
    farms_summary: AntifraudSummaryOut
    bursts: List[AntifraudBurstOut]


class AntifraudBanIn(BaseModel):
    user_ids: List[int] = Field(min_length=1, max_length=5000)
    reason: str = Field(default="Антифрод: мультиаккаунты", max_length=200)


class AntifraudBanOut(BaseModel):
    banned: int
    user_ids: List[int]
