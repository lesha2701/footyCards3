import pytest
from sqlalchemy.exc import IntegrityError

from app.models.coach import Coach, CoachBoost
from app.models.enums import CoachBoostType, Rarity


async def test_coach_with_boosts_persists(db_session):
    coach = Coach(display_name="Test Coach", rarity=Rarity.legendary)
    coach.boosts = [
        CoachBoost(boost_type=CoachBoostType.ATTACK_CENTRAL, magnitude=4.0),
        CoachBoost(boost_type=CoachBoostType.DEFENCE_CENTRAL, magnitude=4.0),
        CoachBoost(boost_type=CoachBoostType.SQUAD_STABILITY, magnitude=2.0),
    ]
    db_session.add(coach)
    await db_session.commit()

    assert coach.id is not None
    assert len(coach.boosts) == 3
    assert coach.is_active is True
    assert coach.is_pack_droppable is True


async def test_coach_rarity_cannot_be_diamond(db_session):
    coach = Coach(display_name="Illegal Diamond Coach", rarity=Rarity.diamond)
    db_session.add(coach)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_coach_boost_type_unique_per_coach(db_session):
    coach = Coach(display_name="Duplicate Boost Coach", rarity=Rarity.common)
    coach.boosts = [
        CoachBoost(boost_type=CoachBoostType.ATTACK_CENTRAL, magnitude=2.0),
        CoachBoost(boost_type=CoachBoostType.ATTACK_CENTRAL, magnitude=3.0),
    ]
    db_session.add(coach)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_deleting_coach_cascades_to_boosts(db_session):
    coach = Coach(display_name="Deletable Coach", rarity=Rarity.rare)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=4.0)]
    db_session.add(coach)
    await db_session.commit()
    coach_id = coach.id

    await db_session.delete(coach)
    await db_session.commit()

    from sqlalchemy import select
    result = await db_session.execute(select(CoachBoost).where(CoachBoost.coach_id == coach_id))
    assert result.scalars().all() == []
