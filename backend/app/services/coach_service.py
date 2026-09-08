from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.coach import Coach, CoachBoost
from app.schemas.coach import CoachCreate, CoachUpdate


async def _get_coach_or_404(db: AsyncSession, coach_id: int) -> Coach:
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
    coach = await _get_coach_or_404(db, coach_id)
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
