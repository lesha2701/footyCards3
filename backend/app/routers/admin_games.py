from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.database import get_db
from app.models.enums import GameSessionStatus, GameType
from app.models.game import GameSession
from app.models.match import Match
from app.models.user import User
from app.schemas.admin import GameConfigOut, GameConfigUpdate, SuspiciousMatchOut, SuspiciousMemorySessionOut
from app.services.admin_log_service import log_action
from app.services.game_config_service import get_config

router = APIRouter(prefix="/admin/games", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("/config", response_model=GameConfigOut)
async def read_config(db: AsyncSession = Depends(get_db)):
    return await get_config(db)


@router.put("/config", response_model=GameConfigOut)
async def update_config(payload: GameConfigUpdate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    config = await get_config(db)
    old_value = GameConfigOut.model_validate(config).model_dump(mode="json")
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(config, key, value)
    db.add(config)
    await log_action(db, admin.id, "update_game_config", "game_config", config.id, old_value=old_value, new_value=updates, ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(config)
    return config


@router.get("/suspicious-memory-sessions", response_model=list[SuspiciousMemorySessionOut])
async def suspicious_memory_sessions(db: AsyncSession = Depends(get_db)):
    config = await get_config(db)
    result = await db.execute(
        select(GameSession, User)
        .join(User, User.id == GameSession.user_id)
        .where(
            GameSession.game_type == GameType.memory_sequence,
            GameSession.score >= config.suspicious_memory_score_threshold,
        )
        .order_by(GameSession.score.desc())
        .limit(100)
    )
    rows = result.all()
    return [
        SuspiciousMemorySessionOut(
            session_id=s.id, user_id=u.id, username=u.username, score=s.score,
            reward_coins=s.reward_coins, created_at=s.created_at,
        )
        for s, u in rows
    ]


@router.get("/suspicious-matches", response_model=list[SuspiciousMatchOut])
async def suspicious_matches(db: AsyncSession = Depends(get_db)):
    config = await get_config(db)
    result = await db.execute(select(Match, User).join(User, User.id == Match.user_id).order_by(Match.created_at.desc()).limit(500))
    rows = result.all()
    suspicious = [
        SuspiciousMatchOut(
            match_id=m.id, user_id=u.id, username=u.username, user_score=m.user_score,
            opponent_score=m.opponent_score, reward_coins=m.reward_coins, created_at=m.created_at,
        )
        for m, u in rows
        if abs(m.user_score - m.opponent_score) >= config.suspicious_score_margin
    ]
    return suspicious[:100]
