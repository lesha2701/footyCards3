from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.coach import Coach, CoachBoost
from app.schemas.coach import CoachCreate, CoachUpdate, _validate_boost_types


async def get_coach_or_404(db: AsyncSession, coach_id: int) -> Coach:
    coach = await db.get(Coach, coach_id)
    if not coach:
        raise NotFoundError("Coach not found")
    return coach


async def create_coach(db: AsyncSession, payload: CoachCreate) -> Coach:
    data = payload.model_dump(exclude={"boosts"})
    coach = Coach(**data)
    coach.boosts = [CoachBoost(boost_type=b.boost_type, magnitude=b.magnitude) for b in payload.boosts]
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
        coach.boosts = [CoachBoost(boost_type=b.boost_type, magnitude=b.magnitude) for b in payload.boosts]

    db.add(coach)
    await db.flush()
    await db.refresh(coach, attribute_names=["boosts"])
    return coach
