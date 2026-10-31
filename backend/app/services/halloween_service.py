"""«🎃 Ночь тыкв» — the Halloween event.

One switch (GameConfig.halloween_enabled), the dates (halloween_starts_at /
halloween_ends_at) and every number in GameConfig.halloween_settings
(DEFAULT_SETTINGS fills the keys an admin never touched).

- Pumpkins 🎃 are a balance of their own (HalloweenWallet, one per event
  key), never coins. They drop from rewarded games (the same
  wallet_service.credit_coins hook as season XP, capped per day), from
  claimed tasks and from activity chests, and doubly from the «Безголовый
  вратарь» of «Контратака».
- «Лавка тыкв» trades them for the event pack, coins, skill tokens and the
  limited «Тыква 2026» badge — under the user's row lock, idempotent by the
  client's key (a unique HalloweenLedger.ref_key).
- «Кошелёк или жизнь»: once a local day, one of three doors; the server
  rolls a treat (coins / pumpkins / pack) or a harmless trick (a zombie
  frame on one footballer for a day — purely visual — or a joke).

Every mutation runs with the user row locked (lock_user_for_update), so a
player's wallet row can't race; the caller of the hooks commits.
"""
import copy
import random
from datetime import datetime, time, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import app_timezone, ensure_aware, local_today
from app.models.badge import Badge, UserBadge
from app.models.card import UserCard
from app.models.card_collection import CardCollection, UserCollectionReward
from app.models.enums import CardSource, TransactionType
from app.models.game_config import GameConfig
from app.models.halloween import HalloweenLedger, HalloweenWallet
from app.models.pack import Pack
from app.models.player import Player
from app.models.user import User
from app.schemas.badge import BadgeOut
from app.schemas.halloween import (
    HalloweenBuyOut,
    HalloweenCollectionOut,
    HalloweenDoorResultOut,
    HalloweenShopItemOut,
    HalloweenStateOut,
)
from app.services.wallet_service import credit_coins, lock_user_for_update

DOORS = 3
SHOP_KINDS = ("pack", "coins", "skill_tokens", "badge")
TREAT_KINDS = ("coins", "pumpkins", "pack")

DEFAULT_SETTINGS: dict[str, Any] = {
    # Drops
    "pumpkins_per_game": 3,
    "pumpkins_games_daily_cap": 60,
    "pumpkins_per_task": 4,
    "pumpkins_per_daily_chest": 6,
    "pumpkins_per_weekly_chest": 20,
    # «Безголовый вратарь»: standing until the final whistle multiplies the game's pumpkins.
    "boss_enabled": True,
    "boss_multiplier": 2,
    # What the event is made of (ids set by migration 0222 / the admin).
    "pack_id": None,
    "badge_id": None,
    "collection_id": None,
    # «Лавка тыкв»; limit 0 = unlimited. A pack / badge item without its id
    # takes pack_id / badge_id above; skill_code null = a random droppable skill.
    "shop": [
        {"code": "legends_pack", "kind": "pack", "title": "Пак «Ночь живых Легенд»", "price": 90, "limit": 5,
         "pack_id": None},
        {"code": "coins", "kind": "coins", "title": "Мешок монет", "price": 25, "amount": 400, "limit": 10},
        {"code": "skill_tokens", "kind": "skill_tokens", "title": "Жетоны навыков", "price": 40, "amount": 2,
         "limit": 5, "skill_code": None},
        {"code": "badge_2026", "kind": "badge", "title": "Значок «Тыква 2026»", "price": 150, "limit": 1,
         "badge_id": None},
    ],
    # «Кошелёк или жизнь»
    "door_trick_pct": 30,
    "door_treats": [
        {"weight": 45, "kind": "coins", "amount": 200},
        {"weight": 40, "kind": "pumpkins", "amount": 15},
        {"weight": 15, "kind": "pack", "pack_id": None},
    ],
    "door_zombie_weight": 70,
    "door_joke_weight": 30,
    "door_zombie_hours": 24,
}

