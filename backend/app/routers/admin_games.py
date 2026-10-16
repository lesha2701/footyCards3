from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import ConflictError
from app.database import get_db
from app.models.enums import GameType, MatchStatus
from app.models.game import GameSession
from app.models.match import Match
from app.models.user import User
from app.schemas.admin import GameConfigOut, GameConfigUpdate, SuspiciousMatchOut, SuspiciousMemorySessionOut
from app.services import magnate_engine
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
    try:
        if updates.get("magnate_board") is not None:
            updates["magnate_board"] = magnate_engine.validate_board(updates["magnate_board"])
        if updates.get("magnate_cards") is not None:
            updates["magnate_cards"] = magnate_engine.validate_cards(updates["magnate_cards"])
    except magnate_engine.EngineError as exc:
        raise ConflictError(f"Футбольный магнат: {exc}")
    for key, value in updates.items():
        setattr(config, key, value)
    if config.shop_daily_offer_pack_id == 0:
        config.shop_daily_offer_pack_id = None  # 0 from the admin form = rotate by date
    for key in ("club_pass_daily_pack_id", "club_pass_frame_cosmetic_id", "club_pass_badge_id",
                "starter_offer_pack_id", "starter_offer_cosmetic_id"):
        if getattr(config, key) == 0:
            setattr(config, key, None)  # 0 from the admin form = none
    if config.card_skill_probability_floor_pct >= config.card_skill_probability_ceiling_pct:
        await db.rollback()
        raise ConflictError("Нижняя граница вероятности навыков должна быть меньше верхней")
    stratego_pieces = (
        3 + config.stratego_wall_count + config.stratego_tackler_count  # cup + star + provocateur
        + config.stratego_speedster_count + config.stratego_regular_count
    )
    stratego_card_pieces = stratego_pieces - 1 - config.stratego_wall_count
    if config.stratego_min_rare_cards + config.stratego_min_common_cards > stratego_card_pieces:
        await db.rollback()
        raise ConflictError("Стратего: минимум редких + обычных больше, чем фишек-карт в составе")
    if stratego_pieces > 2 * config.stratego_board_size:
        await db.rollback()
        raise ConflictError("Стратего: все фишки должны помещаться в два ряда поля")
    db.add(config)
    await log_action(db, admin.id, "update_game_config", "game_config", config.id, old_value=old_value, new_value=updates, ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(config)
    return config


@router.get("/magnate-defaults")
async def magnate_defaults():
    """Built-in «Футбольный магнат» board and event cards — what the game
    uses while GameConfig.magnate_board / magnate_cards are NULL."""
    return {"board": magnate_engine.DEFAULT_BOARD, "cards": magnate_engine.DEFAULT_CARDS}


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
    result = await db.execute(
        select(Match, User)
        .join(User, User.id == Match.user_id)
        .where(Match.status == MatchStatus.finished)
        .order_by(Match.created_at.desc())
        .limit(500)
    )
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
