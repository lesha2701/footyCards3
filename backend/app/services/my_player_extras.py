"""«Мой игрок» extras: sponsors, gifts, limited editions, the trophy
cabinet and the «Зал славы».

- «Спонсор»: every week the player picks one of three (fictional) brands of
  GameConfig.my_player_sponsors; its first three goals
  (my_player_sponsor_goals: trainings, duel wins, career matches / goals /
  wins, rewarded games) pay coins one by one, all of them a bonus. The
  premium contract (Telegram Stars) adds the fourth goal and pays
  my_player_sponsor_premium_pct% — what was already paid is topped up.
  Progress comes from hooks (`progress`) in the training, the duels, the
  career match record and the rewarded-game XP hook; they all run under
  the player's row lock.
- Gifts: Telegram Stars only — a training, a style item or «Карьера Pro»
  for a friend's player; the count of gifts sent makes the sender a «Меценат».
- Limited style items (my_player_limited_supply): Stars only, each copy
  numbered by sale order (MyPlayerEdition).
- Cabinet: lifetime career totals + trophies in the chosen showcase;
  «Зал славы»: the best of all players by league career totals or trophies.
"""
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import app_timezone, ensure_aware
from app.models.enums import NotificationType, TransactionType
from app.models.my_player import MyPlayer
from app.models.my_player_extras import MyPlayerEdition, MyPlayerGift, MyPlayerSponsorContract
from app.models.user import User
from app.services.game_config_service import get_config

# Goals a sponsor may set — each one is counted by a hook (see `progress`).
SPONSOR_GOALS = ("training", "duel_win", "career_match", "career_goal", "career_win", "game_reward")
FREE_GOALS = 3
OFFERS_A_WEEK = 3
PATRON_NAMES = ("Меценат I", "Меценат II", "Меценат III")
HALL_METRICS = ("goals", "assists", "titles", "matches", "golden_ball", "trophies")
HALL_SIZE = 50


def _name(user: Optional[User]) -> str:
    if user is None:
        return "Игрок"
    return user.first_name or user.username or "Игрок"


# --- sponsors --------------------------------------------------------------------------------

def week_key(now: Optional[datetime] = None) -> str:
    local = ensure_aware(now or datetime.now(timezone.utc)).astimezone(app_timezone())
    year, week, _ = local.isocalendar()
    return f"{year}-W{week:02d}"


def week_ends_at(now: Optional[datetime] = None) -> datetime:
    local = ensure_aware(now or datetime.now(timezone.utc)).astimezone(app_timezone())
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return (monday + timedelta(days=7)).astimezone(timezone.utc)


def validate_sponsors(brands: list, goals: dict) -> None:
    """Admin check: known goals with a target, brands with four of them."""
    if not isinstance(goals, dict) or not goals:
        raise ValueError("цели спонсоров — словарь {код: {label, target, coins}}")
    for code, goal in goals.items():
        if code not in SPONSOR_GOALS:
            raise ValueError(f"неизвестная цель «{code}» (можно: {', '.join(SPONSOR_GOALS)})")
        if not isinstance(goal, dict) or int(goal.get("target") or 0) < 1 or int(goal.get("coins") or 0) < 0:
            raise ValueError(f"цель «{code}»: нужны target ≥ 1 и coins ≥ 0")
    if not isinstance(brands, list) or len(brands) < OFFERS_A_WEEK:
        raise ValueError(f"нужно хотя бы {OFFERS_A_WEEK} бренда")
    seen = set()
    for brand in brands:
        code = brand.get("code") if isinstance(brand, dict) else None
        if not code or code in seen or not brand.get("name"):
            raise ValueError("у бренда нужны уникальный code и name")
        seen.add(code)
        codes = brand.get("goals") or []
        if len(codes) != FREE_GOALS + 1 or len(set(codes)) != len(codes) or any(c not in goals for c in codes):
            raise ValueError(f"бренд «{code}»: ровно 4 разные цели из списка целей")


