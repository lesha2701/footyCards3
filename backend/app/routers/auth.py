from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
from app.core.security import create_admin_token
from app.models.user import User
from app.schemas.user import AuthResponse, UserMeOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/session", response_model=AuthResponse)
async def create_session(user: User = Depends(get_current_user)):
    """Validates Telegram initData (or dev-mode header), upserts the user and
    returns the profile plus an admin JWT if the user is an administrator."""
    admin_token = create_admin_token(user.id, user.telegram_id) if user.is_admin else None
    return AuthResponse(user=UserMeOut.model_validate(user), admin_token=admin_token)


@router.get("/me", response_model=UserMeOut)
async def read_me(user: User = Depends(get_current_user)):
    return UserMeOut.model_validate(user)
