from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ClubLogoShape

EmblemKind = Literal["color2", "pattern", "letters", "symbol", "outline", "effect"]
SponsorTier = Literal["bronze", "silver", "gold"]


class ClubEmblemOut(BaseModel):
    """The paid layers on top of logo_shape/logo_color — every field null
    means the plain one-colour logo."""
    color2: Optional[str] = None
    pattern: Optional[str] = None
    symbol: Optional[str] = None
    letters: Optional[str] = None
    outline: Optional[str] = None
    outline_thin: bool = False
    effect: Optional[str] = None


class ClubEmblemItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: EmblemKind
    style_key: str
    name: str
    coins_price: int
    stars_price: int
    is_active: bool
    sort_order: int


class ClubEmblemCatalogItemOut(ClubEmblemItemOut):
    unlocked: bool


class ClubEmblemStateOut(BaseModel):
    enabled: bool
    club_id: int
    logo_shape: ClubLogoShape
    logo_color: str
    emblem: ClubEmblemOut
    items: list[ClubEmblemCatalogItemOut]
    budget: int
    # «Звёзды клуба» — Stars items can be bought from it by budget spenders.
    star_balance: int = 0
    can_edit: bool
    can_spend_budget: bool


class ClubEmblemUpdateIn(BaseModel):
    logo_shape: ClubLogoShape
    logo_color: str = Field(pattern=r"^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")
    color2: Optional[str] = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    pattern: Optional[str] = Field(default=None, max_length=32)
    symbol: Optional[str] = Field(default=None, max_length=32)
    letters: Optional[str] = Field(default=None, max_length=3)
    outline: Optional[str] = Field(default=None, max_length=32)
    outline_thin: bool = False
    effect: Optional[str] = Field(default=None, max_length=32)


class ClubEmblemItemIn(BaseModel):
    """Admin edit of one catalog item — kind/style_key are fixed (the
    frontend draws them), only the shop side is editable."""
    name: str = Field(min_length=1, max_length=64)
    coins_price: int = Field(ge=0, le=10_000_000)
    stars_price: int = Field(ge=0, le=100_000)
    is_active: bool
    sort_order: int = 0


class ClubPatronOut(BaseModel):
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    avatar_url: Optional[str]
    stars: int
    coins: int
    tier: SponsorTier
    is_member: bool


class ClubDonationOut(BaseModel):
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    stars: int
    coins: int
    created_at: datetime


class ClubTreasuryOut(BaseModel):
    enabled: bool
    club_id: int
    budget: int
    star_balance: int = 0
    coins_per_star: int
    star_options: list[int]
    silver_stars: int
    gold_stars: int
    my_stars: int
    my_tier: Optional[SponsorTier]
    patrons: list[ClubPatronOut]
    recent: list[ClubDonationOut]


class ClubDonationInvoiceIn(BaseModel):
    stars: int = Field(ge=1, le=100_000)
    # "stars": onto the club's Stars balance; "coins": converted into the budget.
    target: Literal["stars", "coins"] = "coins"
