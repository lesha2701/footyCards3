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


# Spec §4: most boosts are expressed in flat rating points (legendary tier
# tops out around 8), where the blanket [-1, 20] bound below is already a
# safe fat-finger guard. Three boosts are additive to a small multiplier
# instead (BALL_CONTROL -> INITIATIVE_MULT, DEFENSIVE_DISCIPLINE ->
# MENTALITY_DEFENSE_SHIFT, COUNTER_MASTERY -> TRANSITION_BONUS) with
# legendary tiers of 0.12/0.04/0.4 respectively — the same blanket bound
# would let an admin fat-finger a rating-point-sized number (e.g. "2")
# into one of these and multiply a whole match phase by an order of
# magnitude nobody intended. Bounds below give ~2.5x headroom over the
# spec's current legendary tier for each, not a hard lock to those
# placeholder numbers (spec §4 itself says they're not final).
_TIGHT_MAGNITUDE_BOUNDS: dict[CoachBoostType, tuple[float, float]] = {
    CoachBoostType.BALL_CONTROL: (-0.3, 0.3),
    CoachBoostType.DEFENSIVE_DISCIPLINE: (-0.1, 0.1),
    CoachBoostType.COUNTER_MASTERY: (-1.0, 1.0),
}


class CoachBoostCreate(BaseModel):
    boost_type: CoachBoostType
    # Blanket fat-finger guard for the 8 rating-point-scale boost types
    # (zone boosts, SQUAD_STABILITY, PASSING_ACCURACY) — the real tuned
    # magnitude table (spec §4) isn't enforced number-for-number here.
    # The 3 small-multiplier boost types get a tighter, type-specific
    # bound instead, see _TIGHT_MAGNITUDE_BOUNDS and _check_magnitude below.
    magnitude: float = Field(ge=-1.0, le=20.0)

    @model_validator(mode="after")
    def _check_magnitude(self) -> "CoachBoostCreate":
        bounds = _TIGHT_MAGNITUDE_BOUNDS.get(self.boost_type)
        if bounds is not None:
            lo, hi = bounds
            if not (lo <= self.magnitude <= hi):
                raise ValueError(
                    f"magnitude for {self.boost_type.value} must be between {lo} and {hi} "
                    f"(this boost is additive to a small multiplier, not a rating-point value), got {self.magnitude}"
                )
        return self


def _validate_boost_types(rarity: Rarity, boost_types: list[CoachBoostType]) -> None:
    """Lower-level check that only needs the boost TYPES, not full
    CoachBoostCreate objects with magnitudes — so it's reusable from the
    service layer, where an "effective" (post-update) boost list may be a
    mix of existing ORM CoachBoost rows and/or new CoachBoostCreate payload
    objects, both of which expose a `.boost_type` attribute."""
    if rarity not in BOOST_SLOTS_BY_RARITY:
        raise ValueError(f"Coach rarity must be one of {list(BOOST_SLOTS_BY_RARITY)}, got {rarity}")
    required = BOOST_SLOTS_BY_RARITY[rarity]
    if len(boost_types) != required:
        raise ValueError(f"{rarity.value} coaches must have exactly {required} boost(s), got {len(boost_types)}")
    if len(set(boost_types)) != len(boost_types):
        raise ValueError("A coach cannot have the same boost_type twice")


def _validate_boosts(rarity: Rarity, boosts: list[CoachBoostCreate]) -> list[CoachBoostCreate]:
    _validate_boost_types(rarity, [b.boost_type for b in boosts])
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