def _brands(config) -> dict[str, dict]:
    return {b["code"]: b for b in (config.my_player_sponsors or []) if isinstance(b, dict) and b.get("code")}


def offers_for(user_id: int, week: str, config) -> list[dict]:
    brands = list(_brands(config).values())
    rng = random.Random(f"sponsor:{user_id}:{week}")
    return rng.sample(brands, min(OFFERS_A_WEEK, len(brands)))


def _goal_coins(goal: dict, premium: bool, config) -> int:
    base = int(goal.get("coins") or 0)
    return base * max(100, config.my_player_sponsor_premium_pct) // 100 if premium else base


def _bonus_coins(premium: bool, config) -> int:
    base = config.my_player_sponsor_bonus_coins
    return base * max(100, config.my_player_sponsor_premium_pct) // 100 if premium else base


def _active_goals(contract: MyPlayerSponsorContract) -> list[str]:
    goals = list(contract.goals or [])
    return goals if contract.premium else goals[:FREE_GOALS]


async def _contract(db: AsyncSession, user_id: int, week: str, lock: bool = False) -> Optional[MyPlayerSponsorContract]:
    stmt = select(MyPlayerSponsorContract).where(MyPlayerSponsorContract.user_id == user_id, MyPlayerSponsorContract.week == week)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalar_one_or_none()


async def progress(db: AsyncSession, user_id: int, goal: str, amount: int = 1, now: Optional[datetime] = None) -> None:
    """Hook: `amount` more of `goal` this week (no contract = nothing). The
    callers hold the player's row lock, so the JSON update can't race."""
    if amount <= 0:
        return
    contract = await _contract(db, user_id, week_key(now))
    if contract is None or goal not in (contract.goals or []):
        return
    counts = dict(contract.progress or {})
    counts[goal] = int(counts.get(goal, 0)) + amount
    contract.progress = counts


def _brand_out(brand: dict, config) -> dict:
    goals = config.my_player_sponsor_goals or {}
    return {
        "code": brand["code"], "name": brand["name"], "emoji": brand.get("emoji") or "🏷️",
        "color": brand.get("color") or "#94a3b8",
        "goals": [
            {"code": c, "label": goals.get(c, {}).get("label", c), "target": int(goals.get(c, {}).get("target") or 1),
             "coins": int(goals.get(c, {}).get("coins") or 0), "premium_only": i >= FREE_GOALS}
            for i, c in enumerate(brand.get("goals") or [])
        ],
    }


async def sponsor_view(db: AsyncSession, user: User, now: Optional[datetime] = None) -> dict:
    config = await get_config(db)
    week = week_key(now)
    contract = await _contract(db, user.id, week)
    view = {
        "week": week, "ends_at": week_ends_at(now).isoformat(), "stars": config.my_player_sponsor_stars,
        "premium_pct": config.my_player_sponsor_premium_pct, "bonus_coins": config.my_player_sponsor_bonus_coins,
        "offers": [], "contract": None,
    }
    if contract is None:
        view["offers"] = [_brand_out(b, config) for b in offers_for(user.id, week, config)]
        return view
    brand = _brands(config).get(contract.brand) or {"code": contract.brand, "name": contract.brand}
    goals_cfg = config.my_player_sponsor_goals or {}
    paid = contract.paid or {}
    active = _active_goals(contract)
    goals = []
    for i, code in enumerate(contract.goals or []):
        spec = goals_cfg.get(code, {})
        target = int(spec.get("target") or 1)
        value = int((contract.progress or {}).get(code, 0))
        goals.append({
            "code": code, "label": spec.get("label", code), "target": target, "value": min(value, target),
            "done": value >= target, "claimed": code in paid, "coins": _goal_coins(spec, contract.premium, config),
            "premium_only": i >= FREE_GOALS, "locked": code not in active,
        })
    open_goals = [g for g in goals if not g["locked"]]
    view["contract"] = {
        **{k: v for k, v in _brand_out(brand, config).items() if k != "goals"},
        "premium": contract.premium, "goals": goals,
        "bonus": {
            "coins": _bonus_coins(contract.premium, config), "claimed": "_bonus" in paid,
            "ready": all(g["claimed"] for g in open_goals) and "_bonus" not in paid,
        },
    }
    return view


