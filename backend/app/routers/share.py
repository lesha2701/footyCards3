from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.share import SharePrepareIn, SharePrepareOut
from app.services import share_service

router = APIRouter(prefix="/share", tags=["share"])


@router.post("/prepare", response_model=SharePrepareOut)
async def prepare_share(
    body: SharePrepareIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Image + referral link for sharing one of the player's own moments
    (a legendary/diamond card, an Arena win, a trophy) to a Telegram chat."""
    await check_rate_limit(f"share_prepare:{user.id}", max_calls=10, window_seconds=60)
    return await share_service.prepare_share(db, user, body.kind, body.id)
