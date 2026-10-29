from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.card import UserCardOut


class AgentLicenseOut(BaseModel):
    """The viewer's «Агентская лицензия» and the terms to buy/extend it."""

    enabled: bool
    active: bool
    expires_at: Optional[datetime] = None
    revoked: bool = False
    stars: int
    days: int
    min_account_age_days: int
    requires_verified: bool
    # null = may buy/extend now.
    buy_block_reason: Optional[str] = None


class AdminAgentOut(BaseModel):
    user_id: int
    username: Optional[str]
    name: str
    active: bool
    expires_at: datetime
    first_bought_at: datetime
    purchases: int
    stars_total: int
    revoked_at: Optional[datetime] = None
    revoke_reason: Optional[str] = None
    is_banned: bool
    is_trade_banned: bool


class AdminAgentRevokeIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


class AuctionInfoOut(BaseModel):
    """Market rules for the Mini App (all from GameConfig) plus the viewer's
    own counters, so the UI never hardcodes an economy number."""

    enabled: bool
    durations_hours: list[int]
    fee_pct: int
    min_increment_pct: int
    min_increment_coins: int
    min_price: int
    max_active_lots: int
    snipe_window_seconds: int
    snipe_extend_seconds: int
    min_account_age_days: int
    my_active_lots: int
    # null = may bid/buy now; otherwise why not (ban / trade ban / new account).
    restriction: Optional[str] = None
    # «Агентская лицензия»: listing lots needs an active one.
    license: "AgentLicenseOut"
    server_now: datetime


class AuctionBidOut(BaseModel):
    id: int
    bidder_name: str
    is_mine: bool
    amount: int
    kind: str
    status: str
    created_at: datetime


class AuctionLotOut(BaseModel):
    id: int
    card: UserCardOut
    seller_id: int
    seller_name: str
    # Seller holds an active «Агентская лицензия» right now (badge «Агент»).
    seller_is_agent: bool = False
    status: str
    start_price: int
    buy_now_price: Optional[int]
    current_bid: Optional[int]
    bid_count: int
    # Smallest bid the server accepts right now (start price before the first bid).
    min_next_bid: int
    fee_pct: int
    duration_hours: int
    ends_at: datetime
    created_at: datetime
    closed_at: Optional[datetime]
    final_price: Optional[int]
    fee_amount: Optional[int]
    close_reason: Optional[str] = None
    is_mine: bool
    i_am_leading: bool
    i_won: bool
    # The viewer's own highest bid on this lot (null = never bid).
    my_max_bid: Optional[int] = None
    leader_name: Optional[str] = None
    server_now: datetime
    bids: Optional[list[AuctionBidOut]] = None


class AuctionLotListOut(BaseModel):
    items: list[AuctionLotOut]
    total: int


class AuctionLotCreateIn(BaseModel):
    user_card_id: int
    start_price: int = Field(gt=0, le=100_000_000)
    buy_now_price: Optional[int] = Field(default=None, gt=0, le=100_000_000)
    duration_hours: int = Field(gt=0)
    confirm_last_copy: bool = False


class AuctionPriceFloorOut(BaseModel):
    """Listing form: the copy's lowest start price (its card_value) and
    whether it may be listed at all (null reason = yes)."""

    user_card_id: int
    min_price: int
    valuable: bool
    block_reason: Optional[str] = None


class AuctionBidIn(BaseModel):
    amount: int = Field(gt=0, le=100_000_000)
    # Client-generated per tap; a retried request with the same key replays
    # instead of escrowing twice (unique (bidder_id, idempotency_key)).
    idempotency_key: str = Field(min_length=8, max_length=64)


class AuctionBuyNowIn(BaseModel):
    # The price the player saw — guards against buying after a change.
    expected_price: int = Field(gt=0)


class AuctionActionOut(BaseModel):
    lot: AuctionLotOut
    new_balance: int


class AdminAuctionRemoveIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


class AuctionSweepResult(BaseModel):
    closed: int


AuctionSort = Literal["ending", "newest", "price_asc", "price_desc"]