# Copy, not economy: the harmless tricks behind a door.
JOKES = (
    "Из-за двери выпрыгнул скелет и попросил автограф. Ты расписался — он ушёл довольный.",
    "За дверью — сто летучих мышей. Они пересчитали твои карточки и улетели. Все на месте!",
    "Тебя облили сиропом из тыквы. Липко, но вкусно.",
    "Призрак вратаря взял пенальти, которого ты не бил. Счёт не изменился.",
)
TREAT_TITLES = {"coins": "Сладость: монеты!", "pumpkins": "Сладость: тыквы!", "pack": "Сладость: пак!"}

# A fixed default window: 31.10 – 04.11 of the current year, local time.
_DEFAULT_START = (10, 31)
_DEFAULT_DAYS = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _config(db: AsyncSession) -> Optional[GameConfig]:
    """The config row from the identity map (never created here); reloaded
    when an earlier commit of this session expired it."""
    config = await db.get(GameConfig, 1)
    if config is not None and inspect(config).expired_attributes:
        await db.refresh(config)
    return config


def settings_of(config: GameConfig) -> dict[str, Any]:
    out = copy.deepcopy(DEFAULT_SETTINGS)
    out.update({k: v for k, v in (config.halloween_settings or {}).items() if k in DEFAULT_SETTINGS})
    return out


def window(config: GameConfig) -> tuple[datetime, datetime]:
    if config.halloween_starts_at and config.halloween_ends_at:
        return ensure_aware(config.halloween_starts_at), ensure_aware(config.halloween_ends_at)
    year = local_today().year
    start = datetime(year, *_DEFAULT_START, tzinfo=app_timezone())
    return start, start + timedelta(days=_DEFAULT_DAYS)


def is_active(config: Optional[GameConfig], now: Optional[datetime] = None) -> bool:
    if config is None or not config.halloween_enabled:
        return False
    start, end = window(config)
    return start <= (now or _now()) < end


def event_key(config: GameConfig) -> str:
    return f"halloween-{window(config)[0].astimezone(app_timezone()).year}"


def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


async def _wallet(db: AsyncSession, user_id: int, key: str, create: bool = False) -> Optional[HalloweenWallet]:
    """The caller holds the user's row lock, so creating the row can't race."""
    wallet = await db.get(HalloweenWallet, (user_id, key))
    if wallet is None and create:
        wallet = HalloweenWallet(user_id=user_id, event_key=key, pumpkins=0, earned_total=0, games_pumpkins_today=0)
        db.add(wallet)
        await db.flush()
    return wallet


async def _ledger(
    db: AsyncSession, wallet: HalloweenWallet, kind: str, delta: int, *,
    ref_key: Optional[str] = None, item_code: Optional[str] = None, details: Optional[dict] = None,
) -> Optional[HalloweenLedger]:
    """Moves pumpkins and writes the ledger row. With a ref_key already used
    by this player it is a no-op (returns None) — the retry/once guarantee."""
    if delta < 0 and wallet.pumpkins + delta < 0:
        raise ConflictError("Не хватает тыкв", details={"reason": "not_enough_pumpkins", "pumpkins": wallet.pumpkins})
    entry = HalloweenLedger(
        user_id=wallet.user_id, event_key=wallet.event_key, kind=kind, delta=delta,
        balance_after=wallet.pumpkins + delta, ref_key=ref_key, item_code=item_code, details=details,
    )
    if ref_key is not None:
        try:
            async with db.begin_nested():
                db.add(entry)
                await db.flush()
        except IntegrityError:
            return None
    else:
        db.add(entry)
    wallet.pumpkins += delta
    if delta > 0:
        wallet.earned_total += delta
    wallet.updated_at = _now()
    db.add(wallet)
    return entry


