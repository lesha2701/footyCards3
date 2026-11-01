from typing import Literal, Optional

from pydantic import BaseModel, Field


class ManagerFoundIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class ManagerClubUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=64)
    formation: Optional[str] = Field(default=None, max_length=8)
    style: Optional[str] = Field(default=None, max_length=16)
    academy_card_id: Optional[int] = None
    clear_academy: bool = False


class ManagerOfferIn(BaseModel):
    user_id: int
    wage: int = Field(ge=0)
    seasons: int = 1
    fee: int = Field(default=0, ge=0)
    kind: Optional[Literal["sign", "transfer", "loan"]] = None


class ManagerRespondIn(BaseModel):
    accept: bool


class ManagerMarketIn(BaseModel):
    open: bool


class ManagerNpcIn(BaseModel):
    player_id: int
    kind: Literal["buy", "loan"]
    seasons: int = 1


class ManagerLookIn(BaseModel):
    shape: Optional[str] = Field(default=None, max_length=32)
    symbol: Optional[str] = Field(default=None, max_length=32)
    color: Optional[str] = Field(default=None, max_length=16)
    color2: Optional[str] = Field(default=None, max_length=16)
    kit: Optional[str] = Field(default=None, max_length=32)
    kit_color: Optional[str] = Field(default=None, max_length=16)
    kit_color2: Optional[str] = Field(default=None, max_length=16)
    frame: Optional[str] = Field(default=None, max_length=32)
    theme: Optional[str] = Field(default=None, max_length=32)
    rim: Optional[str] = Field(default=None, max_length=32)
    fx: Optional[str] = Field(default=None, max_length=32)


class ManagerStadiumNameIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=64)


class ManagerDealIn(BaseModel):
    option: Optional[str] = Field(default=None, max_length=32)
    seasons: int = Field(default=1, ge=1, le=10)
    amount: Optional[int] = Field(default=None, ge=0)


class ManagerTicketsIn(BaseModel):
    pct: int = Field(ge=0, le=1000)


class ManagerPlanIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)


class ManagerEventChoiceIn(BaseModel):
    option: str = Field(min_length=1, max_length=32)


class ManagerLoanIn(BaseModel):
    amount: int = Field(ge=0)
    seasons: int = Field(default=1, ge=1, le=10)


class ManagerRepayIn(BaseModel):
    amount: Optional[int] = Field(default=None, ge=0)


class ManagerSharesIn(BaseModel):
    shares: int = Field(ge=1, le=100_000)


class ManagerShareListIn(BaseModel):
    shares: int = Field(ge=0, le=100_000)
    price: int = Field(ge=0, le=10_000_000_000)


class ManagerBondIssueIn(BaseModel):
    units: int = Field(ge=1, le=10_000)
    rate_pct: float = Field(ge=0, le=100)
    seasons: int = Field(default=1, ge=1, le=10)


class ManagerBondBuyIn(BaseModel):
    units: int = Field(ge=1, le=10_000)
