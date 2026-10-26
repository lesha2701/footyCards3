from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.gift import GiftOut
from app.schemas.pack import PackOpenResult
from app.schemas.wheel import WheelSpinResultOut


class StarsInvoiceCreateOut(BaseModel):
    invoice_link: str
    payload_token: str
    stars_amount: int


class StarsCoinResultOut(BaseModel):
    coins_credited: int
    new_balance: int


class StarsInvoiceStatusOut(BaseModel):
    status: Literal["pending", "completed"]
    result: Optional[PackOpenResult] = None
    coin_result: Optional[StarsCoinResultOut] = None
    gift_result: Optional[GiftOut] = None
    wheel_result: Optional[WheelSpinResultOut] = None
    # «Мой игрок» purchase: {"kind": "training" | "item", "name": ...}.
    my_player_result: Optional[dict] = None
    # «21» entry purchase: {"kind": "entry", "paid_entries": n}.
    blackjack_result: Optional[dict] = None
    # «Академия» attempt purchase: {"kind": "path_attempt", "user_card_id": n}.
    path_result: Optional[dict] = None
    # Monetization products (shop_product_service): {"kind": ..., ...}.
    shop_result: Optional[dict] = None


class StarsCoinInvoiceCreate(BaseModel):
    coin_package_id: int


class CoinPackageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stars_price: int
    coins_amount: int
    # «+N%» label; already included in coins_amount.
    bonus_pct: int = 0
    is_active: bool
    sort_order: int
    # Extra coins this player gets on it as their first coin purchase
    # (GameConfig.first_coin_purchase_bonus_pct; 0 once they have bought).
    first_purchase_bonus_coins: int = 0


class StarsPreCheckoutValidateIn(BaseModel):
    payload_token: str
    total_amount: int


class StarsPreCheckoutValidateOut(BaseModel):
    ok: bool
    error_message: Optional[str] = None


class StarsPaymentDeliverIn(BaseModel):
    payload_token: str
    telegram_user_id: int
    telegram_payment_charge_id: str
    total_amount: int
    # Telegram Stars subscriptions (club pass): when the paid period ends,
    # and whether this payment is a renewal. Absent on retries.
    subscription_expiration_date: Optional[int] = None
    is_recurring: bool = False
    is_first_recurring: bool = False
