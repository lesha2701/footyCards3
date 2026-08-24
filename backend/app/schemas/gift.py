from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import GiftKind
from app.schemas.pack import PackOpenResult
from app.schemas.user import UserPublicOut


class GiftSetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    image_path: Optional[str] = None
    kind: GiftKind
    pack_id: Optional[int] = None
    coins_amount: int
    stars_price: int
    coins_price: int
    is_active: bool
    sort_order: int


class GiftSetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    kind: GiftKind = GiftKind.bundle
    pack_id: Optional[int] = None
    coins_amount: int = Field(default=0, ge=0)
    stars_price: int = Field(default=0, ge=0)
    coins_price: int = Field(default=0, ge=0)
    is_active: bool = True
    sort_order: int = 0


class GiftSetUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = None
    pack_id: Optional[int] = None
    coins_amount: Optional[int] = Field(default=None, ge=0)
    stars_price: Optional[int] = Field(default=None, ge=0)
    coins_price: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class GiftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    gift_set: GiftSetOut
    sender: Optional[UserPublicOut] = None
    message: Optional[str] = None
    is_admin_gift: bool
    is_pinned: bool
    claimed_at: Optional[datetime] = None
    created_at: datetime


class GiftClaimResult(BaseModel):
    gift: GiftOut
    pack_result: Optional[PackOpenResult] = None
    coins_credited: int = 0
    new_balance: int


class GiftPurchaseResult(BaseModel):
    gift: GiftOut
    new_balance: int


class GiftSendIn(BaseModel):
    gift_set_id: int
    recipient_id: int
    message: Optional[str] = Field(default=None, max_length=500)


class GiftBuyWithCoinsIn(BaseModel):
    recipient_id: int
    message: Optional[str] = Field(default=None, max_length=500)


class GiftPinIn(BaseModel):
    pinned: bool


class AdminGiftSendIn(BaseModel):
    gift_set_id: int
    user_id: int
    message: Optional[str] = Field(default=None, max_length=500)


class AdminGiftBroadcastIn(BaseModel):
    gift_set_id: int
    message: Optional[str] = Field(default=None, max_length=500)


class AdminGiftBroadcastOut(BaseModel):
    recipients: int
