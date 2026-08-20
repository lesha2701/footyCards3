from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.feature_flags import FeatureFlagsOut
from app.services.game_config_service import get_config

router = APIRouter(tags=["feature-flags"])


@router.get("/feature-flags", response_model=FeatureFlagsOut)
async def read_feature_flags(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    config = await get_config(db)
    return FeatureFlagsOut(
        matchmaking_enabled=config.matchmaking_enabled,
        wheel_enabled=config.wheel_enabled,
        leagues_enabled=config.leagues_enabled,
    )
