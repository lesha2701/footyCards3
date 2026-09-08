import pytest

from app.core.exceptions import ConflictError, NotFoundError
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


async def test_update_coach_rarity_only_rejects_mismatched_boost_count(db_session):
    # Existing legendary coach has 3 boosts; dropping to "common" alone
    # (common allows exactly 1 boost) must be rejected rather than left as
    # an inconsistent "common coach with 3 boosts" row.
    created = await create_coach(db_session, CoachCreate(
        display_name="Legendary Coach", rarity=Rarity.legendary,
        boosts=[
            CoachBoostCreate(boost_type=CoachBoostType.ATTACK_WING, magnitude=5.0),
            CoachBoostCreate(boost_type=CoachBoostType.DEFENCE_WING, magnitude=5.0),
            CoachBoostCreate(boost_type=CoachBoostType.GOALKEEPING, magnitude=3.0),
        ],
    ))

    with pytest.raises(ConflictError):
        await update_coach(db_session, created.id, CoachUpdate(rarity=Rarity.common))


async def test_update_coach_rarity_only_to_diamond_rejected_cleanly(db_session):
    # Coach rarity can never be diamond (ck_coaches_rarity_not_diamond) — the
    # schema layer has no boosts to check against on a rarity-only payload,
    # so this must be caught before it ever reaches the DB constraint as a
    # raw IntegrityError.
    created = await create_coach(db_session, CoachCreate(
        display_name="Almost Diamond Coach", rarity=Rarity.legendary,
        boosts=[
            CoachBoostCreate(boost_type=CoachBoostType.ATTACK_WING, magnitude=5.0),
            CoachBoostCreate(boost_type=CoachBoostType.DEFENCE_WING, magnitude=5.0),
            CoachBoostCreate(boost_type=CoachBoostType.GOALKEEPING, magnitude=3.0),
        ],
    ))

    with pytest.raises(ConflictError):
        await update_coach(db_session, created.id, CoachUpdate(rarity=Rarity.diamond))


async def test_update_coach_boosts_only_rejects_mismatched_count_for_current_rarity(db_session):
    # Existing legendary coach requires exactly 3 distinct boosts; submitting
    # a 1-boost list with no rarity change must be rejected, not silently
    # leave a legendary coach with only 1 boost.
    created = await create_coach(db_session, CoachCreate(
        display_name="Under-boosted After Update", rarity=Rarity.legendary,
        boosts=[
            CoachBoostCreate(boost_type=CoachBoostType.ATTACK_WING, magnitude=5.0),
            CoachBoostCreate(boost_type=CoachBoostType.DEFENCE_WING, magnitude=5.0),
            CoachBoostCreate(boost_type=CoachBoostType.GOALKEEPING, magnitude=3.0),
        ],
    ))

    with pytest.raises(ConflictError):
        await update_coach(db_session, created.id, CoachUpdate(
            boosts=[CoachBoostCreate(boost_type=CoachBoostType.ATTACK_WING, magnitude=5.0)],
        ))
