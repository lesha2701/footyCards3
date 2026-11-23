from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.services import section_time_service

router = APIRouter(prefix="/activity", tags=["activity"])


class SectionTimeIn(BaseModel):
    # {"play/penalty": 42, "home": 12}: seconds counted since the last batch.
    sections: dict[str, int] = Field(default_factory=dict, max_length=32)


@router.post("/time")
async def post_section_time(
    payload: SectionTimeIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
) -> dict:
    """The app's batch of active time per section (once a minute, and when
    the page goes away). Only for the admin report — it pays nothing."""
    await check_rate_limit(f"section_time:{user.id}", max_calls=3, window_seconds=60)
    stored = await section_time_service.record(db, user.id, payload.sections)
    return {"stored": stored}
