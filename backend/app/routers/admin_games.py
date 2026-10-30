from types import SimpleNamespace

from datetime import datetime, timezone

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
from app.services import club_base_service, magnate_engine
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
    if updates.get("club_base_buildings") is not None:
        try:
            updates["club_base_buildings"] = club_base_service.validate_buildings(updates["club_base_buildings"])
        except ValueError as exc:
            raise ConflictError(f"Клубная база: {exc}")
    if updates.get("club_base_cosmetics") is not None:
        try:
            updates["club_base_cosmetics"] = club_base_service.validate_cosmetics(updates["club_base_cosmetics"])
        except (ValueError, TypeError) as exc:
            raise ConflictError(f"Клубная база, магазин стадиона: {exc}")
    if updates.get("club_base_caps") is not None:
        if any(v < 0 for v in updates["club_base_caps"].values()):
            raise ConflictError("Клубная база: потолки не могут быть отрицательными")
    if updates.get("my_player_sponsors") is not None or updates.get("my_player_sponsor_goals") is not None:
        from app.services import my_player_extras

        try:
            my_player_extras.validate_sponsors(
                updates.get("my_player_sponsors", config.my_player_sponsors),
                updates.get("my_player_sponsor_goals", config.my_player_sponsor_goals),
            )
        except (ValueError, TypeError, AttributeError) as exc:
            raise ConflictError(f"Спонсоры «Моего игрока»: {exc}")
    if updates.get("my_player_limited_supply") is not None:
        if any(int(v) < 0 for v in updates["my_player_limited_supply"].values()):
            raise ConflictError("Тираж не может быть отрицательным")
    # Switched on now: existing players' window starts from this moment.
    starter_for_all_started = bool(updates.get("starter_offer_for_all")) and not config.starter_offer_for_all
    artifact_keys = {"artifacts_enabled", "artifact_max_stat"}
    artifacts_before = {k: getattr(config, k) for k in artifact_keys}
    xp_curve_keys = ("my_player_xp_level_base", "my_player_xp_level_step")
    xp_curve_before = SimpleNamespace(**{k: getattr(config, k) for k in xp_curve_keys})
    for key, value in updates.items():
        setattr(config, key, value)
    if starter_for_all_started:
        config.starter_offer_all_since = datetime.now(timezone.utc)
    if any(getattr(config, k) != getattr(xp_curve_before, k) for k in xp_curve_keys):
        # «Мой игрок»: levels are derived from XP — keep everyone's level.
        from app.services import my_player_service

        await my_player_service.rebase_xp_curve(db, xp_curve_before, config)
    if any(getattr(config, k) != v for k, v in artifacts_before.items()):
        # Artifact card bonuses are stored on the cards: recompute them.
        from app.services import artifact_service

        await db.flush()
        await artifact_service.refresh_card_bonuses_for_artifact(db)
    if config.shop_daily_offer_pack_id == 0:
        config.shop_daily_offer_pack_id = None  # 0 from the admin form = rotate by date
    if config.club_pass_bonus_card_rarity == "":
        config.club_pass_bonus_card_rarity = None
    for key in ("club_card_exchange_pack_id", "club_pass_daily_pack_id", "club_pass_bonus_pack_id", "club_pass_frame_cosmetic_id", "club_pass_badge_id",
                "starter_offer_pack_id", "starter_offer_cosmetic_id", "club_raid_reward_pack_id",
                "newbie_finale_pack_id", "newbie_finale_badge_id"):
        if getattr(config, key) == 0:
            setattr(config, key, None)  # 0 from the admin form = none
    if "weekly_top_rewards" in updates:
        from app.services import reward_bundle_service
        from app.services.reward_bundle_service import Bundle

        ladder = []
        for row in updates["weekly_top_rewards"] or []:
            bundle = Bundle(**{k: (row.get(k) or None) for k in ("pack_id", "card_rarity", "badge_id", "cosmetic_id")},
                            coins=row.get("coins") or 0)
            await reward_bundle_service.validate(db, bundle)
            ladder.append({"coins": bundle.coins, "pack_id": bundle.pack_id,
                           "card_rarity": getattr(bundle.card_rarity, "value", bundle.card_rarity),
                           "badge_id": bundle.badge_id, "cosmetic_id": bundle.cosmetic_id})
        config.weekly_top_rewards = ladder
    if updates.get("streak_rewards") is not None:
        from app.services import reward_bundle_service
        from app.services.reward_bundle_service import Bundle

        rows = []
        for row in sorted(updates["streak_rewards"], key=lambda r: r["days"]):
            bundle = Bundle(**{k: (row.get(k) or None) for k in ("pack_id", "card_rarity", "badge_id", "cosmetic_id")},
                            coins=row.get("coins") or 0)
            await reward_bundle_service.validate(db, bundle)
            rows.append({"days": row["days"], "coins": bundle.coins, "pack_id": bundle.pack_id,
                         "card_rarity": getattr(bundle.card_rarity, "value", bundle.card_rarity),
                         "badge_id": bundle.badge_id, "cosmetic_id": bundle.cosmetic_id})
        if len({r["days"] for r in rows}) != len(rows):
            raise ConflictError("Награды за дни подряд: два порога с одинаковым числом дней")
        config.streak_rewards = rows
    if updates.get("referral_milestones") is not None:
        from app.services import reward_bundle_service
        from app.services.reward_bundle_service import Bundle

        rows = []
        for row in sorted(updates["referral_milestones"], key=lambda r: r["count"]):
            bundle = Bundle(**{k: (row.get(k) or None) for k in ("pack_id", "card_rarity", "badge_id", "cosmetic_id")},
                            coins=row.get("coins") or 0)
            await reward_bundle_service.validate(db, bundle)
            rows.append({"count": row["count"], "coins": bundle.coins, "pack_id": bundle.pack_id,
                         "card_rarity": getattr(bundle.card_rarity, "value", bundle.card_rarity),
                         "badge_id": bundle.badge_id, "cosmetic_id": bundle.cosmetic_id})
        if len({r["count"] for r in rows}) != len(rows):
            raise ConflictError("Рефералы: у двух наград одинаковое число друзей")
        config.referral_milestones = rows
    for key in ("newbie_squad_rarity", "newbie_arena_rarity", "newbie_day3_rarity"):
        if key in updates and updates[key] is not None:
            setattr(config, key, getattr(updates[key], "value", updates[key]))
    if updates.get("newbie_first_pack_rarities") is not None:
        config.newbie_first_pack_rarities = [getattr(r, "value", r) for r in updates["newbie_first_pack_rarities"]]
    if updates.get("newbie_tasks") is not None:
        from app.services import newbie_service

        codes = [t["code"] for t in updates["newbie_tasks"]]
        if len(set(codes)) != len(codes):
            raise ConflictError("Путь дебютанта: коды заданий должны быть разными")
        unknown = [t["mode"] for t in updates["newbie_tasks"] if t["mode"] not in newbie_service.known_modes()]
        if unknown:
            raise ConflictError(f"Путь дебютанта: неизвестный режим {unknown[0]}")
        config.newbie_tasks = updates["newbie_tasks"]
    if "weekly_top_metrics" in updates:
        from app.schemas.ranking import RankingMetric

        config.weekly_top_metrics = [m for m in updates["weekly_top_metrics"] or [] if m in RankingMetric.__members__]
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
    if any(key.startswith("equipment_") for key in updates):
        # The switch or a ceiling changed: rewrite what worn things give.
        from app.services import equipment_service

        await db.flush()
        await equipment_service.recompute_all(db)
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
