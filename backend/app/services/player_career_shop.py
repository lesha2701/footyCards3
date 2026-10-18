"""«Карьера игрока» paid extras. They buy time, convenience, comfort and
looks — never prestige or results directly:

- «Карьера Pro» (Stars, config.player_career_pro_days): +1 key moment per
  match, +pro_xp_pct% XP from career matches, +1 training a day, the «Pro»
  background and badge;
- an agent (Stars) for one transfer window: +1 offer and better haggling
  odds — applied at once if the window is open, else at the next one;
- full freshness, healing an injury (coins or Stars);
- bringing back a club that walked away (Stars, once per window, no more
  haggling with it);
- a fast season (Stars): a round every config.player_career_fast_round_minutes —
  only while config.player_career_fast_season_enabled (off by default).

Stars orders go through my_player_service.create_stars_invoice /
validate_stars_purchase / deliver_stars_purchase (StarsInvoice.my_player_purchase
"career:<code>[:arg]"); every price is GameConfig.player_career_*.
"""
import copy
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.enums import TransactionType
from app.models.my_player import MyPlayer
from app.models.user import User
from app.services import my_player_service, player_career_life as life, wallet_service

TITLES = {
    "pro": ("«Карьера Pro»", "Ещё один ключевой момент в матче, больше опыта, лишняя тренировка каждый день и фон «Pro»"),
    "agent": ("Агент", "Агент на одно трансферное окно: ещё одно предложение и лучшие шансы в торге"),
    "refresh": ("Полная свежесть", "Твой игрок полностью восстанавливает силы"),
    "heal": ("Лечение травмы", "Игрок сразу возвращается в строй"),
    "save_offer": ("Вернуть клуб", "Клуб, который ушёл после торга, возвращается с прежним предложением"),
    "fast": ("Ускоренный сезон", "Следующий сезон с турами каждые пару часов"),
}


def prices(config) -> dict:
    return {
        "pro_stars": config.player_career_pro_stars, "pro_days": config.player_career_pro_days,
        "pro_xp_pct": config.player_career_pro_xp_pct,
        "agent_stars": config.player_career_agent_stars, "agent_haggle_bonus": config.player_career_agent_haggle_bonus,
        "refresh_coins": config.player_career_refresh_coins, "refresh_stars": config.player_career_refresh_stars,
        "heal_coins": config.player_career_heal_coins, "heal_stars": config.player_career_heal_stars,
        "save_offer_stars": config.player_career_save_offer_stars,
        "fast_enabled": config.player_career_fast_season_enabled,
        "fast_stars": config.player_career_fast_season_stars, "fast_round_minutes": config.player_career_fast_round_minutes,
    }


def _stars(code: str, config) -> int:
    return {
        "pro": config.player_career_pro_stars, "agent": config.player_career_agent_stars,
        "refresh": config.player_career_refresh_stars, "heal": config.player_career_heal_stars,
        "save_offer": config.player_career_save_offer_stars, "fast": config.player_career_fast_season_stars,
    }[code]