def claimable(view: dict) -> bool:
    contract = view.get("contract")
    if contract is None:
        return bool(view.get("offers"))
    return any(g["done"] and not g["claimed"] and not g["locked"] for g in contract["goals"]) or contract["bonus"]["ready"]


async def sign_sponsor(db: AsyncSession, user: User, brand_code: str, now: Optional[datetime] = None) -> dict:
    from app.services import my_player_service

    config = await get_config(db)
    my_player_service._require_enabled(config)
    if await my_player_service.get_my_player(db, user.id) is None:
        raise NotFoundError("Сначала создай своего игрока")
    week = week_key(now)
    brand = next((b for b in offers_for(user.id, week, config) if b["code"] == brand_code), None)
    if brand is None:
        raise ConflictError("Этого спонсора нет в предложениях недели")
    if await _contract(db, user.id, week) is not None:
        raise ConflictError("Контракт на эту неделю уже подписан")
    try:
        async with db.begin_nested():
            db.add(MyPlayerSponsorContract(
                user_id=user.id, week=week, brand=brand["code"], goals=list(brand.get("goals") or []),
                progress={}, paid={},
            ))
    except IntegrityError:
        raise ConflictError("Контракт на эту неделю уже подписан")
    await db.commit()
    return await sponsor_view(db, user, now)


async def claim_sponsor(db: AsyncSession, user: User, goal: str, now: Optional[datetime] = None) -> dict:
    """Coins for one done goal, or the bonus ("bonus") once every goal is paid."""
    from app.services import wallet_service

    config = await get_config(db)
    locked = await wallet_service.lock_user_for_update(db, user.id)
    contract = await _contract(db, user.id, week_key(now), lock=True)
    if contract is None:
        raise NotFoundError("Сначала подпиши контракт со спонсором")
    paid = dict(contract.paid or {})
    goals_cfg = config.my_player_sponsor_goals or {}
    active = _active_goals(contract)
    if goal == "bonus":
        if "_bonus" in paid:
            raise ConflictError("Бонус уже получен")
        if any(g not in paid for g in active):
            raise ConflictError("Сначала выполни все цели контракта")
        coins, key, what = _bonus_coins(contract.premium, config), "_bonus", "бонус за все цели"
    else:
        if goal not in active:
            raise ConflictError("Эта цель недоступна в контракте")
        if goal in paid:
            raise ConflictError("Награда уже получена")
        spec = goals_cfg.get(goal, {})
        if int((contract.progress or {}).get(goal, 0)) < int(spec.get("target") or 1):
            raise ConflictError("Цель ещё не выполнена")
        coins, key, what = _goal_coins(spec, contract.premium, config), goal, spec.get("label", goal)
    paid[key] = coins
    contract.paid = paid
    if coins > 0:
        await wallet_service.credit_coins(
            db, locked, coins, TransactionType.my_player_sponsor, f"Спонсор {contract.brand}: {what}",
            related_object_type="my_player_sponsor", related_object_id=contract.id,
        )
    await db.commit()
    view = await sponsor_view(db, locked, now)
    view["balance"] = locked.balance
    return view


def sponsor_order(contract: Optional[MyPlayerSponsorContract], config) -> tuple[str, str, str, int]:
    if config.my_player_sponsor_stars <= 0:
        raise ConflictError("Премиальный контракт сейчас не продаётся")
    if contract is None:
        raise ConflictError("Сначала подпиши контракт со спонсором")
    if contract.premium:
        raise ConflictError("Контракт уже премиальный")
    return (
        f"sponsor:{contract.week}", "Премиальный контракт спонсора",
        f"Четвёртая цель и ×{config.my_player_sponsor_premium_pct / 100:g} монет за цели недели",
        config.my_player_sponsor_stars,
    )


