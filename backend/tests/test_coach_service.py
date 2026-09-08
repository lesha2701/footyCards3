import pytest

from app.core.exceptions import NotFoundError
from app.models.enums import CoachBoostType, Rarity
from app.schemas.coach import CoachBoostCreate, CoachCreate, CoachUpdate
from app.services.coach_service import create_coach, update_coach


async def test_create_coach_persists_boosts(db_session):
    payload = CoachCreate(
        display_name="Service Test Coach", rarity=Rarity.epic,
        boosts=[
            CoachBoostCreate(boost_type=CoachBoostType.ATTACK_WING, magnitude=4.0),
            CoachBoostCreate(boost_type=CoachBoostType.DEFENCE_WING, magnitude=4.0),
        ],
    )
    coach = await create_coach(db_session, payload)
    assert coach.id is not None
    assert {b.boost_type for b in coach.boosts} == {CoachBoostType.ATTACK_WING, CoachBoostType.DEFENCE_WING}


async def test_update_coach_replaces_all_boosts(db_session):
    created = await create_coach(db_session, CoachCreate(
        display_name="Replaceable Coach", rarity=Rarity.common,
        boosts=[CoachBoostCreate(boost_type=CoachBoostType.GOALKEEPING, magnitude=2.0)],
    ))

    updated = await update_coach(db_session, created.id, CoachUpdate(
        rarity=Rarity.common,
        boosts=[CoachBoostCreate(boost_type=CoachBoostType.PASSING_ACCURACY, magnitude=2.0)],
    ))

    assert len(updated.boosts) == 1
    assert updated.boosts[0].boost_type == CoachBoostType.PASSING_ACCURACY


async def test_update_coach_without_boosts_leaves_them_untouched(db_session):
    created = await create_coach(db_session, CoachCreate(
        display_name="Partial Update Coach", rarity=Rarity.rare,
        boosts=[CoachBoostCreate(boost_type=CoachBoostType.BALL_CONTROL, magnitude=1.0)],
    ))

    updated = await update_coach(db_session, created.id, CoachUpdate(is_active=False))

    assert updated.is_active is False
    assert len(updated.boosts) == 1
    assert updated.boosts[0].boost_type == CoachBoostType.BALL_CONTROL


async def test_update_missing_coach_raises_not_found(db_session):
    with pytest.raises(NotFoundError):
        await update_coach(db_session, 999999, CoachUpdate(is_active=False))