async def add_pumpkins(
    db: AsyncSession, user: User, amount: int, kind: str, *, ref_key: Optional[str] = None,
    config: Optional[GameConfig] = None, details: Optional[dict] = None,
) -> int:
    """Credits pumpkins to a row-locked `user` while the event runs. Returns
    what was added (0 when off, blocked, or the ref_key was used)."""
    config = config or await _config(db)
    if amount <= 0 or not is_active(config) or user.game_rewards_blocked:
        return 0
    wallet = await _wallet(db, user.id, event_key(config), create=True)
    entry = await _ledger(db, wallet, kind, amount, ref_key=ref_key, details=details)
    return amount if entry is not None else 0


# --- Drop hooks ------------------------------------------------------------------

async def grant_game_pumpkins(db: AsyncSession, user: User, tx_type: TransactionType, amount: int) -> int:
    """wallet_service.credit_coins hook: a rewarded game (the season-XP
    transaction types) drops pumpkins, up to the daily cap. Reads the
    already-loaded config row, never creates it."""
    from app.services.season_pass_service import SEASON_XP_TX_TYPES

    if amount <= 0 or tx_type not in SEASON_XP_TX_TYPES:
        return 0
    config = await _config(db)
    if not is_active(config) or user.game_rewards_blocked:
        return 0
    s = settings_of(config)
    per_game, cap = _int(s["pumpkins_per_game"]), _int(s["pumpkins_games_daily_cap"])
    if per_game <= 0:
        return 0
    wallet = await _wallet(db, user.id, event_key(config), create=True)
    today = local_today().isoformat()
    if wallet.games_day != today:
        wallet.games_day, wallet.games_pumpkins_today = today, 0
    give = per_game if cap <= 0 else max(0, min(per_game, cap - wallet.games_pumpkins_today))
    if give <= 0:
        db.add(wallet)
        return 0
    wallet.games_pumpkins_today += give
    await _ledger(db, wallet, "game", give, details={"tx": tx_type.value})
    return give


async def grant_task_pumpkins(db: AsyncSession, user: User, user_task_id: int, period_key: Optional[str]) -> int:
    config = await _config(db)
    if not is_active(config):
        return 0
    return await add_pumpkins(
        db, user, _int(settings_of(config)["pumpkins_per_task"]), "task",
        ref_key=f"task:{user_task_id}:{period_key or '-'}", config=config,
    )


async def grant_chest_pumpkins(db: AsyncSession, user: User, period: str, period_key: str, index: int) -> int:
    config = await _config(db)
    if not is_active(config):
        return 0
    s = settings_of(config)
    amount = _int(s["pumpkins_per_weekly_chest" if period == "weekly" else "pumpkins_per_daily_chest"])
    return await add_pumpkins(db, user, amount, "chest", ref_key=f"chest:{period}:{period_key}:{index}", config=config)


# --- «Безголовый вратарь» --------------------------------------------------------

BOSS_CODE = "headless"


def kontra_boss(config: Optional[GameConfig]) -> Optional[dict]:
    """The event's «Контратака» boss while the event runs, else None (the
    weekly rotation stays)."""
    if not is_active(config) or not settings_of(config).get("boss_enabled", True):
        return None
    from app.services.kontra_catalog import HALLOWEEN_BOSS

    return dict(HALLOWEEN_BOSS, abilities=list(HALLOWEEN_BOSS["abilities"]))


def boss_won(state: dict) -> bool:
    """Against the boss you can't empty its weekly HP in one go: standing
    until the final whistle (or knocking it out) is the win."""
    return not state.get("forfeit") and state.get("winner") in ("me", "time")


