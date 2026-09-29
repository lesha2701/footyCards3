from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import Rarity
from app.models.stadium import Stadium
from app.schemas.stadium import StadiumCreate, StadiumUpdate


async def get_stadium_or_404(db: AsyncSession, stadium_id: int) -> Stadium:
    stadium = await db.get(Stadium, stadium_id)
    if not stadium:
        raise NotFoundError("Stadium not found")
    return stadium


async def create_stadium(db: AsyncSession, payload: StadiumCreate) -> Stadium:
    # Stadium rarity can never be diamond (ck_stadiums_rarity_not_diamond) —
    # unlike Coach, there's no boosts list whose count-vs-rarity validation
    # naturally excludes diamond, so this must be checked explicitly here,
    # before the row ever reaches the DB constraint as a raw IntegrityError.
    if payload.rarity == Rarity.diamond:
        raise ConflictError("Stadium rarity cannot be diamond")
    stadium = Stadium(**payload.model_dump())
    db.add(stadium)
    await db.flush()
    return stadium


async def update_stadium(db: AsyncSession, stadium_id: int, payload: StadiumUpdate) -> Stadium:
    stadium = await get_stadium_or_404(db, stadium_id)
    # Same reasoning as create_stadium above: catch it before mutating the
    # row or hitting ck_stadiums_rarity_not_diamond as an unhandled 500.
    if payload.rarity == Rarity.diamond:
        raise ConflictError("Stadium rarity cannot be diamond")
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(stadium, key, value)
    db.add(stadium)
    await db.flush()
    return stadium