async def sponsor_stars_order(db: AsyncSession, user_id: int, config) -> tuple[str, str, str, int]:
    return sponsor_order(await _contract(db, user_id, week_key()), config)


async def validate_sponsor_stars(db: AsyncSession, invoice, config) -> tuple[bool, str]:
    week = invoice.my_player_purchase.split(":", 1)[1]
    contract = await _contract(db, invoice.user_id, week)
    if config.my_player_sponsor_stars != invoice.stars_amount:
        return False, "Цена изменилась — открой покупку заново"
    if contract is None or contract.premium or week != week_key():
        return False, "Контракт этой недели уже премиальный или закончился"
    return True, ""


async def deliver_sponsor_stars(db: AsyncSession, user: User, invoice, config) -> dict:
    """Premium on, and the goals / bonus already paid topped up to the
    premium rate. The payment is taken: never refuses (a contract of a
    past week still gets the top-up)."""
    from app.services import wallet_service

    week = invoice.my_player_purchase.split(":", 1)[1]
    contract = await _contract(db, user.id, week, lock=True)
    if contract is None or contract.premium:
        return {"kind": "sponsor", "name": "Премиальный контракт спонсора"}
    contract.premium = True
    goals_cfg = config.my_player_sponsor_goals or {}
    paid = dict(contract.paid or {})
    top_up = 0
    for key, coins in list(paid.items()):
        full = _bonus_coins(True, config) if key == "_bonus" else _goal_coins(goals_cfg.get(key, {}), True, config)
        if full > coins:
            top_up += full - coins
            paid[key] = full
    contract.paid = paid
    if top_up > 0:
        locked = await wallet_service.lock_user_for_update(db, user.id)
        await wallet_service.credit_coins(
            db, locked, top_up, TransactionType.my_player_sponsor, f"Спонсор {contract.brand}: доплата за премиум",
            related_object_type="my_player_sponsor", related_object_id=contract.id,
        )
    return {"kind": "sponsor", "name": "Премиальный контракт спонсора"}


async def sponsor_badge(db: AsyncSession, user_id: int, config) -> Optional[dict]:
    """The brand on the player's kit this week (None = no contract)."""
    contract = await _contract(db, user_id, week_key())
    if contract is None:
        return None
    brand = _brands(config).get(contract.brand)
    if brand is None:
        return None
    return {"code": brand["code"], "name": brand["name"], "emoji": brand.get("emoji") or "🏷️",
            "color": brand.get("color") or "#94a3b8", "premium": contract.premium}


# --- limited editions ------------------------------------------------------------------------

def supply_of(code: str, config) -> int:
    return int((config.my_player_limited_supply or {}).get(code) or 0)


async def sold_counts(db: AsyncSession, config) -> dict[str, int]:
    codes = [c for c, n in (config.my_player_limited_supply or {}).items() if int(n or 0) > 0]
    if not codes:
        return {}
    rows = (await db.execute(
        select(MyPlayerEdition.code, func.count(MyPlayerEdition.id)).where(MyPlayerEdition.code.in_(codes))
        .group_by(MyPlayerEdition.code)
    )).all()
    return {code: int(n) for code, n in rows}


async def editions_of(db: AsyncSession, user_id: int) -> dict[str, int]:
    rows = (await db.execute(
        select(MyPlayerEdition.code, MyPlayerEdition.number).where(MyPlayerEdition.user_id == user_id)
    )).all()
    return {code: number for code, number in rows}


async def check_supply(db: AsyncSession, code: str, config) -> None:
    supply = supply_of(code, config)
    if supply and (await sold_counts(db, config)).get(code, 0) >= supply:
        raise ConflictError("Тираж распродан")