async def _locked_mp(db: AsyncSession, user_id: int) -> MyPlayer:
    mp = (await db.execute(
        select(MyPlayer).where(MyPlayer.user_id == user_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if mp is None:
        raise NotFoundError("Сначала создай своего игрока")
    return mp


async def _window(db: AsyncSession, user_id: int):
    """The open transfer window (latest season finished), row-locked, or None."""
    from app.services.player_career_service import _last_season, _lock_season

    last = await _last_season(db, user_id)
    if last is None or last.status != "finished":
        return None
    return await _lock_season(db, last.id)


# --- checks shared by coins and Stars -------------------------------------------------------

async def check(db: AsyncSession, user_id: int, code: str, arg: Optional[str], config) -> None:
    mp = await my_player_service.get_my_player(db, user_id)
    if mp is None:
        raise NotFoundError("Сначала создай своего игрока")
    if code == "fast" and not config.player_career_fast_season_enabled:
        raise ConflictError("Ускоренный сезон сейчас недоступен")
    if code == "heal" and (mp.injury_rounds or 0) <= 0:
        raise ConflictError("Игрок здоров")
    if code == "refresh":
        bonus = await my_player_service.regen_bonus(db, user_id)
        if my_player_service.freshness_now(mp, config, regen_bonus=bonus) >= 100:
            raise ConflictError("Игрок и так полон сил")
    if code == "save_offer":
        from app.services.player_career_service import _last_season

        last = await _last_season(db, user_id)
        state = (last.state or {}) if last is not None and last.status == "finished" else {}
        offer = next((o for o in state.get("offers") or [] if o.get("key") == arg and "salary" in o), None)
        if offer is None or offer["status"] != "withdrawn":
            raise ConflictError("Вернуть можно только клуб, который ушёл в это трансферное окно")
        if state.get("saved"):
            raise ConflictError("Вернуть клуб можно один раз за трансферное окно")


# --- effects ---------------------------------------------------------------------------------

async def apply(db: AsyncSession, user_id: int, code: str, arg: Optional[str], config, strict: bool = True) -> str:
    """Delivers one extra (caller holds the user lock and commits). strict=False
    — a Stars payment already taken — never refuses on soft conditions."""
    mp = await _locked_mp(db, user_id)
    now = datetime.now(timezone.utc)
    if code == "pro":
        start = max(now, ensure_aware(mp.pro_until)) if mp.pro_until else now
        mp.pro_until = start + timedelta(days=config.player_career_pro_days)
        state = my_player_service.cosmetics_of(mp)
        if "bg_pro" not in state["owned"]:
            mp.cosmetics = {**state, "owned": [*state["owned"], "bg_pro"]}
        if mp.pro_bonus_day != now.date():
            mp.extra_training_credits += 1
            mp.pro_bonus_day = now.date()
        return f"«Карьера Pro» до {mp.pro_until.strftime('%d.%m')}"
    if code == "agent":
        mp.agent_credits = (mp.agent_credits or 0) + 1
        await _agent_now(db, user_id, mp, config)
        return "Агент нанят"
    if code == "refresh":
        my_player_service.set_freshness(mp, 100, now)
        return "Свежесть 100%"
    if code == "heal":
        mp.injury_rounds = 0
        return "Игрок здоров"
    if code == "fast":
        mp.fast_season_credits = (mp.fast_season_credits or 0) + 1
        return "Ускоренный сезон готов"
    if code == "save_offer":
        season = await _window(db, user_id)
        if season is None:
            if strict:
                raise ConflictError("Трансферное окно закрыто")
            return "Окно закрыто"
        state = copy.deepcopy(season.state)
        offer = next((o for o in state.get("offers") or [] if o.get("key") == arg and "salary" in o), None)
        if offer is not None and offer["status"] == "withdrawn":
            from app.services.player_career_service import MAX_COUNTERS

            offer.update({"status": "open", "counters": MAX_COUNTERS, "last": "saved"})
            state["saved"] = True
            season.state = state
            flag_modified(season, "state")
        return f"«{offer['name'] if offer else arg}» вернулся"
    raise ConflictError("Неизвестная покупка")


async def _agent_now(db: AsyncSession, user_id: int, mp: MyPlayer, config) -> None:
    """With the transfer window open, the agent works right away: one more
    offer and the haggling bonus for this window."""
    from app.services import player_career_clubs as pcc
    from app.services.player_career_service import make_offers

    season = await _window(db, user_id)
    if season is None or (season.state or {}).get("agent"):
        return
    state = copy.deepcopy(season.state)
    clubs = await pcc.club_catalog(db, config)
    current = pcc.find_club(clubs, mp.club_key)
    taken = {o.get("key") for o in state.get("offers") or []}
    fresh = [o for o in make_offers(clubs, current, mp, config, random.Random(), extra=2) if o["key"] not in taken and not o["renewal"]]
    if fresh:
        state.setdefault("offers", []).append(fresh[0])
    state["agent"] = True
    mp.agent_credits -= 1
    season.state = state
    flag_modified(season, "state")


async def buy_with_coins(db: AsyncSession, user: User, code: str) -> dict:
    """Full freshness or healing for coins."""
    from app.services.game_config_service import get_config
    from app.services.player_career_service import get_view

    config = await get_config(db)
    price = {"refresh": config.player_career_refresh_coins, "heal": config.player_career_heal_coins}.get(code)
    if price is None:
        raise ConflictError("За монеты это не продаётся")
    if price <= 0:
        raise ConflictError("За монеты это сейчас не продаётся")
    await check(db, user.id, code, None, config)
    locked = await wallet_service.lock_user_for_update(db, user.id)
    await wallet_service.debit_coins(
        db, locked, price, TransactionType.player_career_reward, f"Карьера игрока: {TITLES[code][0]}",
        related_object_type="player_career_shop",
    )
    await apply(db, user.id, code, None, config)
    await db.commit()
    return await get_view(db, locked)


# --- Stars (called from my_player_service) ---------------------------------------------------

async def stars_order(db: AsyncSession, user_id: int, code: str, arg: Optional[str], config) -> tuple[str, str, str, int]:
    """(invoice key, title, description, stars) — refuses what can't be bought now."""
    if code not in TITLES:
        raise ConflictError("Неизвестная покупка")
    stars = _stars(code, config)
    if stars <= 0:
        raise ConflictError("За звёзды это сейчас не продаётся")
    await check(db, user_id, code, arg, config)
    key = f"career:{code}" + (f":{arg}" if arg else "")
    if len(key) > 64:
        raise ConflictError("Слишком длинный ключ покупки")
    title, description = TITLES[code]
    return key, title, description, stars


async def validate_stars(db: AsyncSession, invoice, config) -> tuple[bool, str]:
    _, code, *rest = invoice.my_player_purchase.split(":", 2)
    arg = rest[0] if rest else None
    if code not in TITLES or _stars(code, config) != invoice.stars_amount:
        return False, "Цена изменилась — открой покупку заново"
    try:
        await check(db, invoice.user_id, code, arg, config)
    except (ConflictError, NotFoundError) as exc:
        return False, exc.message
    return True, ""


async def deliver_stars(db: AsyncSession, user: User, invoice, config) -> dict:
    _, code, *rest = invoice.my_player_purchase.split(":", 2)
    name = await apply(db, user.id, code, rest[0] if rest else None, config, strict=False)
    return {"kind": f"career_{code}", "name": name}


def view(mp: MyPlayer, config) -> dict:
    """What the career page shows about the extras."""
    return {
        **prices(config),
        "pro": life.is_pro(mp), "pro_until": ensure_aware(mp.pro_until).isoformat() if mp.pro_until else None,
        "agent_credits": mp.agent_credits or 0, "fast_season_credits": mp.fast_season_credits or 0,
    }
