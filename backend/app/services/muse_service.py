"""«Музы»: companions that inspire the player's own footballer («Мой футболист»).

A Muse drops from packs (Pack.muse_drop_chance — the «Музы» pack has 0.1 per
slot, pack_service.roll_and_create_cards) and is kept in the player's
«Музы» album (one UserMuse per Muse; a repeat drop adds to `copies`, a spare
copy sells for GameConfig.muse_spare_coins[rarity]). One owned Muse is
active at a time — like a coach or an artifact, only she gives her bonus:
  * daily_coins      — +N coins once a day (claim_daily, one MuseDailyClaim
                       row per user per local day — switching Muses never
                       pays twice);
  * match_rating / attack / defense — +N to «Мой футболист» in matches;
  * shot_pp / dribble_pp — +N pp in the match engine (engine card boosts);
  * xp_bonus_pct     — +N% experience of «Мой футболист»;
  * freshness_regen  — +N freshness per hour.
my_player_service adds `effects_of` next to the artifact effects.

Gifts (MuseAccessory: bag, dress, cosmetics, …) are bought for one owned
Muse for coins or Stars ("muse_accessory:<user_muse_id>:<accessory_id>",
shop_product_service); each raises her bonus by `boost_pct` percent (sum
capped by muse_max_accessory_pct, the result by the per-effect ceilings).
A gift stays with that Muse. Every write locks the owner row first
(wallet_service.lock_user_for_update); coin purchases are idempotent via
(user_id, purchase_key). `muses_enabled=False` stops every bonus and closes
gifts, the claim and Muse drops.

«Свидание» (MuseDate): once a local day the player plays a random mini-game
(GameConfig.muse_date_games: memory / pairs / hangman) with the active
Muse. It is an extra attempt — the game's hourly and daily counters are not
touched (the game services call `begin_date` / `finish_date`); any result
counts. Finishing pays `muse_date_coins` and inspires the Muse for
`muse_inspiration_hours`; with `muse_date_required` her bonus (daily coins
included) works only while she is inspired.
"""
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.enums import Rarity, TransactionType
from app.models.game_config import GameConfig
from app.models.muse import Muse, MuseAccessory, MuseCollection, MuseDailyClaim, MuseDate, UserMuse, UserMuseAccessory
from app.models.user import User
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update

EFFECTS: dict[str, str] = {
    "daily_coins": "+{v} монет в день",
    "match_rating": "+{v} к рейтингу «Моего футболиста»",
    "attack": "+{v} к атаке",
    "defense": "+{v} к защите",
    "shot_pp": "+{v}% к точности удара",
    "dribble_pp": "+{v}% к обыгрышу 1 на 1",
    "xp_bonus_pct": "+{v}% опыта",
    "freshness_regen": "+{v} свежести в час",
}
KINDS: dict[str, str] = {
    "bag": "Сумка",
    "dress": "Платье",
    "swimsuit": "Купальник",
    "cosmetics": "Косметика",
    "jewelry": "Украшение",
    "shoes": "Туфли",
    "perfume": "Духи",
    "other": "Подарок",
}
RARITIES = ("common", "rare", "epic", "legendary")
# game -> (title, page)
DATE_GAMES: dict[str, tuple[str, str]] = {
    "memory": ("Memory Sequence", "/play/memory"),
    "pairs": ("Найди пару", "/play/pairs"),
    "hangman": ("Футбольные буквы", "/play/hangman"),
}
_STAT_EFFECTS = ("match_rating", "attack", "defense", "freshness_regen")
_PP_EFFECTS = ("shot_pp", "dribble_pp")


def effect_label(effect: str, value: int) -> str:
    return EFFECTS.get(effect, "").format(v=value)


def _cap(effect: str, value: int, config: GameConfig) -> int:
    if effect in _STAT_EFFECTS:
        return min(value, config.muse_max_stat)
    if effect in _PP_EFFECTS:
        return min(value, config.muse_max_pp)
    if effect == "xp_bonus_pct":
        return min(value, config.muse_max_xp_pct)
    if effect == "daily_coins":
        return min(value, config.muse_max_daily_coins)
    return value


