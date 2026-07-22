from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import TradeStatus
from app.schemas.card import UserCardOut
from app.schemas.user import UserPublicOut


class TradeOfferCardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    card: UserCardOut
    side: str


class TradeOfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender: UserPublicOut
    receiver: UserPublicOut
    status: TradeStatus
    sender_coins: int
    receiver_coins: int
    message: Optional[str]
    offered_cards: list[UserCardOut]
    requested_cards: list[UserCardOut]
    expires_at: datetime
    resolved_at: Optional[datetime]
    created_at: datetime


class TradeCreateRequest(BaseModel):
    receiver_id: Optional[int] = None
    receiver_username: Optional[str] = None
    offered_card_ids: list[int] = Field(default_factory=list)
    requested_card_ids: list[int] = Field(default_factory=list)
    sender_coins: int = Field(default=0, ge=0)
    receiver_coins: int = Field(default=0, ge=0)
    message: Optional[str] = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def check_receiver_and_content(self):
        if not self.receiver_id and not self.receiver_username:
            raise ValueError("receiver_id or receiver_username is required")
        if not self.offered_card_ids and not self.requested_card_ids and not self.sender_coins and not self.receiver_coins:
            raise ValueError("Trade must include at least one card or coin amount")
        return self
