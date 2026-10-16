from typing import Optional

from pydantic import BaseModel


class DayCount(BaseModel):
    date: str
    count: int


class ActivityOut(BaseModel):
    dau_today: int
    wau: int
    mau: int
    stickiness: Optional[float] = None
    active_in_period: int
    total_users: int
    dau_by_day: list[DayCount]
    registrations_by_day: list[DayCount]


class RetentionCohortOut(BaseModel):
    date: str
    size: int
    d1: Optional[float] = None
    d7: Optional[float] = None
    d30: Optional[float] = None


class RetentionSummaryOut(BaseModel):
    d1: Optional[float] = None
    d7: Optional[float] = None
    d30: Optional[float] = None
    d1_eligible: int
    d7_eligible: int
    d30_eligible: int


class RetentionOut(BaseModel):
    cohorts: list[RetentionCohortOut]
    summary: RetentionSummaryOut


class ModeRowOut(BaseModel):
    key: str
    label: str
    games: int
    players: int


class FunnelStepOut(BaseModel):
    key: str
    label: str
    users: int
    share: Optional[float] = None


class FunnelOut(BaseModel):
    cohort_size: int
    steps: list[FunnelStepOut]


class ProductRowOut(BaseModel):
    product: str
    stars: int
    purchases: int


class MonetizationOut(BaseModel):
    stars_total: int
    purchases: int
    payers: int
    paying_share: Optional[float] = None
    arppu: Optional[float] = None
    stars_by_day: list[DayCount]
    by_product: list[ProductRowOut]


class SuspiciousTradeRowOut(BaseModel):
    user_id: int
    telegram_id: Optional[int] = None
    name: str
    username: Optional[str] = None
    young_donors: int
    coins_received: int
    cards_received: int
    trades: int
    last_trade_at: Optional[str] = None


class SuspiciousTradesOut(BaseModel):
    young_days: int
    min_donors: int
    rows: list[SuspiciousTradeRowOut]


class AnalyticsReportOut(BaseModel):
    days: int
    today: str
    activity: ActivityOut
    retention: RetentionOut
    modes: list[ModeRowOut]
    funnel: FunnelOut
    monetization: MonetizationOut
    suspicious_trades: SuspiciousTradesOut
