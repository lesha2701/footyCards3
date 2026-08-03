from typing import Literal, Optional

from pydantic import BaseModel

from app.schemas.pack import PackOpenResult


class StarsInvoiceCreateOut(BaseModel):
    invoice_link: str
    payload_token: str
    stars_amount: int


class StarsInvoiceStatusOut(BaseModel):
    status: Literal["pending", "completed"]
    result: Optional[PackOpenResult] = None


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