async def grant_edition(db: AsyncSession, user_id: int, code: str, config) -> Optional[int]:
    """Next number of a limited item for `user_id` (the one already held, if any).
    Delivery of a paid copy: a race past the supply still gets a number."""
    if not supply_of(code, config):
        return None
    for _ in range(5):
        mine = (await db.execute(
            select(MyPlayerEdition.number).where(MyPlayerEdition.code == code, MyPlayerEdition.user_id == user_id)
        )).scalar_one_or_none()
        if mine is not None:
            return mine
        top = (await db.execute(select(func.max(MyPlayerEdition.number)).where(MyPlayerEdition.code == code))).scalar_one()
        try:
            async with db.begin_nested():
                db.add(MyPlayerEdition(code=code, user_id=user_id, number=int(top or 0) + 1))
            return int(top or 0) + 1
        except IntegrityError:
            continue
    raise ConflictError("Не удалось выдать номер тиража — попробуй ещё раз")


# --- gifts -----------------------------------------------------------------------------------

def patron_of(sent: int, config) -> dict:
    levels = [int(x) for x in (config.my_player_patron_levels or []) if int(x) > 0][:len(PATRON_NAMES)]
    level = sum(1 for threshold in levels if sent >= threshold)
    return {
        "level": level, "name": PATRON_NAMES[level - 1] if level else None, "sent": sent,
        "next_at": levels[level] if level < len(levels) else None,
    }


async def gifts_sent(db: AsyncSession, user_id: int) -> int:
    return int((await db.execute(select(func.count(MyPlayerGift.id)).where(MyPlayerGift.sender_id == user_id))).scalar_one())


async def gift_options(db: AsyncSession, user: User, friend_id: int) -> dict:
    """What can be given to this friend's player — Telegram Stars only."""
    from app.services import my_player_service

    config = await get_config(db)
    mp = await _friend_player(db, user.id, friend_id)
    owned = set(my_player_service.cosmetics_of(mp)["owned"])
    sold = await sold_counts(db, config)
    stars_prices = config.my_player_cosmetic_stars_prices or {}
    options = []
    if config.my_player_extra_training_stars > 0:
        options.append({"code": "training", "kind": "training", "name": "Дополнительная тренировка",
                        "stars": config.my_player_extra_training_stars})
    if config.player_career_enabled and config.player_career_pro_stars > 0:
        options.append({"code": "pro", "kind": "pro", "name": f"«Карьера Pro» на {config.player_career_pro_days} дн.",
                        "stars": config.player_career_pro_stars})
    for code, (kind, name) in my_player_service.COSMETICS.items():
        stars = int(stars_prices.get(code) or 0)
        supply = supply_of(code, config)
        if stars <= 0 or code in owned or (supply and sold.get(code, 0) >= supply):
            continue
        options.append({"code": f"cosmetic:{code}", "kind": kind, "name": name, "stars": stars,
                        "limited": supply or None})
    owner = await db.get(User, friend_id)
    return {"friend": {"user_id": friend_id, "user_name": _name(owner), "player_name": mp.name}, "options": options}


async def _friend_player(db: AsyncSession, user_id: int, friend_id: int) -> MyPlayer:
    from app.services import my_player_service
    from app.services.friend_service import friend_ids

    if friend_id == user_id or friend_id not in await friend_ids(db, user_id):
        raise ConflictError("Подарить можно только другу")
    mp = await my_player_service.get_my_player(db, friend_id)
    if mp is None:
        raise ConflictError("У друга ещё нет своего игрока")
    return mp


async def _gift_price(db: AsyncSession, user_id: int, friend_id: int, code: str, config) -> tuple[str, str, int]:
    """(kind, name, stars) for a gift — refuses what can't be given now."""
    from app.services import my_player_service

    mp = await _friend_player(db, user_id, friend_id)
    if code == "training":
        if config.my_player_extra_training_stars <= 0:
            raise ConflictError("Тренировки за звёзды сейчас не продаются")
        return "training", "Дополнительная тренировка", config.my_player_extra_training_stars
    if code == "pro":
        if not config.player_career_enabled or config.player_career_pro_stars <= 0:
            raise ConflictError("«Карьера Pro» сейчас не продаётся")
        return "pro", f"«Карьера Pro» на {config.player_career_pro_days} дн.", config.player_career_pro_stars
    if code.startswith("cosmetic:"):
        item = code.split(":", 1)[1]
        if item not in my_player_service.COSMETICS:
            raise NotFoundError("Предмет не найден")
        stars = int((config.my_player_cosmetic_stars_prices or {}).get(item) or 0)
        if stars <= 0:
            raise ConflictError("Этот предмет нельзя подарить")
        if item in my_player_service.cosmetics_of(mp)["owned"]:
            raise ConflictError("У друга это уже есть")
        await check_supply(db, item, config)
        return "cosmetic", my_player_service.COSMETICS[item][1], stars
    raise ConflictError("Неизвестный подарок")


