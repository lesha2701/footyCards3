from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.stadium import Stadium
from app.schemas.stadium import StadiumCreate, StadiumUpdate


async def get_stadium_or_404(db: AsyncSession, stadium_id: int) -> Stadium:
    stadium = await db.get(Stadium, stadium_id)
    if not stadium:
        raise NotFoundError("Stadium not found")
    return stadium


async def create_stadium(db: AsyncSession, payload: StadiumCreate) -> Stadium:
    stadium = Stadium(**payload.model_dump())
    db.add(stadium)
    await db.flush()
    return stadium


async def update_stadium(db: AsyncSession, stadium_id: int, payload: StadiumUpdate) -> Stadium:
    stadium = await get_stadium_or_404(db, stadium_id)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(stadium, key, value)
    db.add(stadium)
    await db.flush()
    return stadium
