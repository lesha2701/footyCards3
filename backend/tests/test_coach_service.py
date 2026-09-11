import pytest

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import CoachBoostType, Rarity
from app.schemas.coach import CoachBoostCreate, CoachCreate, CoachUpdate
from app.services.coach_service import create_coach, update_coach


async def test_create_coach_persists_boosts(db_session):
    payload = CoachCreate(
        display_name="Service Test Coach", rarity=Rarity.epic,
        boosts=[
            CoachBoostCreate(boost_type=CoachBoostType.ATTACK_WING),
            CoachBoostCreate(boost_type=CoachBoostType.DEFENCE_WING),
        ],
    )
    coach = await create_coach(db_session, payload)
    assert coach.id is not None
    assert {b.boost_type for b in coach.boosts} == {CoachBoostType.ATTACK_WING, CoachBoostType.DEFENCE_WING}


async def test_update_coach_replaces_all_boosts(db_session):
    created = await create_coach(db_session, CoachCreate(
        display_name="Replaceable Coach", rarity=Rarity.common,
        boosts=[CoachBoostCreate(boost_type=CoachBoostType.GOALKEEPING)],
    ))

    updated = await update_coach(db_session, created.id, CoachUpdate(
        rarity=Rarity.common,
        boosts=[CoachBoostCreate(boost_type=CoachBoostType.PASSING_ACCURACY)],
    ))

    assert len(updated.boosts) == 1
    assert updated.boosts[0].boost_type == CoachBoostType.PASSING_ACCURACY


async def test_update_coach_without_boosts_leaves_them_untouched(db_session):
    created = await create_coach(db_session, CoachCreate(
        display_name="Partial Update Coach", rarity=Rarity.rare,
        boosts=[CoachBoostCreate(boost_type=CoachBoostType.BALL_CONTROL)],
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
            CoachBoostCreate(boost_type=CoachBoostType.ATTACK_WING),
            CoachBoostCreate(boost_type=CoachBoostType.DEFENCE_WING),
            CoachBoostCreate(boost_type=CoachBoostType.GOALKEEPING),
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
            CoachBoostCreate(boost_type=CoachBoostType.ATTACK_WING),
            CoachBoostCreate(boost_type=CoachBoostType.DEFENCE_WING),
            CoachBoostCreate(boost_type=CoachBoostType.GOALKEEPING),
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
            CoachBoostCreate(boost_type=CoachBoostType.ATTACK_WING),
            CoachBoostCreate(boost_type=CoachBoostType.DEFENCE_WING),
            CoachBoostCreate(boost_type=CoachBoostType.GOALKEEPING),
        ],
    ))

    with pytest.raises(ConflictError):
        await update_coach(db_session, created.id, CoachUpdate(
            boosts=[CoachBoostCreate(boost_type=CoachBoostType.ATTACK_WING)],
        ))


async def test_create_coach_derives_magnitude_from_rarity_tier(db_session):
    # Spec §4: magnitude = base_unit * tier_index. Same boost type
    # (ATTACK_CENTRAL, base_unit=2), different rarity -> different derived
    # magnitude, proving this is a genuine rarity-dependent computation and
    # not a hardcoded constant that happens to equal one of the two values.
    common_coach = await create_coach(db_session, CoachCreate(
        display_name="Common Attack Coach", rarity=Rarity.common,
        boosts=[CoachBoostCreate(boost_type=CoachBoostType.ATTACK_CENTRAL)],
    ))
    legendary_coach = await create_coach(db_session, CoachCreate(
        display_name="Legendary Attack Coach", rarity=Rarity.legendary,
        boosts=[
            CoachBoostCreate(boost_type=CoachBoostType.ATTACK_CENTRAL),
            CoachBoostCreate(boost_type=CoachBoostType.DEFENCE_CENTRAL),
            CoachBoostCreate(boost_type=CoachBoostType.GOALKEEPING),
        ],
    ))

    assert common_coach.boosts[0].magnitude == 2.0
    legendary_attack = next(b for b in legendary_coach.boosts if b.boost_type == CoachBoostType.ATTACK_CENTRAL)
    assert legendary_attack.magnitude == 8.0


async def test_create_coach_derives_small_multiplier_boost_on_its_own_scale(db_session):
    # BALL_CONTROL has base_unit 0.03 (not the 2-point rating-boost scale) —
    # confirms the small-multiplier boost types aren't accidentally sharing
    # the rating-point base_unit.
    coach = await create_coach(db_session, CoachCreate(
        display_name="Legendary Ball Control Coach", rarity=Rarity.legendary,
        boosts=[
            CoachBoostCreate(boost_type=CoachBoostType.BALL_CONTROL),
            CoachBoostCreate(boost_type=CoachBoostType.DEFENSIVE_DISCIPLINE),
            CoachBoostCreate(boost_type=CoachBoostType.COUNTER_MASTERY),
        ],
    ))

    ball_control = next(b for b in coach.boosts if b.boost_type == CoachBoostType.BALL_CONTROL)
    assert float(ball_control.magnitude) == pytest.approx(0.12)


async def test_update_coach_rederives_magnitude_from_new_rarity_when_both_change_together(db_session):
    # Upgrade a coach from common to legendary while ALSO changing its boost
    # type in the same call. The resulting magnitude must match the NEW
    # (legendary) rarity, not the coach's rarity at the start of the call —
    # this is the effective_rarity ordering concern: `updates` (which sets
    # coach.rarity) is applied before boosts are replaced, but the derivation
    # must use effective_rarity regardless of that ordering to be correct.
    created = await create_coach(db_session, CoachCreate(
        display_name="Upgradable Coach", rarity=Rarity.common,
        boosts=[CoachBoostCreate(boost_type=CoachBoostType.ATTACK_CENTRAL)],
    ))
    assert created.boosts[0].magnitude == 2.0  # common tier (1) * base_unit 2

    updated = await update_coach(db_session, created.id, CoachUpdate(
        rarity=Rarity.legendary,
        boosts=[
            CoachBoostCreate(boost_type=CoachBoostType.BALL_CONTROL),
            CoachBoostCreate(boost_type=CoachBoostType.DEFENSIVE_DISCIPLINE),
            CoachBoostCreate(boost_type=CoachBoostType.COUNTER_MASTERY),
        ],
    ))

    assert updated.rarity == Rarity.legendary
    ball_control = next(b for b in updated.boosts if b.boost_type == CoachBoostType.BALL_CONTROL)
    counter_mastery = next(b for b in updated.boosts if b.boost_type == CoachBoostType.COUNTER_MASTERY)
    # legendary tier (4): 0.03*4 = 0.12, 0.1*4 = 0.4 — NOT the common-tier
    # values (0.03, 0.1) the boost types would derive to at tier 1.
    assert float(ball_control.magnitude) == pytest.approx(0.12)
    assert float(counter_mastery.magnitude) == pytest.approx(0.4)