async def grant_boss_bonus(db: AsyncSession, user: User, battle_id: int, state: dict) -> int:
    """Doubles (×boss_multiplier) the game's pumpkins for a win over the
    «Безголовый вратарь». `user` is row-locked by kontra_service._finish."""
    if (state.get("boss") or {}).get("code") != BOSS_CODE or not boss_won(state):
        return 0
    config = await _config(db)
    if not is_active(config):
        return 0
    s = settings_of(config)
    extra = _int(s["pumpkins_per_game"]) * max(0, _int(s["boss_multiplier"], 1) - 1)
    return await add_pumpkins(db, user, extra, "boss", ref_key=f"kontra-boss:{battle_id}", config=config)


# --- State -----------------------------------------------------------------------

def _shop_items(s: dict) -> list[dict]:
    items = []
    for raw in s.get("shop") or []:
        if not isinstance(raw, dict) or raw.get("kind") not in SHOP_KINDS or not raw.get("code"):
            continue
        item = dict(raw)
        if item["kind"] == "pack":
            item["pack_id"] = item.get("pack_id") or s.get("pack_id")
        if item["kind"] == "badge":
            item["badge_id"] = item.get("badge_id") or s.get("badge_id")
        items.append(item)
    return items


async def _bought_counts(db: AsyncSession, user_id: int, key: str) -> dict[str, int]:
    rows = (await db.execute(
        select(HalloweenLedger.item_code, func.count(HalloweenLedger.id)).where(
            HalloweenLedger.user_id == user_id, HalloweenLedger.event_key == key, HalloweenLedger.kind == "shop",
        ).group_by(HalloweenLedger.item_code)
    )).all()
    return {code: int(n) for code, n in rows}


async def _shop_out(db: AsyncSession, user: User, s: dict, key: str, active: bool) -> list[HalloweenShopItemOut]:
    bought = await _bought_counts(db, user.id, key)
    out = []
    for item in _shop_items(s):
        pack = await db.get(Pack, item["pack_id"]) if item["kind"] == "pack" and item.get("pack_id") else None
        badge = await db.get(Badge, item["badge_id"]) if item["kind"] == "badge" and item.get("badge_id") else None
        limit = _int(item.get("limit"))
        n = bought.get(item["code"], 0)
        owned_badge = badge is not None and (await db.execute(
            select(UserBadge.id).where(UserBadge.user_id == user.id, UserBadge.badge_id == badge.id)
        )).first() is not None
        configured = (item["kind"] != "pack" or (pack is not None and pack.is_active)) and (item["kind"] != "badge" or badge is not None)
        out.append(HalloweenShopItemOut(
            code=item["code"], kind=item["kind"], title=str(item.get("title") or item["code"]),
            price=_int(item.get("price")), amount=_int(item.get("amount")), limit=limit, bought=n,
            available=active and configured and (limit <= 0 or n < limit) and not owned_badge,
            pack_id=pack.id if pack else None, pack_name=pack.name if pack else None,
            badge=BadgeOut.model_validate(badge) if badge else None,
        ))
    return out


def _next_local_midnight(now: Optional[datetime] = None) -> datetime:
    return datetime.combine(local_today(now) + timedelta(days=1), time.min, tzinfo=app_timezone())


async def _door_today(db: AsyncSession, user_id: int, key: str) -> Optional[HalloweenDoorResultOut]:
    entry = (await db.execute(select(HalloweenLedger).where(
        HalloweenLedger.user_id == user_id, HalloweenLedger.ref_key == f"door:{key}:{local_today().isoformat()}",
    ))).scalar_one_or_none()
    if entry is None or not entry.details:
        return None
    return HalloweenDoorResultOut.model_validate({k: v for k, v in entry.details.items() if k != "cards"})


