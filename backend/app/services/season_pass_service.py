"""«Сезонный пропуск»: seasons with start/end dates and levels reached by
XP. XP comes from playing — every rewarded game credits coins with one of
SEASON_XP_TX_TYPES, and wallet_service.credit_coins calls
`grant_reward_xp` (same hook as «Мой игрок» XP) — plus each login calendar
claim. Each level has a free reward and a premium reward; the premium track
is unlocked for the season with Telegram Stars, and rewards already earned
on it can be claimed right after buying."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.enums import CardSource, TransactionType
from app.models.game_config import GameConfig
from app.models.monetization import Season, SeasonClaim, SeasonLevel, SeasonProgress
from app.models.user import User
from app.schemas.monetization import (
    GrantedRewardsOut,
    RewardBundleIn,
    SeasonAdminOut,
    SeasonIn,
    SeasonLevelIn,
    SeasonLevelOut,
    SeasonPassOut,
)
from app.services import reward_bundle_service
from app.services.game_config_service import get_config
from app.services.reward_bundle_service import Bundle
from app.services.wallet_service import lock_user_for_update

SEASON_XP_TX_TYPES = frozenset({
    TransactionType.game_reward, TransactionType.match_reward, TransactionType.tactico_reward,
    TransactionType.career_reward, TransactionType.bingo_reward, TransactionType.player_tournament_match_reward,
    TransactionType.club_tournament_match_reward, TransactionType.stratego_reward, TransactionType.magnate_reward,
    TransactionType.my_player_duel_reward,
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def active_season(db: AsyncSession, now: Optional[datetime] = None) -> Optional[Season]:
    now = now or _now()
    return (await db.execute(
        select(Season).where(Season.is_active.is_(True), Season.starts_at <= now, Season.ends_at > now)
        .order_by(Season.starts_at.desc()).limit(1)
    )).scalar_one_or_none()


async def _progress(db: AsyncSession, user_id: int, season_id: int, create: bool = False) -> Optional[SeasonProgress]:
    row = (await db.execute(select(SeasonProgress).where(
        SeasonProgress.user_id == user_id, SeasonProgress.season_id == season_id,
    ))).scalar_one_or_none()
    if row is None and create:
        try:
            async with db.begin_nested():
                row = SeasonProgress(user_id=user_id, season_id=season_id, xp=0, is_premium=False)
                db.add(row)
                await db.flush()
        except IntegrityError:
            row = await _progress(db, user_id, season_id)
    return row


async def add_xp(db: AsyncSession, user_id: int, amount: int) -> int:
    """Adds season XP. Callers hold the user's row lock, so one player's XP
    updates are serialized. Returns the XP added (0 without a season)."""
    if amount <= 0:
        return 0
    season = await active_season(db)
    if season is None:
        return 0
    progress = await _progress(db, user_id, season.id, create=True)
    progress.xp += amount
    db.add(progress)
    return amount


async def grant_reward_xp(db: AsyncSession, user: User, tx_type: TransactionType, amount: int) -> int:
    """Hook for wallet_service.credit_coins: a rewarded game gives season XP.
    Reads the already-loaded config row (identity map), never creates it."""
    if amount <= 0 or tx_type not in SEASON_XP_TX_TYPES:
        return 0
    config = await db.get(GameConfig, 1)
    if config is None or not config.season_pass_enabled or not config.season_xp_per_game:
        return 0
    return await add_xp(db, user.id, config.season_xp_per_game)


async def add_xp_for_daily_claim(db: AsyncSession, user: User) -> int:
    config = await get_config(db)
    if not config.season_pass_enabled:
        return 0
    return await add_xp(db, user.id, config.season_xp_per_daily_claim)


async def _levels(db: AsyncSession, season_id: int) -> list[SeasonLevel]:
    return list((await db.execute(
        select(SeasonLevel).where(SeasonLevel.season_id == season_id).order_by(SeasonLevel.level)
    )).scalars())


async def get_pass(db: AsyncSession, user: User) -> SeasonPassOut:
    config = await get_config(db)
    season = await active_season(db) if config.season_pass_enabled else None
    if season is None:
        return SeasonPassOut(enabled=False)
    progress = await _progress(db, user.id, season.id)
    xp = progress.xp if progress else 0
    is_premium = bool(progress and progress.is_premium)
    levels = await _levels(db, season.id)
    claims = {(lvl, track) for lvl, track in (await db.execute(
        select(SeasonClaim.level_id, SeasonClaim.track).where(
            SeasonClaim.user_id == user.id, SeasonClaim.level_id.in_([lv.id for lv in levels] or [0]),
        )
    )).all()}
    out_levels = []
    claimable = locked_premium = 0
    for lv in levels:
        reached = xp >= lv.xp_required
        free, premium = Bundle.of(lv, "free_"), Bundle.of(lv, "premium_")
        free_claimed = (lv.id, "free") in claims
        premium_claimed = (lv.id, "premium") in claims
        if reached and not free.is_empty() and not free_claimed:
            claimable += 1
        if reached and not premium.is_empty() and not premium_claimed:
            if is_premium:
                claimable += 1
            else:
                locked_premium += 1
        out_levels.append(SeasonLevelOut(
            level=lv.level, xp_required=lv.xp_required, reached=reached,
            free=await reward_bundle_service.describe(db, free),
            premium=await reward_bundle_service.describe(db, premium),
            free_claimed=free_claimed, premium_claimed=premium_claimed,
        ))
    reached_levels = [lv.level for lv in levels if xp >= lv.xp_required]
    next_xp = next((lv.xp_required for lv in levels if xp < lv.xp_required), None)
    return SeasonPassOut(
        enabled=True, season_id=season.id, name=season.name, starts_at=season.starts_at, ends_at=season.ends_at,
        premium_stars=season.premium_stars, xp=xp, level=max(reached_levels, default=0), next_level_xp=next_xp,
        is_premium=is_premium, levels=out_levels, claimable=claimable, locked_premium=locked_premium,
        xp_per_game=config.season_xp_per_game, xp_per_daily_claim=config.season_xp_per_daily_claim,
    )


async def claim(db: AsyncSession, user: User, level: int, track: str) -> GrantedRewardsOut:
    season = await active_season(db)
    if season is None:
        raise ConflictError("Сезон сейчас не идёт")
    lv = (await db.execute(select(SeasonLevel).where(
        SeasonLevel.season_id == season.id, SeasonLevel.level == level,
    ))).scalar_one_or_none()
    if lv is None:
        raise NotFoundError("Уровень не найден")
    locked = await lock_user_for_update(db, user.id)
    progress = await _progress(db, locked.id, season.id)
    if progress is None or progress.xp < lv.xp_required:
        raise ConflictError("Этот уровень ещё не достигнут")
    if track == "premium" and not progress.is_premium:
        raise ConflictError("Премиум-награды открываются сезонным пропуском")
    bundle = Bundle.of(lv, f"{track}_")
    if bundle.is_empty():
        raise ConflictError("На этом уровне нет награды")
    try:
        async with db.begin_nested():
            db.add(SeasonClaim(user_id=locked.id, level_id=lv.id, track=track))
            await db.flush()
    except IntegrityError:
        raise ConflictError("Награда уже получена") from None
    granted = await reward_bundle_service.grant(
        db, locked, bundle, tx_type=TransactionType.season_pass_reward,
        description=f"Сезонный пропуск «{season.name}»: уровень {level}",
        card_source=CardSource.stars_purchase if track == "premium" else CardSource.game_reward,
        idempotency_prefix=f"season-{season.id}-{locked.id}-{level}-{track}", cosmetic_source="season_pass",
        related_object_type="season_level", related_object_id=lv.id,
    )
    await db.commit()
    await db.refresh(locked)
    granted.new_balance = locked.balance
    return granted


# --- Stars ("season_premium:<season_id>", see shop_product_service) -------------------


async def stars_order(db: AsyncSession, user: User) -> tuple[str, int, str, str]:
    season = await active_season(db)
    if season is None or not (await get_config(db)).season_pass_enabled:
        raise ConflictError("Сезон сейчас не идёт")
    progress = await _progress(db, user.id, season.id)
    if progress and progress.is_premium:
        raise ConflictError("Сезонный пропуск уже куплен")
    levels = await _levels(db, season.id)
    bundles = [Bundle.of(lv, "premium_") for lv in levels]
    coins = sum(b.coins for b in bundles)
    packs = sum(1 for b in bundles if b.pack_id)
    cards = sum(1 for b in bundles if b.card_rarity)
    extras = sum(1 for b in bundles if b.badge_id or b.cosmetic_id)
    parts = [f"{coins} монет"] if coins else []
    if packs:
        parts.append(f"паков: {packs}")
    if cards:
        parts.append(f"карточек: {cards}")
    if extras:
        parts.append(f"украшений: {extras}")
    return (
        f"season_premium:{season.id}", season.premium_stars, "Сезонный пропуск",
        f"Премиум-дорожка сезона «{season.name}» до {ensure_aware(season.ends_at):%d.%m}: "
        + (", ".join(parts) or "премиум-награды") + " за уровни сезона.",
    )


async def validate_stars(db: AsyncSession, user_id: int, season_id: int, stars_amount: int) -> tuple[bool, str]:
    season = await active_season(db)
    if season is None or season.id != season_id:
        return False, "Этот сезон уже закончился"
    if season.premium_stars != stars_amount:
        return False, "Цена пропуска изменилась — открой покупку заново"
    progress = await _progress(db, user_id, season_id)
    if progress and progress.is_premium:
        return False, "Сезонный пропуск уже куплен"
    return True, ""


async def deliver_stars(db: AsyncSession, user: User, season_id: int) -> dict:
    await lock_user_for_update(db, user.id)
    progress = await _progress(db, user.id, season_id, create=True)
    progress.is_premium = True
    progress.premium_at = progress.premium_at or _now()
    db.add(progress)
    season = await db.get(Season, season_id)
    return {"kind": "season_premium", "name": season.name if season else "Сезон"}


# --- admin ----------------------------------------------------------------------------


def _level_in(lv: SeasonLevel) -> SeasonLevelIn:
    return SeasonLevelIn(
        level=lv.level, xp_required=lv.xp_required,
        free=RewardBundleIn(**Bundle.of(lv, "free_").to_in().model_dump()),
        premium=RewardBundleIn(**Bundle.of(lv, "premium_").to_in().model_dump()),
    )


async def _admin_out(db: AsyncSession, season: Season) -> SeasonAdminOut:
    players, premium = (await db.execute(
        select(func.count(SeasonProgress.id), func.count(SeasonProgress.id).filter(SeasonProgress.is_premium.is_(True)))
        .where(SeasonProgress.season_id == season.id)
    )).one()
    return SeasonAdminOut(
        id=season.id, name=season.name, starts_at=season.starts_at, ends_at=season.ends_at,
        premium_stars=season.premium_stars, is_active=season.is_active,
        levels=[_level_in(lv) for lv in await _levels(db, season.id)], players=players, premium_players=premium,
    )


async def admin_list(db: AsyncSession) -> list[SeasonAdminOut]:
    seasons = (await db.execute(select(Season).order_by(Season.starts_at.desc()))).scalars().all()
    return [await _admin_out(db, s) for s in seasons]


async def _apply(db: AsyncSession, season: Season, data: SeasonIn) -> None:
    if ensure_aware(data.ends_at) <= ensure_aware(data.starts_at):
        raise ConflictError("Сезон должен заканчиваться позже, чем начинается")
    levels = sorted(data.levels, key=lambda lv: lv.level)
    if len({lv.level for lv in levels}) != len(levels):
        raise ConflictError("Номера уровней не должны повторяться")
    for prev, cur in zip(levels, levels[1:]):
        if cur.xp_required < prev.xp_required:
            raise ConflictError("Опыт для уровней должен расти")
    for lv in levels:
        await reward_bundle_service.validate(db, Bundle.from_in(lv.free))
        await reward_bundle_service.validate(db, Bundle.from_in(lv.premium))
    season.name, season.starts_at, season.ends_at = data.name, data.starts_at, data.ends_at
    season.premium_stars, season.is_active = data.premium_stars, data.is_active
    db.add(season)
    await db.flush()
    existing = {lv.level: lv for lv in await _levels(db, season.id)}
    for lv in levels:
        row = existing.pop(lv.level, None) or SeasonLevel(season_id=season.id, level=lv.level)
        row.xp_required = lv.xp_required
        for track, bundle in (("free", lv.free), ("premium", lv.premium)):
            for key, value in bundle.model_dump().items():
                setattr(row, f"{track}_{key}", value)
        db.add(row)
    for stale in existing.values():
        await db.delete(stale)


async def admin_create(db: AsyncSession, data: SeasonIn) -> SeasonAdminOut:
    season = Season()
    await _apply(db, season, data)
    await db.commit()
    return await _admin_out(db, season)


async def admin_update(db: AsyncSession, season_id: int, data: SeasonIn) -> SeasonAdminOut:
    season = await db.get(Season, season_id)
    if season is None:
        raise NotFoundError("Сезон не найден")
    await _apply(db, season, data)
    await db.commit()
    return await _admin_out(db, season)