def boosted_value(muse: Muse, boost_pct: int, config: GameConfig) -> int:
    """The Muse's bonus with her gifts: base × (100 + boost)%, rounded half
    up, then capped per effect."""
    boost = max(0, min(boost_pct, config.muse_max_accessory_pct))
    return _cap(muse.effect, (max(0, muse.effect_value) * (100 + boost) + 50) // 100, config)


def spare_coins(config: GameConfig, rarity: str) -> int:
    return int((config.muse_spare_coins or {}).get(rarity, 0) or 0)


async def _gifts(db: AsyncSession, user_id: int) -> dict[int, list[UserMuseAccessory]]:
    rows = (await db.execute(
        select(UserMuseAccessory).where(UserMuseAccessory.user_id == user_id).order_by(UserMuseAccessory.id)
    )).unique().scalars().all()
    out: dict[int, list[UserMuseAccessory]] = {}
    for row in rows:
        out.setdefault(row.user_muse_id, []).append(row)
    return out


def _boost_of(gifts: list[UserMuseAccessory]) -> int:
    return sum(max(0, g.accessory.boost_pct) for g in gifts)


async def _active(db: AsyncSession, user_id: int) -> Optional[UserMuse]:
    return (await db.execute(
        select(UserMuse).where(UserMuse.user_id == user_id, UserMuse.is_active.is_(True))
    )).unique().scalar_one_or_none()


async def effects_of(db: AsyncSession, user_id: int, config: Optional[GameConfig] = None) -> dict[str, int]:
    """What the active Muse gives right now: {effect: value} (one effect)."""
    config = config or await get_config(db)
    if not config.muses_enabled:
        return {}
    row = await _active(db, user_id)
    if row is None or not row.muse.is_active:
        return {}
    if config.muse_date_required and await inspired_until(db, user_id, config) is None:
        return {}
    gifts = (await _gifts(db, user_id)).get(row.id, [])
    value = boosted_value(row.muse, _boost_of(gifts), config)
    return {row.muse.effect: value} if value > 0 else {}


async def inspired_until(db: AsyncSession, user_id: int, config: GameConfig, now: Optional[datetime] = None) -> Optional[datetime]:
    """When the last finished date stops inspiring her (None = not inspired now)."""
    now = now or datetime.now(timezone.utc)
    last = (await db.execute(
        select(MuseDate.completed_at).where(MuseDate.user_id == user_id, MuseDate.completed_at.is_not(None))
        .order_by(MuseDate.completed_at.desc()).limit(1)
    )).scalar_one_or_none()
    if last is None:
        return None
    until = ensure_aware(last) + timedelta(hours=config.muse_inspiration_hours)
    return until if until > now else None


# --- views ---------------------------------------------------------------------------------


def muse_out(muse: Muse, config: GameConfig, owned: Optional[UserMuse] = None,
             gifts: Optional[list[UserMuseAccessory]] = None) -> dict:
    gifts = gifts or []
    boost = min(_boost_of(gifts), config.muse_max_accessory_pct)
    value = boosted_value(muse, boost, config) if owned else muse.effect_value
    return {
        "id": muse.id, "name": muse.name, "title": muse.title, "description": muse.description,
        "icon": muse.icon, "image_path": muse.image_path, "rarity": muse.rarity,
        "collection_id": muse.collection_id,
        "effect": muse.effect, "effect_value": muse.effect_value, "effect_label": effect_label(muse.effect, value),
        "base_effect_label": effect_label(muse.effect, muse.effect_value),
        "boosted_value": value, "boost_pct": boost,
        "owned": owned is not None, "user_muse_id": owned.id if owned else None,
        "copies": owned.copies if owned else 0, "is_active": bool(owned and owned.is_active),
        "accessory_ids": [g.accessory_id for g in gifts],
        "spare_coins": spare_coins(config, muse.rarity),
    }


def accessory_out(accessory: MuseAccessory) -> dict:
    return {
        "id": accessory.id, "name": accessory.name, "description": accessory.description, "icon": accessory.icon,
        "image_path": accessory.image_path, "kind": accessory.kind, "kind_label": KINDS.get(accessory.kind, "Подарок"),
        "rarity": accessory.rarity, "boost_pct": accessory.boost_pct,
        "coins_price": accessory.coins_price, "stars_price": accessory.stars_price,
    }


def collection_out(collection: MuseCollection) -> dict:
    return {
        "id": collection.id, "name": collection.name, "description": collection.description,
        "image_path": collection.image_path,
    }


async def _claimed_today(db: AsyncSession, user_id: int) -> Optional[MuseDailyClaim]:
    return (await db.execute(
        select(MuseDailyClaim).where(MuseDailyClaim.user_id == user_id, MuseDailyClaim.claim_date == local_today())
    )).scalar_one_or_none()


async def album(db: AsyncSession, user: User) -> dict:
    """The «Музы» page: every collection with its Muses (owned or not), the
    active Muse, today's daily claim and the gift catalog."""
    config = await get_config(db)
    collections = (await db.execute(
        select(MuseCollection).where(MuseCollection.is_active.is_(True))
        .order_by(MuseCollection.sort_order, MuseCollection.id)
    )).scalars().all()
    muses = (await db.execute(
        select(Muse).where(Muse.is_active.is_(True)).order_by(Muse.sort_order, Muse.id)
    )).unique().scalars().all()
    owned = {r.muse_id: r for r in (await db.execute(
        select(UserMuse).where(UserMuse.user_id == user.id)
    )).unique().scalars().all()}
    gifts = await _gifts(db, user.id)
    accessories = (await db.execute(
        select(MuseAccessory).where(MuseAccessory.is_active.is_(True))
        .order_by(MuseAccessory.sort_order, MuseAccessory.id)
    )).scalars().all()
    active_ids = {c.id for c in collections}

    def out(m: Muse) -> dict:
        row = owned.get(m.id)
        return muse_out(m, config, row, gifts.get(row.id, []) if row else None)

    groups = [
        {**collection_out(c), "muses": [out(m) for m in muses if m.collection_id == c.id]} for c in collections
    ]
    loose = [out(m) for m in muses if m.collection_id is None or m.collection_id not in active_ids]
    if loose:
        groups.append({"id": None, "name": "Другие музы", "description": None, "image_path": None, "muses": loose})
    active_row = next((r for r in owned.values() if r.is_active), None)
    claim = await _claimed_today(db, user.id)
    effects = await effects_of(db, user.id, config)
    today_date = await _date_today(db, user.id)
    until = await inspired_until(db, user.id, config)
    return {
        "enabled": config.muses_enabled,
        "collections": [g for g in groups if g["muses"]],
        "active": out(active_row.muse) if active_row and active_row.muse.is_active else None,
        "owned_count": sum(1 for m in muses if m.id in owned),
        "total_count": len(muses),
        "daily": {
            "coins": effects.get("daily_coins", 0),
            "claimed_today": claim is not None,
            "claimed_coins": claim.coins if claim else 0,
        },
        "date": {
            "today": _date_out(today_date) if today_date else None,
            "coins": config.muse_date_coins,
            "required": config.muse_date_required,
            "inspiration_hours": config.muse_inspiration_hours,
            "inspired_until": until.isoformat() if until else None,
        },
        "accessories": [accessory_out(a) for a in accessories],
        "caps": {
            "stat": config.muse_max_stat, "pp": config.muse_max_pp, "xp_pct": config.muse_max_xp_pct,
            "daily_coins": config.muse_max_daily_coins, "accessory_pct": config.muse_max_accessory_pct,
        },
    }


# --- player actions --------------------------------------------------------------------------


def _check_enabled(config: GameConfig) -> None:
    if not config.muses_enabled:
        raise ConflictError("Музы сейчас недоступны", details={"reason": "disabled"})


async def _own_row(db: AsyncSession, user_id: int, muse_id: int) -> UserMuse:
    row = (await db.execute(
        select(UserMuse).where(UserMuse.user_id == user_id, UserMuse.muse_id == muse_id)
        .with_for_update(of=UserMuse).execution_options(populate_existing=True)
    )).unique().scalar_one_or_none()
    if row is None:
        raise NotFoundError("Этой музы у тебя нет")
    return row


async def set_active(db: AsyncSession, user: User, muse_id: Optional[int]) -> dict:
    """Makes `muse_id` the active Muse (None = none)."""
    config = await get_config(db)
    _check_enabled(config)
    locked = await lock_user_for_update(db, user.id)
    target = await _own_row(db, locked.id, muse_id) if muse_id is not None else None
    if target is not None and not target.muse.is_active:
        raise ConflictError("Эта муза сейчас недоступна")
    current = (await db.execute(
        select(UserMuse).where(UserMuse.user_id == locked.id, UserMuse.is_active.is_(True))
        .with_for_update(of=UserMuse).execution_options(populate_existing=True)
    )).unique().scalars().all()
    for row in current:
        if target is None or row.id != target.id:
            row.is_active = False
            db.add(row)
    await db.flush()  # the one-active partial unique index sees the old one off first
    if target is not None:
        target.is_active = True
        db.add(target)
    await db.commit()
    return await album(db, locked)


async def claim_daily(db: AsyncSession, user: User) -> dict:
    config = await get_config(db)
    _check_enabled(config)
    locked = await lock_user_for_update(db, user.id)
    coins = (await effects_of(db, locked.id, config)).get("daily_coins", 0)
    if coins <= 0:
        raise ConflictError("Активная муза не приносит монеты — выбери музу с бонусом «монет в день»")
    if await _claimed_today(db, locked.id) is not None:
        raise ConflictError("Сегодня монеты от музы уже получены — приходи завтра")
    active = await _active(db, locked.id)
    db.add(MuseDailyClaim(user_id=locked.id, claim_date=local_today(), muse_id=active.muse_id if active else None, coins=coins))
    await credit_coins(
        db, locked, coins, TransactionType.muse_daily_coins, "Муза: монеты дня", related_object_type="muse",
        related_object_id=active.muse_id if active else None,
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("Сегодня монеты от музы уже получены — приходи завтра")
    await db.refresh(locked)
    view = await album(db, locked)
    view["claimed"] = coins
    view["new_balance"] = locked.balance
    return view


async def sell_spare(db: AsyncSession, user: User, muse_id: int, count: int = 1) -> dict:
    """Sells spare copies (the Muse herself always stays)."""
    config = await get_config(db)
    _check_enabled(config)
    locked = await lock_user_for_update(db, user.id)
    row = await _own_row(db, locked.id, muse_id)
    count = max(1, count)
    if row.copies - 1 < count:
        raise ConflictError("Лишних копий этой музы нет")
    price = spare_coins(config, row.muse.rarity)
    row.copies -= count
    db.add(row)
    if price * count > 0:
        await credit_coins(
            db, locked, price * count, TransactionType.muse_spare_sale, f"Муза «{row.muse.name}»: лишняя копия",
            related_object_type="muse", related_object_id=row.muse_id,
        )
    await db.commit()
    await db.refresh(locked)
    view = await album(db, locked)
    view["sold_coins"] = price * count
    view["new_balance"] = locked.balance
    return view


def _check_gift(accessory: Optional[MuseAccessory]) -> MuseAccessory:
    if accessory is None or not accessory.is_active:
        raise NotFoundError("Подарок не найден")
    return accessory


async def _has_gift(db: AsyncSession, user_muse_id: int, accessory_id: int) -> bool:
    return (await db.execute(
        select(UserMuseAccessory.id).where(
            UserMuseAccessory.user_muse_id == user_muse_id, UserMuseAccessory.accessory_id == accessory_id,
        )
    )).first() is not None


async def buy_accessory(
    db: AsyncSession, user: User, muse_id: int, accessory_id: int, purchase_key: Optional[str] = None,
) -> dict:
    config = await get_config(db)
    _check_enabled(config)
    if purchase_key:
        existing = (await db.execute(
            select(UserMuseAccessory).where(
                UserMuseAccessory.user_id == user.id, UserMuseAccessory.purchase_key == purchase_key,
            )
        )).unique().scalar_one_or_none()
        if existing is not None:
            await db.refresh(user)
            view = await album(db, user)
            view["new_balance"] = user.balance
            return view
    locked = await lock_user_for_update(db, user.id)
    row = await _own_row(db, locked.id, muse_id)
    accessory = _check_gift(await db.get(MuseAccessory, accessory_id))
    if accessory.coins_price <= 0:
        raise ConflictError("Этот подарок продаётся только за звёзды")
    if await _has_gift(db, row.id, accessory.id):
        raise ConflictError("У этой музы уже есть такой подарок")
    await debit_coins(
        db, locked, accessory.coins_price, TransactionType.muse_accessory_purchase,
        f"Подарок «{accessory.name}» для музы «{row.muse.name}»",
        related_object_type="muse_accessory", related_object_id=accessory.id,
    )
    db.add(UserMuseAccessory(
        user_id=locked.id, user_muse_id=row.id, accessory_id=accessory.id, source="coins", purchase_key=purchase_key,
    ))
    try:
        await db.commit()
    except IntegrityError:
        # A retried request with the same key, or a parallel purchase of the same gift.
        await db.rollback()
        if purchase_key:
            return await buy_accessory(db, user, muse_id, accessory_id, purchase_key)
        raise ConflictError("У этой музы уже есть такой подарок")
    await db.refresh(locked)
    view = await album(db, locked)
    view["new_balance"] = locked.balance
    return view


# --- «Свидание» ----------------------------------------------------------------------------


def _date_out(row: MuseDate) -> dict:
    title, page = DATE_GAMES.get(row.game, ("Мини-игра", "/play"))
    return {
        "game": row.game, "game_title": title, "path": f"{page}?muse=1",
        "completed": row.completed_at is not None, "coins": row.coins,
    }


async def _date_today(db: AsyncSession, user_id: int, lock: bool = False) -> Optional[MuseDate]:
    query = select(MuseDate).where(MuseDate.user_id == user_id, MuseDate.date_day == local_today())
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return (await db.execute(query)).scalar_one_or_none()


async def start_date(db: AsyncSession, user: User) -> dict:
    """Today's date with the active Muse: picks a random game once a day (a
    started but unfinished date keeps its game). The client then opens the
    game page with ?muse=1."""
    config = await get_config(db)
    _check_enabled(config)
    locked = await lock_user_for_update(db, user.id)
    active = await _active(db, locked.id)
    if active is None or not active.muse.is_active:
        raise ConflictError("Сначала выбери активную музу")
    row = await _date_today(db, locked.id, lock=True)
    if row is not None and row.completed_at is not None:
        raise ConflictError("Сегодня свидание уже было — муза ждёт тебя завтра")
    if row is None:
        games = [g for g in (config.muse_date_games or []) if g in DATE_GAMES] or list(DATE_GAMES)
        row = MuseDate(user_id=locked.id, date_day=local_today(), game=random.choice(games), muse_id=active.muse_id)
        db.add(row)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            row = await _date_today(db, user.id)
    else:
        await db.commit()
    return _date_out(row)


async def begin_date(db: AsyncSession, user_id: int, game: str) -> MuseDate:
    """Called by a mini-game's start_session(muse_date=True) under the user
    lock: today's unfinished date in this game, or a 409. The caller skips
    its hourly counter and links the session (row.session_id)."""
    _check_enabled(await get_config(db))
    row = await _date_today(db, user_id, lock=True)
    if row is None or row.completed_at is not None or row.game != game:
        raise ConflictError("Свидания с музой в этой игре сегодня нет", details={"reason": "no_muse_date"})
    return row


async def finish_date(db: AsyncSession, locked_user: User, session_id: int) -> Optional[int]:
    """Called by a mini-game's claim_reward under the user lock: if this
    session is a date, completes it (once) and pays the date coins instead
    of the game's reward. None = not a date session. The caller commits."""
    row = (await db.execute(
        select(MuseDate).where(MuseDate.user_id == locked_user.id, MuseDate.session_id == session_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if row is None:
        return None
    if row.completed_at is not None:
        return 0
    config = await get_config(db)
    coins = 0 if locked_user.game_rewards_blocked else max(0, config.muse_date_coins)
    row.completed_at = datetime.now(timezone.utc)
    row.coins = coins
    db.add(row)
    if coins:
        await credit_coins(
            db, locked_user, coins, TransactionType.muse_date_reward, "Свидание с музой",
            related_object_type="game_session", related_object_id=session_id,
        )
    return coins


# --- Stars ("muse_accessory:<user_muse_id>:<accessory_id>", see shop_product_service) ------


def _parse(arg: str) -> tuple[int, int]:
    user_muse_id, _, accessory_id = arg.partition(":")
    return int(user_muse_id), int(accessory_id)


async def stars_order(db: AsyncSession, user: User, muse_id: int, accessory_id: int) -> tuple[str, int, str, str]:
    _check_enabled(await get_config(db))
    row = (await db.execute(
        select(UserMuse).where(UserMuse.user_id == user.id, UserMuse.muse_id == muse_id)
    )).unique().scalar_one_or_none()
    if row is None:
        raise NotFoundError("Этой музы у тебя нет")
    accessory = _check_gift(await db.get(MuseAccessory, accessory_id))
    if accessory.stars_price <= 0:
        raise ConflictError("Этот подарок продаётся только за монеты")
    if await _has_gift(db, row.id, accessory.id):
        raise ConflictError("У этой музы уже есть такой подарок")
    return (
        f"muse_accessory:{row.id}:{accessory.id}", accessory.stars_price, accessory.name,
        f"Подарок для музы «{row.muse.name}»: +{accessory.boost_pct}% к её бонусу. " + (accessory.description or ""),
    )


async def validate_stars(db: AsyncSession, user_id: int, arg: str, stars_amount: int) -> tuple[bool, str]:
    if not (await get_config(db)).muses_enabled:
        return False, "Музы сейчас недоступны"
    try:
        user_muse_id, accessory_id = _parse(arg)
    except ValueError:
        return False, "Unknown order"
    row = await db.get(UserMuse, user_muse_id)
    accessory = await db.get(MuseAccessory, accessory_id)
    if row is None or row.user_id != user_id:
        return False, "Этой музы у тебя нет"
    if accessory is None or not accessory.is_active or accessory.stars_price <= 0 or accessory.stars_price != stars_amount:
        return False, "Этот подарок больше не продаётся"
    if await _has_gift(db, row.id, accessory.id):
        return False, "У этой музы уже есть такой подарок"
    return True, ""


async def deliver_stars(db: AsyncSession, user: User, arg: str) -> dict:
    """Already paid: the gift is delivered even if it was switched off
    meanwhile. If the Muse already has it (two invoices paid in a race), the
    player gets its coin price instead. The caller commits."""
    user_muse_id, accessory_id = _parse(arg)
    row = await db.get(UserMuse, user_muse_id)
    accessory = await db.get(MuseAccessory, accessory_id)
    if row is None or accessory is None or row.user_id != user.id:
        return {"kind": "muse_accessory", "name": accessory.name if accessory else "Подарок музе"}
    if await _has_gift(db, row.id, accessory.id):
        coins = accessory.coins_price or accessory.stars_price * 100
        locked = await lock_user_for_update(db, user.id)
        await credit_coins(
            db, locked, coins, TransactionType.muse_accessory_purchase,
            f"Подарок «{accessory.name}» уже был у музы — возврат монетами",
            related_object_type="muse_accessory", related_object_id=accessory.id,
        )
        return {"kind": "muse_accessory", "name": accessory.name, "refunded_coins": coins}
    db.add(UserMuseAccessory(user_id=user.id, user_muse_id=row.id, accessory_id=accessory.id, source="stars"))
    await db.flush()
    return {"kind": "muse_accessory", "name": accessory.name}


# --- packs (pack_service.roll_and_create_cards) ----------------------------------------------


_RARITY_ORDER = {"common": 0, "rare": 1, "epic": 2, "legendary": 3}


async def droppable(db: AsyncSession) -> list[Muse]:
    """Active Muses in active (or no) collections — the pack's drop pool."""
    rows = (await db.execute(select(Muse).where(Muse.is_active.is_(True), Muse.drop_weight > 0))).unique().scalars().all()
    return [m for m in rows if m.collection is None or m.collection.is_active]


def pick_random_muse(pool: list[Muse], rarity: Rarity) -> Optional[Muse]:
    """A Muse of the slot's rarity (diamond → legendary) by drop weight; if
    none has that rarity, the closest rarity below, then above."""
    if not pool:
        return None
    wanted = _RARITY_ORDER.get("legendary" if rarity == Rarity.diamond else rarity.value, 0)
    by_distance = sorted({_RARITY_ORDER.get(m.rarity, 0) for m in pool}, key=lambda r: (abs(r - wanted), r > wanted))
    tier = [m for m in pool if _RARITY_ORDER.get(m.rarity, 0) == by_distance[0]]
    return random.choices(tier, weights=[m.drop_weight for m in tier], k=1)[0]


async def grant(db: AsyncSession, user_id: int, muse: Muse, source: str) -> tuple[UserMuse, bool]:
    """Adds a Muse to the player's album (a repeat adds a copy); the first
    Muse a player gets becomes active. Caller holds the user lock, commits."""
    row = (await db.execute(
        select(UserMuse).where(UserMuse.user_id == user_id, UserMuse.muse_id == muse.id)
        .with_for_update(of=UserMuse).execution_options(populate_existing=True)
    )).unique().scalar_one_or_none()
    if row is not None:
        row.copies += 1
        db.add(row)
        await db.flush()
        return row, False
    has_active = await _active(db, user_id) is not None
    row = UserMuse(user_id=user_id, muse_id=muse.id, copies=1, is_active=not has_active, source=source)
    row.muse = muse
    db.add(row)
    await db.flush()
    return row, True


# --- admin -------------------------------------------------------------------------------


def admin_muse_out(muse: Muse) -> dict:
    return {
        "id": muse.id, "name": muse.name, "title": muse.title, "description": muse.description, "icon": muse.icon,
        "image_path": muse.image_path, "rarity": muse.rarity, "collection_id": muse.collection_id,
        "effect": muse.effect, "effect_value": muse.effect_value, "effect_label": effect_label(muse.effect, muse.effect_value),
        "drop_weight": muse.drop_weight, "is_active": muse.is_active, "sort_order": muse.sort_order,
    }


def admin_accessory_out(accessory: MuseAccessory) -> dict:
    return {**accessory_out(accessory), "is_active": accessory.is_active, "sort_order": accessory.sort_order}


def admin_collection_out(collection: MuseCollection) -> dict:
    return {**collection_out(collection), "is_active": collection.is_active, "sort_order": collection.sort_order}


async def admin_catalog(db: AsyncSession) -> dict:
    collections = (await db.execute(select(MuseCollection).order_by(MuseCollection.sort_order, MuseCollection.id))).scalars().all()
    muses = (await db.execute(select(Muse).order_by(Muse.sort_order, Muse.id))).unique().scalars().all()
    accessories = (await db.execute(select(MuseAccessory).order_by(MuseAccessory.sort_order, MuseAccessory.id))).scalars().all()
    return {
        "effects": [{"code": code, "label": label.format(v="N")} for code, label in EFFECTS.items()],
        "kinds": [{"code": code, "label": label} for code, label in KINDS.items()],
        "rarities": list(RARITIES),
        "collections": [admin_collection_out(c) for c in collections],
        "muses": [admin_muse_out(m) for m in muses],
        "accessories": [admin_accessory_out(a) for a in accessories],
    }


def _validate(data: dict) -> None:
    if data.get("effect") is not None and data["effect"] not in EFFECTS:
        raise ConflictError(f"Неизвестный бонус: {data['effect']}")
    if data.get("rarity") is not None and data["rarity"] not in RARITIES:
        raise ConflictError(f"Неизвестная редкость: {data['rarity']}")
    if data.get("kind") is not None and data["kind"] not in KINDS:
        raise ConflictError(f"Неизвестный вид подарка: {data['kind']}")


async def _save(db: AsyncSession, model, data: dict, row_id: Optional[int], missing: str):
    _validate(data)
    if row_id is None:
        row = model(**data)
        db.add(row)
    else:
        row = await db.get(model, row_id)
        if row is None:
            raise NotFoundError(missing)
        for key, value in data.items():
            setattr(row, key, value)
    await db.flush()
    await db.refresh(row)
    return row


async def admin_save_collection(db: AsyncSession, data: dict, collection_id: Optional[int] = None) -> dict:
    return admin_collection_out(await _save(db, MuseCollection, data, collection_id, "Коллекция не найдена"))


async def admin_save_muse(db: AsyncSession, data: dict, muse_id: Optional[int] = None) -> dict:
    if data.get("collection_id") and await db.get(MuseCollection, data["collection_id"]) is None:
        raise NotFoundError("Коллекция не найдена")
    return admin_muse_out(await _save(db, Muse, data, muse_id, "Муза не найдена"))


async def admin_save_accessory(db: AsyncSession, data: dict, accessory_id: Optional[int] = None) -> dict:
    return admin_accessory_out(await _save(db, MuseAccessory, data, accessory_id, "Подарок не найден"))


async def admin_grant(db: AsyncSession, muse_id: int, user_id: int) -> dict:
    muse = await db.get(Muse, muse_id)
    if muse is None:
        raise NotFoundError("Муза не найдена")
    locked = await db.get(User, user_id)
    if locked is None:
        raise NotFoundError("Пользователь не найден")
    await lock_user_for_update(db, user_id)
    row, is_new = await grant(db, user_id, muse, "admin")
    return {"user_muse_id": row.id, "copies": row.copies, "is_new": is_new}
