from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.pack import PackOpenResult


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


class StarsCoinInvoiceCreate(BaseModel):
    coin_package_id: int


class CoinPackageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stars_price: int
    coins_amount: int
    is_active: bool
    sort_order: int


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
