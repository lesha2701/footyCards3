from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.coach import Coach, CoachBoost
from app.models.enums import CoachBoostType, Rarity
from app.schemas.coach import CoachCreate, CoachUpdate, _validate_boost_types

# Spec §4 (docs/superpowers/specs/2026-09-08-coach-cards-design.md) — magnitude =
# base_unit * tier_index, tier_index = common:1, rare:2, epic:3, legendary:4. The
# single source of truth for boost magnitude: the admin panel no longer sends a
# magnitude at all, this derives it from (boost_type, coach's own rarity) so a
# wrong-scale value (e.g. typing "2" for a boost whose real scale tops out at 0.12)
# can no longer happen.
_TIER_INDEX_BY_RARITY: dict[Rarity, int] = {
    Rarity.common: 1, Rarity.rare: 2, Rarity.epic: 3, Rarity.legendary: 4,
}
_BASE_UNIT_BY_BOOST_TYPE: dict[CoachBoostType, float] = {
    CoachBoostType.ATTACK_CENTRAL: 2, CoachBoostType.ATTACK_WING: 2, CoachBoostType.MIDFIELD_CONTROL: 2,
    CoachBoostType.DEFENCE_CENTRAL: 2, CoachBoostType.DEFENCE_WING: 2, CoachBoostType.GOALKEEPING: 2,
    CoachBoostType.PASSING_ACCURACY: 1, CoachBoostType.SQUAD_STABILITY: 1,
    CoachBoostType.BALL_CONTROL: 0.03, CoachBoostType.DEFENSIVE_DISCIPLINE: 0.01, CoachBoostType.COUNTER_MASTERY: 0.1,
}


def magnitude_for(boost_type: CoachBoostType, rarity: Rarity) -> float:
    return round(_BASE_UNIT_BY_BOOST_TYPE[boost_type] * _TIER_INDEX_BY_RARITY[rarity], 3)


async def get_coach_or_404(db: AsyncSession, coach_id: int) -> Coach:
    coach = await db.get(Coach, coach_id)
    if not coach:
        raise NotFoundError("Coach not found")
    return coach


async def create_coach(db: AsyncSession, payload: CoachCreate) -> Coach:
    data = payload.model_dump(exclude={"boosts"})
    coach = Coach(**data)
    coach.boosts = [CoachBoost(boost_type=b.boost_type, magnitude=magnitude_for(b.boost_type, coach.rarity)) for b in payload.boosts]
    db.add(coach)
    await db.flush()
    await db.refresh(coach, attribute_names=["boosts"])
    return coach


async def update_coach(db: AsyncSession, coach_id: int, payload: CoachUpdate) -> Coach:
    coach = await get_coach_or_404(db, coach_id)

    # CoachUpdate's own Pydantic validator only fires when rarity and boosts
    # are BOTH submitted together — since this merges the payload into an
    # EXISTING row, either field alone must still be checked against the
    # coach's resulting (merged) state, or a partial update could silently
    # leave a rarity/boost-count mismatch (or hit the DB's raw
    # ck_coaches_rarity_not_diamond constraint as an unhandled 500). Validate
    # BEFORE mutating anything, so an invalid update never touches the coach
    # or the database at all.
    effective_rarity = payload.rarity if payload.rarity is not None else coach.rarity
    if payload.boosts is not None:
        effective_boost_types = [b.boost_type for b in payload.boosts]
    else:
        # get_coach_or_404 uses db.get(), which doesn't eager-load boosts —
        # refresh explicitly so this read doesn't trigger a lazy load
        # (unsupported under async SQLAlchemy, MissingGreenlet). Cheap/no-op
        # when the caller (e.g. the router) already refreshed this same
        # identity-mapped object.
        await db.refresh(coach, attribute_names=["boosts"])
        effective_boost_types = [b.boost_type for b in coach.boosts]
    try:
        _validate_boost_types(effective_rarity, effective_boost_types)
    except ValueError as exc:
        raise ConflictError(str(exc)) from exc

    updates = payload.model_dump(exclude_unset=True, exclude={"boosts"})
    for key, value in updates.items():
        setattr(coach, key, value)

    if payload.boosts is not None:
        # Replace-all: simplest correct semantics for "up to 3 rows" in an
        # admin-only phase — no per-boost PATCH exists yet.
        #
        # Two-phase on purpose: SQLAlchemy's unit-of-work flushes INSERT/UPDATE
        # before DELETE by default, so a single `coach.boosts = [new list]`
        # reassignment races the new rows' INSERT against the old rows'
        # delete-orphan DELETE. Whenever the new payload keeps at least one
        # boost_type that was already present (a very normal edit — e.g. the
        # admin only changes one of three slots), the new row's INSERT hits
        # uq_coach_boost_type_once before the old row is physically gone
        # (real Postgres bug, reproduced in production: coach_id=7 editing
        # while keeping 'passing_accuracy' raised UniqueViolationError).
        # Clearing and flushing first forces the DELETEs to land before any
        # new row referencing the same (coach_id, boost_type) is inserted.
        #
        # `coach.boosts` may not be loaded yet in this session (the branch
        # above only refreshes it when payload.boosts is None) — accessing
        # an unloaded collection to .clear() it would trigger an implicit
        # lazy-load, unsupported under async SQLAlchemy (MissingGreenlet).
        # Explicit refresh first makes this safe regardless of prior state.
        await db.refresh(coach, attribute_names=["boosts"])
        coach.boosts.clear()
        await db.flush()
        coach.boosts = [
            CoachBoost(boost_type=b.boost_type, magnitude=magnitude_for(b.boost_type, effective_rarity))
            for b in payload.boosts
        ]

    db.add(coach)
    await db.flush()
    await db.refresh(coach, attribute_names=["boosts"])
    return coach
