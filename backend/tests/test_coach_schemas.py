import pytest
from pydantic import ValidationError

from app.models.enums import CoachBoostType, Rarity
from app.schemas.coach import CoachBoostCreate, CoachCreate


def _boost(boost_type: CoachBoostType, magnitude: float = 2.0) -> CoachBoostCreate:
    return CoachBoostCreate(boost_type=boost_type, magnitude=magnitude)


def test_legendary_coach_needs_exactly_three_distinct_boosts():
    payload = CoachCreate(
        display_name="Legendary Coach", rarity=Rarity.legendary,
        boosts=[
            _boost(CoachBoostType.ATTACK_CENTRAL), _boost(CoachBoostType.DEFENCE_CENTRAL), _boost(CoachBoostType.GOALKEEPING),
        ],
    )
    assert len(payload.boosts) == 3


def test_legendary_coach_with_two_boosts_is_rejected():
    with pytest.raises(ValidationError):
        CoachCreate(
            display_name="Under-boosted Legendary", rarity=Rarity.legendary,
            boosts=[_boost(CoachBoostType.ATTACK_CENTRAL), _boost(CoachBoostType.DEFENCE_CENTRAL)],
        )


def test_epic_coach_with_three_boosts_is_rejected():
    with pytest.raises(ValidationError):
        CoachCreate(
            display_name="Over-boosted Epic", rarity=Rarity.epic,
            boosts=[
                _boost(CoachBoostType.ATTACK_CENTRAL), _boost(CoachBoostType.DEFENCE_CENTRAL), _boost(CoachBoostType.GOALKEEPING),
            ],
        )


def test_common_coach_needs_exactly_one_boost():
    payload = CoachCreate(display_name="Common Coach", rarity=Rarity.common, boosts=[_boost(CoachBoostType.PASSING_ACCURACY)])
    assert len(payload.boosts) == 1


def test_duplicate_boost_type_on_one_coach_is_rejected():
    with pytest.raises(ValidationError):
        CoachCreate(
            display_name="Duplicate Boost Coach", rarity=Rarity.rare,
            boosts=[_boost(CoachBoostType.ATTACK_CENTRAL), _boost(CoachBoostType.ATTACK_CENTRAL, magnitude=3.0)],
        )


def test_diamond_rarity_is_rejected_at_the_schema_layer():
    with pytest.raises(ValidationError):
        CoachCreate(display_name="Illegal Diamond", rarity=Rarity.diamond, boosts=[_boost(CoachBoostType.ATTACK_CENTRAL)])