async def _collection_out(db: AsyncSession, user_id: int, collection_id: Optional[int]) -> Optional[HalloweenCollectionOut]:
    if not collection_id:
        return None
    collection = await db.get(CardCollection, collection_id)
    if collection is None:
        return None
    total = (await db.execute(select(func.count(Player.id)).where(
        Player.collection_id == collection.id, Player.is_active.is_(True),
    ))).scalar_one()
    owned = (await db.execute(
        select(func.count(func.distinct(UserCard.player_id))).join(Player, Player.id == UserCard.player_id).where(
            UserCard.owner_id == user_id, Player.collection_id == collection.id, Player.is_active.is_(True),
        )
    )).scalar_one()
    completed = (await db.execute(select(UserCollectionReward.id).where(
        UserCollectionReward.user_id == user_id, UserCollectionReward.collection_id == collection.id,
    ))).first() is not None
    reward_pack = await db.get(Pack, collection.reward_pack_id) if collection.reward_pack_id else None
    return HalloweenCollectionOut(
        id=collection.id, name=collection.name, owned=int(owned), total=int(total),
        reward_coins=collection.reward_coins, reward_pack_name=reward_pack.name if reward_pack else None,
        completed=completed,
    )


async def get_state(db: AsyncSession, user: User) -> HalloweenStateOut:
    from app.services.game_config_service import get_config

    config = await get_config(db)
    start, end = window(config)
    active = is_active(config)
    if not config.halloween_enabled:
        return HalloweenStateOut(enabled=False, active=False, starts_at=start, ends_at=end)
    s = settings_of(config)
    key = event_key(config)
    wallet = await _wallet(db, user.id, key)
    zombie_live = bool(wallet and wallet.zombie_until and ensure_aware(wallet.zombie_until) > _now())
    boss = kontra_boss(config)
    today = local_today().isoformat()
    return HalloweenStateOut(
        enabled=True, active=active, starts_at=start, ends_at=end,
        pumpkins=wallet.pumpkins if wallet else 0, earned_total=wallet.earned_total if wallet else 0,
        pumpkins_per_game=_int(s["pumpkins_per_game"]),
        games_pumpkins_today=wallet.games_pumpkins_today if wallet and wallet.games_day == today else 0,
        games_daily_cap=_int(s["pumpkins_games_daily_cap"]), pumpkins_per_task=_int(s["pumpkins_per_task"]),
        pumpkins_per_daily_chest=_int(s["pumpkins_per_daily_chest"]),
        pumpkins_per_weekly_chest=_int(s["pumpkins_per_weekly_chest"]),
        boss_multiplier=_int(s["boss_multiplier"], 1), boss_name=boss["name"] if boss else None,
        shop=await _shop_out(db, user, s, key, active),
        door_today=await _door_today(db, user.id, key), door_resets_at=_next_local_midnight(),
        zombie_player_id=wallet.zombie_player_id if zombie_live else None,
        zombie_until=wallet.zombie_until if zombie_live else None,
        pack_id=s.get("pack_id"), collection=await _collection_out(db, user.id, s.get("collection_id")),
    )


# --- «Лавка тыкв» ----------------------------------------------------------------

async def _random_skill_code(db: AsyncSession) -> str:
    from app.services.card_skill_service import pack_token_drop_table, pick_pack_token

    table = await pack_token_drop_table(db)
    if not table:
        raise ConflictError("Жетоны навыков сейчас недоступны")
    return pick_pack_token(table)[0]


