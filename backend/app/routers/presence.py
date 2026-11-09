from typing import Optional

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.services import presence_service
from app.services.game_config_service import get_config

router = APIRouter(prefix="/presence", tags=["presence"])


class PresenceAnswerIn(BaseModel):
    token: str
    value: int


@router.get("")
async def get_presence(user: User = Depends(get_current_user)) -> Optional[dict]:
    """The open «Ты здесь?» check (null when there is none)."""
    return presence_service.view(user)


@router.get("/image/{token}")
async def presence_image(token: str, user: User = Depends(get_current_user)):
    return Response(content=presence_service.render(user, token), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.post("/answer")
async def presence_answer(
    payload: PresenceAnswerIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    await check_rate_limit(f"presence_answer:{user.id}", max_calls=20, window_seconds=60)
    return await presence_service.answer(db, user, payload.token, payload.value, await get_config(db))