async def gift_stars_order(db: AsyncSession, user_id: int, friend_id: Optional[int], code: str, config) -> tuple[str, str, str, int]:
    if friend_id is None:
        raise ConflictError("Кому подарок?")
    kind, name, stars = await _gift_price(db, user_id, friend_id, code, config)
    friend = await db.get(User, friend_id)
    return f"gift:{friend_id}:{code}", f"Подарок: {name}", f"Подарок игроку друга {_name(friend)}: {name}", stars


async def validate_gift_stars(db: AsyncSession, invoice, config) -> tuple[bool, str]:
    _, friend_id, code = invoice.my_player_purchase.split(":", 2)
    try:
        _, _, stars = await _gift_price(db, invoice.user_id, int(friend_id), code, config)
    except (ConflictError, NotFoundError) as exc:
        return False, exc.message
    if stars != invoice.stars_amount:
        return False, "Цена изменилась — открой подарок заново"
    return True, ""


async def deliver_gift_stars(db: AsyncSession, user: User, invoice, config) -> dict:
    """Gives the paid gift to the friend's player and notifies the friend.
    The payment is taken: a cosmetic the friend got meanwhile is just recorded."""
    from app.services import my_player_service, player_career_shop
    from app.services.notification_service import notify

    _, friend_id, code = invoice.my_player_purchase.split(":", 2)
    rid = int(friend_id)
    mp = await my_player_service._locked_player(db, rid)
    if code == "training":
        kind, item, name = "training", None, "Дополнительная тренировка"
        mp.extra_training_credits = (mp.extra_training_credits or 0) + 1
    elif code == "pro":
        kind, item, name = "pro", None, f"«Карьера Pro» на {config.player_career_pro_days} дн."
        await player_career_shop.apply(db, rid, "pro", None, config, strict=False)
    else:
        item = code.split(":", 1)[1]
        kind, name = "cosmetic", my_player_service.COSMETICS.get(item, ("", item))[1]
        if item in my_player_service.COSMETICS and item not in my_player_service.cosmetics_of(mp)["owned"]:
            await grant_edition(db, rid, item, config)
            state = my_player_service.cosmetics_of(mp)
            mp.cosmetics = {**state, "owned": [*state["owned"], item]}
    gift = MyPlayerGift(sender_id=user.id, recipient_id=rid, kind=kind, code=item, name=name, stars=invoice.stars_amount)
    db.add(gift)
    await db.flush()
    await notify(
        db, rid, NotificationType.my_player_gift, "🎁 Подарок для твоего игрока",
        f"{_name(user)} подарил твоему игроку {mp.name}: {name}. Загляни в «Мой игрок»!",
        related_object_type="my_player_gift", related_object_id=gift.id,
    )
    return {"kind": "gift", "name": f"Подарок другу: {name}"}