async def buy(db: AsyncSession, user: User, item_code: str, idempotency_key: str) -> HalloweenBuyOut:
    """Spends pumpkins on one shop item. Everything (pumpkins, coins, pack,
    tokens, badge) happens in one transaction under the user's row lock; a
    retried request with the same key returns the first result."""
    from app.services.collection_service import grant_collection_rewards_for_new_cards
    from app.services.game_config_service import get_config
    from app.services.pack_service import grant_bonus_pack_opening

    config = await get_config(db)
    if not is_active(config):
        raise ConflictError("Ночь тыкв закончилась — лавка закрыта")
    s = settings_of(config)
    item = next((i for i in _shop_items(s) if i["code"] == item_code), None)
    if item is None:
        raise NotFoundError("Такого товара в лавке нет")
    key = event_key(config)
    ref_key = f"shop:{idempotency_key}"

    locked = await lock_user_for_update(db, user.id)
    previous = (await db.execute(select(HalloweenLedger).where(
        HalloweenLedger.user_id == locked.id, HalloweenLedger.ref_key == ref_key,
    ))).scalar_one_or_none()
    wallet = await _wallet(db, locked.id, key, create=True)
    if previous is not None:
        if previous.item_code != item_code:
            raise ConflictError("Этот ключ покупки уже использован")
        return HalloweenBuyOut(item_code=item_code, pumpkins=wallet.pumpkins, new_balance=locked.balance,
                               **(previous.details or {}).get("result", {}))
    if locked.game_rewards_blocked:
        raise ConflictError("Награды ивента для этого аккаунта отключены")

    limit = _int(item.get("limit"))
    if limit > 0 and (await _bought_counts(db, locked.id, key)).get(item_code, 0) >= limit:
        raise ConflictError("Лимит этого товара исчерпан")
    price = _int(item.get("price"))
    if price <= 0:
        raise ConflictError("Товар ещё не настроен")
    if wallet.pumpkins < price:
        raise ConflictError("Не хватает тыкв", details={"reason": "not_enough_pumpkins", "pumpkins": wallet.pumpkins,
                                                        "required": price})

    kind = item["kind"]
    result: dict[str, Any] = {}
    out = HalloweenBuyOut(item_code=item_code, pumpkins=0, new_balance=0)
    entry = await _ledger(db, wallet, "shop", -price, ref_key=ref_key, item_code=item_code)
    if entry is None:  # a concurrent twin got in first (Postgres serializes it on the lock; belt and braces)
        raise ConflictError("Покупка уже обрабатывается")

    if kind == "coins":
        amount = _int(item.get("amount"))
        await credit_coins(db, locked, amount, TransactionType.halloween_reward, f"Лавка тыкв: {item.get('title')}",
                           "halloween_ledger", entry.id)
        out.coins = result["coins"] = amount
    elif kind == "pack":
        pack_id = item.get("pack_id")
        pack = await db.get(Pack, pack_id) if pack_id else None
        if pack is None or not pack.is_active:
            raise ConflictError("Пак ещё не в продаже")
        opened = await grant_bonus_pack_opening(db, locked, pack_id, idempotency_prefix=f"halloween-shop-{entry.id}",
                                                source=CardSource.pack)
        if opened is not None:
            await grant_collection_rewards_for_new_cards(db, locked, [c.card.player.id for c in opened.cards])
            out.pack_name = result["pack_name"] = opened.pack.name
            out.cards = [c.card for c in opened.cards]
    elif kind == "skill_tokens":
        from app.services.card_skill_service import grant_tokens

        code = item.get("skill_code") or await _random_skill_code(db)
        amount = max(1, _int(item.get("amount"), 1))
        await grant_tokens(db, locked, code, amount, "grant_event", related_object_type="halloween_ledger",
                           related_object_id=entry.id, reason="Лавка тыкв")
        out.skill_code, out.skill_tokens = code, amount
        result.update(skill_code=code, skill_tokens=amount)
    elif kind == "badge":
        from app.services.reward_bundle_service import grant_badge

        badge_id = item.get("badge_id")
        if not badge_id:
            raise ConflictError("Значок ещё не настроен")
        if (await db.execute(select(UserBadge.id).where(
            UserBadge.user_id == locked.id, UserBadge.badge_id == badge_id,
        ))).first():
            raise ConflictError("Этот значок у тебя уже есть")
        badge = await grant_badge(db, locked, badge_id)
        if badge is None:
            raise ConflictError("Значок ещё не настроен")
        out.badge = BadgeOut.model_validate(badge)
        result["badge"] = out.badge.model_dump(mode="json")

    entry.details = {"result": result}
    db.add(entry)
    await db.commit()
    await db.refresh(locked)
    out.pumpkins = wallet.pumpkins
    out.new_balance = locked.balance
    return out


