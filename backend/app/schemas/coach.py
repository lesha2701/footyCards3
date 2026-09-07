from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import CoachBoostType, Rarity

# Spec §4's rarity -> required boost count. A coach must have EXACTLY this
# many boosts, all of distinct CoachBoostType — not "up to N", since a
# coach with fewer boosts than its rarity allows would just be a worse
# version of a lower rarity, which is confusing rather than a deliberate
# design choice this admin tool should allow by accident.
BOOST_SLOTS_BY_RARITY: dict[Rarity, int] = {
    Rarity.common: 1,
    Rarity.rare: 1,
    Rarity.epic: 2,
    Rarity.legendary: 3,
}


class CoachBoostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    boost_type: CoachBoostType
    magnitude: float


class CoachBoostCreate(BaseModel):
    boost_type: CoachBoostType
    # Sane fat-finger guard only in this phase — see this plan's Global
    # Constraints: the real tuned magnitude table (spec §4) isn't enforced
    # here, since nothing reads this value yet.
    magnitude: float = Field(ge=-1.0, le=20.0)


def _validate_boosts(rarity: Rarity, boosts: list[CoachBoostCreate]) -> list[CoachBoostCreate]:
    if rarity not in BOOST_SLOTS_BY_RARITY:
        raise ValueError(f"Coach rarity must be one of {list(BOOST_SLOTS_BY_RARITY)}, got {rarity}")
    required = BOOST_SLOTS_BY_RARITY[rarity]
    if len(boosts) != required:
        raise ValueError(f"{rarity.value} coaches must have exactly {required} boost(s), got {len(boosts)}")
    types = [b.boost_type for b in boosts]
    if len(set(types)) != len(types):
        raise ValueError("A coach cannot have the same boost_type twice")
    return boosts


class CoachOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_name: str
    rarity: Rarity
    image_path: Optional[str]
    quick_sell_price: int
    is_active: bool
    is_pack_droppable: bool
    boosts: list[CoachBoostOut]


class CoachCreate(BaseModel):
    display_name: str
    rarity: Rarity
    quick_sell_price: int = Field(ge=0, default=10)
    is_active: bool = True
    is_pack_droppable: bool = True
    boosts: list[CoachBoostCreate]

    @model_validator(mode="after")
    def _check_boosts(self) -> "CoachCreate":
        _validate_boosts(self.rarity, self.boosts)
        return self


class CoachUpdate(BaseModel):
    display_name: Optional[str] = None
    rarity: Optional[Rarity] = None
    quick_sell_price: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None
    is_pack_droppable: Optional[bool] = None
    boosts: Optional[list[CoachBoostCreate]] = None

    @model_validator(mode="after")
    def _check_boosts(self) -> "CoachUpdate":
        # Only validate the rarity/boost-count pairing when BOTH are being
        # set together — partial updates (e.g. just toggling is_active)
        # must not require re-submitting the boost list every time.
        if self.rarity is not None and self.boosts is not None:
            _validate_boosts(self.rarity, self.boosts)
        return self