async def gifts_view(db: AsyncSession, user: User) -> dict:
    """Friends to give to, gifts received (newest first) and the patron level."""
    from app.services import my_player_service
    from app.services.friend_service import friend_ids

    config = await get_config(db)
    ids = await friend_ids(db, user.id)
    players = {mp.user_id: mp for mp in (await db.execute(select(MyPlayer).where(MyPlayer.user_id.in_(ids or [0])))).scalars().all()}
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(list(players) or [0])))).scalars().all()}
    friends = sorted(
        ({"user_id": uid, "user_name": _name(users.get(uid)), "player_name": mp.name,
          "player": my_player_service.player_out(mp, config)} for uid, mp in players.items()),
        key=lambda f: f["user_name"].lower(),
    )
    received_rows = (await db.execute(
        select(MyPlayerGift).where(MyPlayerGift.recipient_id == user.id).order_by(MyPlayerGift.id.desc()).limit(20)
    )).scalars().all()
    senders = {u.id: u for u in (await db.execute(
        select(User).where(User.id.in_({g.sender_id for g in received_rows} or {0}))
    )).scalars().all()}
    return {
        "friends": friends,
        "received": [
            {"id": g.id, "from_name": _name(senders.get(g.sender_id)), "kind": g.kind, "name": g.name,
             "at": ensure_aware(g.created_at).isoformat()}
            for g in received_rows
        ],
        "patron": patron_of(await gifts_sent(db, user.id), config),
    }


# --- cabinet & «Зал славы» ------------------------------------------------------------------

async def cabinet(db: AsyncSession, mp: MyPlayer, config) -> dict:
    """The trophy cabinet: the showcase, lifetime career totals and the
    patron level (trophies themselves come with the view)."""
    from app.services import my_player_service

    stats = mp.career_stats or {}
    return {
        "showcase": my_player_service.cosmetics_of(mp).get("showcase"),
        "totals": {k: int(stats.get(k, 0)) for k in ("seasons", "matches", "goals", "assists", "titles", "top_scorer", "mvp")},
        "cups": int(stats.get("cl_titles", 0)) + int(stats.get("national_titles", 0)),
        "patron": patron_of(await gifts_sent(db, mp.user_id), config),
    }


async def hall_of_fame(db: AsyncSession, user: User, metric: str) -> dict:
    """The best «Мои игроки» of all time: league career totals summed over
    every club, or trophies («Золотой мяч» / all career trophies)."""
    from app.models.player_career import PlayerCareerClubRecord
    from app.models.trophy import TrophyDefinition, UserTrophy
    from app.services import my_player_service

    if metric not in HALL_METRICS:
        raise ConflictError("Неизвестная номинация")
    config = await get_config(db)
    if metric in ("golden_ball", "trophies"):
        codes = ("player_career_golden_ball",) if metric == "golden_ball" else my_player_service.TROPHY_CODES
        value = func.count(UserTrophy.id)
        base = (
            select(UserTrophy.user_id.label("uid"), value.label("value"))
            .join(TrophyDefinition, TrophyDefinition.id == UserTrophy.trophy_definition_id)
            .where(TrophyDefinition.code.in_(codes)).group_by(UserTrophy.user_id)
        )
    else:
        column = getattr(PlayerCareerClubRecord, metric)
        base = (
            select(PlayerCareerClubRecord.user_id.label("uid"), func.sum(column).label("value"))
            .group_by(PlayerCareerClubRecord.user_id)
        )
    ranked = base.subquery()
    rows = (await db.execute(
        select(ranked.c.uid, ranked.c.value).where(ranked.c.value > 0).order_by(ranked.c.value.desc(), ranked.c.uid).limit(HALL_SIZE)
    )).all()
    ids = [uid for uid, _ in rows]
    players = {mp.user_id: mp for mp in (await db.execute(select(MyPlayer).where(MyPlayer.user_id.in_(ids or [0])))).scalars().all()}
    owners = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(ids or [0])))).scalars().all()}
    entries = [
        {"place": i + 1, "user_id": uid, "user_name": _name(owners.get(uid)), "value": int(value),
         "player": my_player_service.player_out(players[uid], config)}
        for i, (uid, value) in enumerate(rows) if uid in players
    ]
    mine = (await db.execute(select(ranked.c.value).where(ranked.c.uid == user.id))).scalar_one_or_none()
    me = None
    if mine:
        above = (await db.execute(select(func.count()).select_from(ranked).where(ranked.c.value > mine))).scalar_one()
        me = {"place": int(above) + 1, "value": int(mine)}
    return {"metric": metric, "entries": entries, "me": me}