# --- «Кошелёк или жизнь» --------------------------------------------------------

def _weighted(rng: random.Random, options: list[tuple[Any, int]]) -> Any:
    options = [(o, w) for o, w in options if w > 0]
    if not options:
        return None
    return rng.choices([o for o, _ in options], weights=[w for _, w in options], k=1)[0]


async def open_door(db: AsyncSession, user: User, door: int) -> HalloweenDoorResultOut:
    """Once a local day. The server rolls the outcome — the door number is
    only the player's pick, it never decides what is behind it."""
    from app.services.collection_service import grant_collection_rewards_for_new_cards
    from app.services.game_config_service import get_config
    from app.services.pack_service import grant_bonus_pack_opening

    if not 0 <= door < DOORS:
        raise NotFoundError("Такой двери нет")
    config = await get_config(db)
    if not is_active(config):
        raise ConflictError("Ночь тыкв закончилась — двери заперты")
    s = settings_of(config)
    key = event_key(config)
    locked = await lock_user_for_update(db, user.id)
    if locked.game_rewards_blocked:
        raise ConflictError("Награды ивента для этого аккаунта отключены")
    wallet = await _wallet(db, locked.id, key, create=True)
    ref_key = f"door:{key}:{local_today().isoformat()}"
    if (await db.execute(select(HalloweenLedger.id).where(
        HalloweenLedger.user_id == locked.id, HalloweenLedger.ref_key == ref_key,
    ))).first():
        raise ConflictError("Сегодня ты уже стучался — приходи завтра")

    rng = random.SystemRandom()
    trick = rng.randint(1, 100) <= _int(s["door_trick_pct"])
    result = HalloweenDoorResultOut(door=door, outcome="trick" if trick else "treat", kind="joke", title="", text="")
    pumpkins = 0
    if trick:
        zombie_card = None
        kind = _weighted(rng, [("zombie_frame", _int(s["door_zombie_weight"])), ("joke", _int(s["door_joke_weight"]))])
        if kind == "zombie_frame":
            zombie_card = (await db.execute(
                select(UserCard).where(UserCard.owner_id == locked.id).order_by(func.random()).limit(1)
            )).scalar_one_or_none()
        if zombie_card is not None:
            player = await db.get(Player, zombie_card.player_id)
            until = _now() + timedelta(hours=max(1, _int(s["door_zombie_hours"], 24)))
            wallet.zombie_player_id, wallet.zombie_until = player.id, until
            result.kind, result.zombie_player_name, result.zombie_until = "zombie_frame", player.display_name, until
            result.title = "Гадость: зомби-рамка!"
            result.text = f"{player.display_name} восстал из мёртвых — сутки ходит в зомби-рамке. Не заразно!"
        else:
            result.kind, result.title, result.text = "joke", "Гадость!", rng.choice(JOKES)
    else:
        treats = [t for t in (s.get("door_treats") or []) if isinstance(t, dict) and t.get("kind") in TREAT_KINDS]
        treat = _weighted(rng, [(t, _int(t.get("weight"))) for t in treats]) or {"kind": "pumpkins", "amount": 5}
        result.kind, result.title = treat["kind"], TREAT_TITLES[treat["kind"]]
        if treat["kind"] == "pack":
            pack_id = treat.get("pack_id") or s.get("pack_id")
            pack = await db.get(Pack, pack_id) if pack_id else None
            if pack is None or not pack.is_active:  # no pack on sale yet → pumpkins instead
                treat = {"kind": "pumpkins", "amount": 10}
                result.kind, result.title = "pumpkins", TREAT_TITLES["pumpkins"]
        if treat["kind"] == "coins":
            result.amount = _int(treat.get("amount"))
            await credit_coins(db, locked, result.amount, TransactionType.halloween_reward, "Кошелёк или жизнь")
            result.text = f"За дверью — мешок с {result.amount} монетами!"
        elif treat["kind"] == "pumpkins":
            pumpkins = result.amount = _int(treat.get("amount"))
            result.text = f"Тебе насыпали {pumpkins} 🎃!"
        else:
            opened = await grant_bonus_pack_opening(db, locked, pack.id, idempotency_prefix=f"halloween-door-{ref_key}",
                                                    source=CardSource.game_reward)
            if opened is not None:
                await grant_collection_rewards_for_new_cards(db, locked, [c.card.player.id for c in opened.cards])
                result.pack_name = opened.pack.name
                result.cards = [c.card for c in opened.cards]
            result.text = f"За дверью — пак «{pack.name}»!"

    details = result.model_dump(mode="json", exclude={"cards"})
    entry = await _ledger(db, wallet, "door", pumpkins, ref_key=ref_key, details=details)
    if entry is None:
        raise ConflictError("Сегодня ты уже стучался — приходи завтра")
    db.add(wallet)
    await db.commit()
    return result


# --- Admin -----------------------------------------------------------------------

async def admin_stats(db: AsyncSession, config: GameConfig) -> dict[str, int]:
    key = event_key(config)
    players, earned, held = (await db.execute(select(
        func.count(HalloweenWallet.user_id), func.coalesce(func.sum(HalloweenWallet.earned_total), 0),
        func.coalesce(func.sum(HalloweenWallet.pumpkins), 0),
    ).where(HalloweenWallet.event_key == key))).one()
    purchases = (await db.execute(select(func.count(HalloweenLedger.id)).where(
        HalloweenLedger.event_key == key, HalloweenLedger.kind == "shop",
    ))).scalar_one()
    doors = (await db.execute(select(func.count(HalloweenLedger.id)).where(
        HalloweenLedger.event_key == key, HalloweenLedger.kind == "door",
    ))).scalar_one()
    return {"players": int(players), "earned": int(earned), "held": int(held), "purchases": int(purchases),
            "doors": int(doors)}


def validate_settings(raw: dict) -> dict:
    """Admin input: known keys only, non-negative numbers, sane shop rows."""
    clean: dict[str, Any] = {}
    for k, v in raw.items():
        if k not in DEFAULT_SETTINGS:
            continue
        default = DEFAULT_SETTINGS[k]
        if isinstance(default, bool):
            clean[k] = bool(v)
        elif isinstance(default, int) or (default is None and k.endswith("_id")):
            if v in (None, "", 0) and default is None:
                clean[k] = None
                continue
            n = _int(v, -1)
            if n < 0:
                raise ConflictError(f"«{k}» должно быть неотрицательным числом")
            clean[k] = n
        elif k == "shop":
            if not isinstance(v, list):
                raise ConflictError("Лавка — список товаров")
            codes = set()
            for item in v:
                if not isinstance(item, dict) or item.get("kind") not in SHOP_KINDS or not item.get("code"):
                    raise ConflictError("У товара лавки нужны code и kind (pack / coins / skill_tokens / badge)")
                if item["code"] in codes:
                    raise ConflictError(f"Код товара «{item['code']}» повторяется")
                codes.add(item["code"])
                if _int(item.get("price"), -1) <= 0:
                    raise ConflictError(f"Цена товара «{item['code']}» должна быть больше нуля")
            clean[k] = v
        elif k == "door_treats":
            if not isinstance(v, list) or any(
                not isinstance(t, dict) or t.get("kind") not in TREAT_KINDS or _int(t.get("weight"), -1) < 0 for t in v
            ):
                raise ConflictError("Сладости дверей — список {weight, kind: coins/pumpkins/pack, amount}")
            clean[k] = v
        else:
            clean[k] = v
    if "door_trick_pct" in clean and clean["door_trick_pct"] > 100:
        raise ConflictError("Шанс гадости — от 0 до 100")
    return clean
