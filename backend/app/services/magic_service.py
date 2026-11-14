"""«Мяч и Магия» — DB layer around magic_engine: the army (stacks built from
the player's duplicates: one footballer = one stack, his card's rarity =
the creature's tier, his number of copies = the stack size), runs, limits
and rewards.

A run lives in `MagicRun.server_state`. Every action carries the run
`version` under the row lock: a stale one gets 409, a retried one (the same
request as the last accepted) returns the run unchanged. The mode is played
against a bot only, so its weekly rating moves by difficulty and is capped
by the daily ranked limit (anti_bot_service.take_ranked_slot) instead of the
bot-win cut other modes use for their bot matches.
"""
import copy
import random
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.card import UserCard
from app.models.enums import CardSource, TransactionType
from app.models.game_config import GameConfig
from app.models.magic import MagicRun
from app.models.monetization import Cosmetic
from app.models.pack import Pack
from app.models.player import Player
from app.models.user import User
from app.schemas.magic import (
    MagicArmyOut,
    MagicArtifactOut,
    MagicBattleOut,
    MagicArmyStackOut,
    MagicCaptainOut,
    MagicCardOut,
    MagicDifficultyOut,
    MagicModeOut,
    MagicChallengeOut,
    MagicChallengeRowOut,
    MagicEffectOut,
    MagicExtraRunOut,
    MagicCreatureOut,
    MagicCreaturePackOut,
    MagicFactionOut,
    MagicHeroClassOut,
    MagicPackOpenOut,
    MagicHeroOut,
    MagicHubOut,
    MagicMapObjectOut,
    MagicOfferOut,
    MagicPackCardOut,
    MagicRunHeroOut,
    MagicRunOut,
    MagicSpellOut,
    MagicStackOut,
    MagicTargetOut,
    MagicUnitOut,
    MagicCasualtiesOut,
    MagicCasualtyOut,
    MagicHealOut,
    MagicRiskOut,
    MagicWoundedOut,
    MagicShopBuyOut,
    MagicShopItemOut,
    MagicShopOut,
    MagicGuardMaterialOut,
    MagicGuardOut,
    MagicReviveOut,
    MagicTraitOut,
)
from app.schemas.ranking import RankingMetric
from app.services import anti_bot_service, collection_service, cosmetic_service, ranking_service
from app.services import magic_engine as engine
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update

RELATED = "magic_run"
CANDIDATES = 60
RATING_PCT = {"easy": 50, "normal": 100, "hard": 150}
EFFECT_LABELS = {"bless": "Благословение", "wall": "Стена света", "curse": "Проклятие"}
OBJECT_EMOJI = {"chest": "💰", "well": "🔮", "tribune": "🏟️", "reinforce": "🎁", "castle": "🏰", "market": "⚖️",
                "mine": "⛏️", "training": "🎽", "floodtower": "💡", "medic": "⛑️", "tunnel": "🌀", "shrine": "🕯️"}
OBJECT_HINT = {
    "chest": "Золото или опыт героя — на выбор", "well": "Мана до полной и +1 к запасу",
    "tribune": "Болельщики пополнят павших бойцов", "reinforce": "Новый отряд в армию",
    "castle": "Замок соперника — вызов на финальную битву", "market": "Найм отрядов за золото похода",
    "mine": f"+{engine.MINE_GOLD} золота каждое утро",
    "training": f"Сборы: армия бьёт на {engine.TRAINING_PCT}% сильнее до конца похода",
    "floodtower": "Прожектор разгонит туман далеко вокруг",
    "medic": f"Вся армия снова в строю. Приём раз в {engine.MEDIC_EVERY} дней",
    "tunnel": "Проход под трибунами к другому концу карты",
    "shrine": "Оберег от гипноза Безликого и разведка ближайшего логова",
}
CAMP_LABEL = {1: "Слабый лагерь", 2: "Лагерь", 3: "Сильный лагерь", 4: "Логово Потерявших всё"}


def _require_enabled(config: GameConfig) -> None:
    if not config.magic_enabled:
        raise ConflictError("«Мяч и Магия» сейчас недоступна", details={"reason": "disabled"})


def _val(v) -> str:
    return v.value if hasattr(v, "value") else str(v)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

def _spell_out(code: str) -> MagicSpellOut:
    name, cost, target, description = engine.SPELLS[code]
    return MagicSpellOut(code=code, name=name, cost=cost, target=target, description=description)


def _factions_out() -> list[MagicFactionOut]:
    out = []
    for f in engine.FACTIONS.values():
        units = []
        variants = [(alt, group) for tier, groups in engine.VARIANTS.get(f["code"], {}).items()
                    for group, alt in groups.items()]
        seen_alt: set = set()
        for code, note in [(c, "") for c in f["units"]] + [(a, engine.VARIANT_NOTE[g]) for a, g in variants]:
            if code in seen_alt:
                continue
            seen_alt.add(code)
            u = engine.UNITS[code]
            units.append(MagicUnitOut(
                code=code, name=u["name"], tier=u["tier"], emoji=u["emoji"], ranged=u["ranged"], flying=u["flying"],
                ability_text=u["ability_text"], hp=u["hp"], atk=u["atk"], defence=u["def"], dmin=u["dmin"],
                dmax=u["dmax"], spd=u["spd"], note=note,
            ))
        units.sort(key=lambda u: (u.tier, u.note != ""))
        spells = []
        for i, code in enumerate(f["spells"]):
            s = _spell_out(code)
            s.level = 1 if i < 2 else 3
            spells.append(s)
        out.append(MagicFactionOut(code=f["code"], name=f["name"], emoji=f["emoji"], tagline=f["tagline"],
                                   units=units, spells=spells))
    return out


def _reward_pct(config: GameConfig, difficulty: str) -> int:
    return {"easy": config.magic_easy_reward_pct, "hard": config.magic_hard_reward_pct}.get(difficulty, 100)


# Hardcore: a much bigger map and more days — and a bigger prize for it.
MODE_REWARD_PCT = {"quick": 100, "hardcore": 250, "adventure": 400}
# Hero XP is the run's score: the quick run's long step and 7 camps a side score ~1.3× more,
# so it counts ×0.75 (same pace); a hardcore run scores about as much as the 2 quick runs it costs.
# «Приключение» (4 runs) scores ~2000: ×0.75 gives what 4 quick runs do.
MODE_XP_PCT = {"quick": 75, "hardcore": 100, "adventure": 75}
# Gold left at the end → coins: the adventure piles up ~5× a quick run's gold, so a quarter counts.
MODE_GOLD_PCT = {"adventure": 25}
MODE_PACK_PCT = {"quick": 100, "hardcore": 200, "adventure": 400}


def _pack_chance(config: GameConfig, difficulty: str) -> int:
    if config.magic_pack_id is None:
        return 0
    return {"normal": config.magic_pack_chance_normal_pct, "hard": config.magic_pack_chance_hard_pct}.get(difficulty, 0)


# ---------------------------------------------------------------------------
# Army: one footballer = one stack
# ---------------------------------------------------------------------------

def _tier(player: Player) -> int:
    return engine.TIER_BY_RARITY.get(_val(player.rarity), 1)


def _card_out(player: Player) -> MagicCardOut:
    return MagicCardOut(
        player_id=player.id, name=player.display_name, image_path=player.image_path,
        rarity=_val(player.rarity), rating=player.rating, position=_val(player.position), club=player.club,
    )


async def _owned(db: AsyncSession, user_id: int) -> list[tuple[Player, int]]:
    """(player, copies) of every footballer version the user owns."""
    rows = (await db.execute(
        select(Player, func.count(UserCard.id))
        .join(UserCard, UserCard.player_id == Player.id)
        .where(UserCard.owner_id == user_id, UserCard.is_locked_by_admin.is_(False))
        .group_by(Player.id)
    )).all()
    return [(p, int(n)) for p, n in rows]


def _captain_cap(player: Player) -> int:
    return engine.CAPTAIN_CAP.get(_val(player.rarity), 2)


def _have(user: User) -> dict[str, int]:
    have = (user.magic_creatures or {}).get("have") or {}
    return {code: n for code, n in have.items() if n > 0 and code in engine.UNITS}


def _hero_class_of(user: User, hero_class: Optional[str]) -> str:
    code = hero_class or (user.magic_army or {}).get("hero_class") or "knight"
    return code if code in engine.HERO_CLASSES else "knight"


def _build_stacks(picks: list[tuple[str, Optional[Player]]], have: dict[str, int], cap: int,
                  budget: int, user: Optional[User] = None) -> tuple[list[MagicArmyStackOut], int]:
    """The marching stacks in order; the ones past the leadership budget are unruly (half the fighters)."""
    out, used = [], 0
    for code, captain in picks:
        u = engine.UNITS[code]
        cost = engine.STACK_COST[u["tier"]]
        unruly = used + cost > budget
        used += cost
        count = min(cap, have.get(code, 0))
        if unruly:
            count = max(1, count // 2)
        bonus = max(-3, min(5, (captain.rating - 75) // 4)) if captain else 0
        power = int(count * engine.unit_value(u) * (1 + bonus * 0.06))
        out.append(MagicArmyStackOut(
            unit=code, name=u["name"], emoji=u["emoji"], faction=u["faction"], tier=u["tier"], have=have.get(code, 0),
            count=count, cost=cost, unruly=unruly, power=power, captain=_card_out(captain) if captain else None,
            captain_level=_cap_level(user, captain.id) if captain and user else 1,
            captain_traits=_cap_row(user, captain.id).get("traits", []) if captain and user else [],
        ))
    return out, used


def _auto_picks(have: dict[str, int], owned: list[tuple[Player, int]], cap: int,
                budget: int) -> list[tuple[str, Optional[Player]]]:
    """The strongest creatures that fit the leadership, each led by the best captain allowed for it."""
    ranked = sorted(have, key=lambda c: (-min(cap, have[c]) * engine.unit_value(engine.UNITS[c]), c))
    units, used = [], 0
    for code in ranked:
        cost = engine.STACK_COST[engine.UNITS[code]["tier"]]
        if len(units) < engine.MAX_STACKS and used + cost <= budget:
            units.append(code)
            used += cost
    if not units and ranked:
        units = [ranked[-1]]
    # Captains: the strongest tiers pick first.
    free = sorted((p for p, _ in owned), key=lambda p: (-p.rating, p.id))
    picks: dict[str, Optional[Player]] = {}
    for code in sorted(units, key=lambda c: -engine.UNITS[c]["tier"]):
        tier = engine.UNITS[code]["tier"]
        best = next((p for p in free if _captain_cap(p) >= tier), None)
        if best:
            free.remove(best)
        picks[code] = best
    return [(c, picks[c]) for c in units]


async def _army(db: AsyncSession, user: User, config: GameConfig, hero_class: Optional[str] = None,
                ) -> tuple[list[MagicArmyStackOut], bool, int, int, list[tuple[Player, int]]]:
    """(the army's stacks, is it the automatic pick, leadership budget, used, the owned footballers)."""
    owned = await _owned(db, user.id)
    players = {p.id: p for p, _ in owned}
    have = _have(user)
    level = engine.hero_level(user.magic_hero_xp)
    budget = engine.leadership(level, _hero_class_of(user, hero_class)) + _bonus(user, "leadership")
    cap = config.magic_stack_cap
    saved = (user.magic_army or {}).get("stacks") or []
    picks: list[tuple[str, Optional[Player]]] = []
    seen_units: set = set()
    seen_caps: set = set()
    for row in saved:
        code, pid = row.get("unit"), row.get("captain")
        if code not in have or code in seen_units:
            continue
        captain = players.get(pid) if pid else None
        if captain and (pid in seen_caps or _captain_cap(captain) < engine.UNITS[code]["tier"]):
            captain = None
        seen_units.add(code)
        if captain:
            seen_caps.add(pid)
        picks.append((code, captain))
    picks = picks[:engine.MAX_STACKS]
    auto = not picks
    if auto:
        picks = _auto_picks(have, owned, cap, budget)
    stacks, used = _build_stacks(picks, have, cap, budget, user)
    return stacks, auto, budget, used, owned


async def get_army(db: AsyncSession, user: User, hero_class: Optional[str] = None) -> MagicArmyOut:
    config = await get_config(db)
    await _ensure_starter(db, user)
    stacks, auto, budget, used, owned = await _army(db, user, config, hero_class)
    captains = sorted((_captain_out(user, p, n, config) for p, n in owned),
                      key=lambda c: (-c.level, -c.cap, -c.card.rating, c.card.player_id))
    return MagicArmyOut(
        guard=await _guard_out(db, user, owned), traits=_traits_out(),
        captain_xp=list(engine.CAPTAIN_XP), guard_xp=list(engine.GUARD_XP),
        stacks=stacks, creatures=_creatures_out(user), captains=captains[:CANDIDATES],
        max_stacks=engine.MAX_STACKS, stack_cap=config.magic_stack_cap, auto=auto,
        hero_class=_hero_class_of(user, hero_class), leadership=budget, leadership_used=used,
        costs=dict(engine.STACK_COST),
    )


async def set_army(db: AsyncSession, user: User, picks: list, hero_class: Optional[str] = None) -> MagicArmyOut:
    units = [p.unit for p in picks]
    if not 1 <= len(units) <= engine.MAX_STACKS or len(set(units)) != len(units):
        raise ConflictError(f"В армии от 1 до {engine.MAX_STACKS} разных отрядов")
    have = _have(user)
    if not set(units) <= set(have):
        raise ForbiddenError("Можно брать только существ из своей коллекции")
    players = {p.id: p for p, _ in await _owned(db, user.id)}
    caps = [p.captain for p in picks if p.captain is not None]
    if len(set(caps)) != len(caps):
        raise ConflictError("Один футболист ведёт только один отряд")
    for p in picks:
        if p.captain is None:
            continue
        captain = players.get(p.captain)
        if captain is None:
            raise ForbiddenError("Капитаном можно назначить только своего футболиста")
        if _captain_cap(captain) < engine.UNITS[p.unit]["tier"]:
            raise ConflictError(f"{captain.display_name} может вести существ до уровня {_captain_cap(captain)}")
    user.magic_army = {"stacks": [{"unit": p.unit, "captain": p.captain} for p in picks],
                       "hero_class": _hero_class_of(user, hero_class)}
    flag_modified(user, "magic_army")
    db.add(user)
    await db.commit()
    return await get_army(db, user, hero_class)


async def auto_army(db: AsyncSession, user: User, hero_class: Optional[str] = None) -> MagicArmyOut:
    keep = _hero_class_of(user, hero_class)
    user.magic_army = {"hero_class": keep}
    flag_modified(user, "magic_army")
    db.add(user)
    await db.commit()
    return await get_army(db, user, hero_class)


# ---------------------------------------------------------------------------
# Limits, hub
# ---------------------------------------------------------------------------

def _ensure_hourly_reset(user: User) -> None:
    now = datetime.now(timezone.utc)
    if user.magic_hour_started_at is None or now - ensure_aware(user.magic_hour_started_at) >= timedelta(hours=1):
        user.magic_hourly_attempts = 0
        user.magic_hour_started_at = now


def _is_today(user: User) -> bool:
    return bool(user.magic_attempts_reset_at) and local_today(user.magic_attempts_reset_at) == local_today()


def _ensure_daily_reset(user: User) -> None:
    if not _is_today(user):
        user.magic_rewarded_attempts_today = 0
        user.magic_extra_runs_today = 0
        user.magic_retries_today = 0
        user.magic_attempts_reset_at = datetime.now(timezone.utc)


def _today(user: User) -> tuple[int, int, int]:
    """(free runs started, extra runs bought, second chances used) today — without resetting."""
    if not _is_today(user):
        return 0, 0, 0
    return user.magic_rewarded_attempts_today, user.magic_extra_runs_today, user.magic_retries_today


# Runs are counted per mode, each with its own day: free runs, then COIN_BUYS for coins,
# then a few for Stars. A bought run waits in that mode's bank until the day ends.
RUN_MODES = ("quick", "hardcore", "adventure", "challenge")
COIN_BUYS = 1


def _run_rules(config: GameConfig, mode: str) -> tuple[int, int, int, int]:
    """(free runs a day, coin price, Stars price, runs for Stars a day) of a mode."""
    if mode == "hardcore":
        return (config.magic_hardcore_daily_limit, config.magic_hardcore_run_coins,
                config.magic_hardcore_run_stars, config.magic_hardcore_star_runs)
    if mode == "adventure":
        return (config.magic_adventure_daily_limit, config.magic_adventure_run_coins,
                config.magic_adventure_run_stars, config.magic_adventure_star_runs)
    if mode == "challenge":
        return 1, 0, 0, 0  # the weekly challenge: one try a day, never sold
    return config.magic_daily_limit, config.magic_extra_run_coins, config.magic_extra_run_stars, config.magic_extra_runs_daily_limit


def _runs_day(user: User) -> dict:
    day = local_today().isoformat()
    data = user.magic_runs_day if isinstance(user.magic_runs_day, dict) else {}
    return dict(data) if data.get("day") == day else {"day": day}


def _run_row(user: User, mode: str) -> dict:
    return {"free": 0, "coins": 0, "stars": 0, "bank": 0, **(_runs_day(user).get(mode) or {})}


def _save_row(user: User, mode: str, row: dict) -> None:
    data = _runs_day(user)
    data[mode] = row
    user.magic_runs_day = data  # a new dict: the JSON column sees the change


def _runs_status(config: GameConfig, user: User, mode: str) -> dict:
    free, coins, stars, star_buys = _run_rules(config, mode)
    row = _run_row(user, mode)
    return {
        "free_total": free, "free_left": max(0, free - row["free"]), "bank": row["bank"],
        "price_coins": coins if coins > 0 and row["coins"] < COIN_BUYS else None,
        "price_stars": stars if stars > 0 and row["stars"] < star_buys else None,
        "stars_left": max(0, star_buys - row["stars"]) if stars > 0 else 0,
    }


def _extra_price(config: GameConfig, user: User, mode: str = "quick") -> tuple[Optional[int], Optional[int]]:
    """(coins, Stars) of the next run bought for `mode`: the day's first for coins, then for Stars."""
    st = _runs_status(config, user, mode)
    if st["price_coins"] is not None:
        return st["price_coins"], None
    return None, st["price_stars"]


def _free_left(config: GameConfig, user: User, mode: str = "quick") -> int:
    return _runs_status(config, user, mode)["free_left"]


def _run_mode(mode: str) -> str:
    if mode not in RUN_MODES or mode == "challenge":
        raise ConflictError("Неизвестный режим")
    return mode


def _parse_run_arg(arg: str) -> tuple[str, str]:
    """«magic_run:<mode>:<day>» (old invoices: «magic_run:<day>» — the quick mode)."""
    mode, _, day = arg.partition(":")
    return (mode, day) if day else ("quick", mode)


async def _skins(db: AsyncSession, user: User) -> tuple[str, str]:
    """The equipped hero / castle skins as the style the frontend draws ("default" when none)."""
    from app.models.monetization import Cosmetic

    out = []
    for cid, prefix in ((user.equipped_magic_hero_id, "magic_hero_"), (user.equipped_magic_castle_id, "magic_castle_")):
        c = await db.get(Cosmetic, cid) if cid else None
        out.append(c.style_key.removeprefix(prefix) if c else "default")
    return out[0], out[1]


async def _active_run(db: AsyncSession, user_id: int) -> Optional[int]:
    return (await db.execute(
        select(MagicRun.id).where(MagicRun.user_id == user_id, MagicRun.status == "in_progress")
        .order_by(MagicRun.id.desc()).limit(1)
    )).scalar_one_or_none()


def _hero_out(user: User) -> MagicHeroOut:
    level = engine.hero_level(user.magic_hero_xp)
    start, nxt = engine.level_bounds(level)
    return MagicHeroOut(level=level, xp=user.magic_hero_xp, level_start=start, next_level_xp=nxt,
                        mana=6 + level, spell_power=1 + level // 3)


def _week_key(now: Optional[datetime] = None) -> tuple[str, datetime]:
    """The ISO week of the weekly challenge and when it ends (Monday 00:00 UTC)."""
    now = now or datetime.now(timezone.utc)
    year, week, weekday = now.isocalendar()
    monday = (now - timedelta(days=weekday - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return f"{year}-W{week:02d}", monday + timedelta(days=7)


async def _challenge(db: AsyncSession, user: User) -> MagicChallengeOut:
    week, ends = _week_key()
    best = func.max(MagicRun.score).label("best")
    rows = (await db.execute(
        select(MagicRun.user_id, best)
        .where(MagicRun.challenge_week == week, MagicRun.status == "finished")
        .group_by(MagicRun.user_id).order_by(best.desc()).limit(10)
    )).all()
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_([r[0] for r in rows])))).scalars()} if rows else {}
    mine = (await db.execute(
        select(func.max(MagicRun.score), func.count(MagicRun.id))
        .where(MagicRun.challenge_week == week, MagicRun.user_id == user.id, MagicRun.status == "finished")
    )).one()
    return MagicChallengeOut(
        week=week, ends_at=ends, best=mine[0], plays=mine[1] or 0,
        top=[MagicChallengeRowOut(rank=i, name=users[r[0]].full_display_name() if r[0] in users else "—",
                                  score=r[1] or 0, me=r[0] == user.id) for i, r in enumerate(rows, 1)],
    )


async def get_hub(db: AsyncSession, user: User) -> MagicHubOut:
    config = await get_config(db)
    await _ensure_starter(db, user)
    stacks, _, budget, used, _ = await _army(db, user, config)
    ranking = await ranking_service.get_ranking(db, RankingMetric.magic_rating, user, limit=5)
    pack = await db.get(Pack, config.magic_pack_id) if config.magic_pack_id else None
    free_used, extra, retries = _today(user)
    coins, stars = _extra_price(config, user)
    hero_skin, castle_skin = await _skins(db, user)
    quick = _runs_status(config, user, "quick")
    challenge_runs = _runs_status(config, user, "challenge")
    return MagicHubOut(
        free_left=quick["free_left"], bonus_runs=quick["bank"], extra_runs_today=extra,
        extra_runs_limit=quick["stars_left"] + (1 if quick["price_coins"] is not None else 0),
        extra_price_coins=coins, extra_price_stars=stars,
        can_start=any(_runs_status(config, user, m)["free_left"] or _runs_status(config, user, m)["bank"] for m in engine.MODES),
        challenge_left=challenge_runs["free_left"],
        retry_coins=config.magic_retry_coins,
        retry_stars=config.magic_retry_stars, retries_left=max(0, config.magic_retries_daily_limit - retries),
        retry_credits=user.magic_retry_credits, gold_coins_pct=config.magic_gold_coins_pct,
        hero_skin=hero_skin, castle_skin=castle_skin,
        enabled=config.magic_enabled, hero=_hero_out(user), rating=user.magic_rating,
        rank=ranking.me.rank if ranking.me else None, wins=user.magic_wins,
        active_run_id=await _active_run(db, user.id),
        rewarded_today=free_used,
        daily_limit=config.magic_daily_limit, reward_win=config.magic_reward_win, reward_loss=config.magic_reward_loss,
        pack_name=pack.name if pack else None, days=config.magic_days, moves_per_day=config.magic_moves_per_day,
        factions=_factions_out(),
        hero_classes=[
            MagicHeroClassOut(code=c["code"], name=c["name"], emoji=c["emoji"], tagline=c["tagline"],
                              mana=engine.hero_base(engine.hero_level(user.magic_hero_xp), c["code"])[0] + _bonus(user, "mana"),
                              spell_power=engine.hero_base(engine.hero_level(user.magic_hero_xp), c["code"])[1],
                              moves=config.magic_moves_per_day + engine.QUICK_LAYOUT["extra_moves"] + c["moves"])
            for c in engine.HERO_CLASSES.values()
        ],
        skin_classes=engine.SKIN_CLASS,
        creatures=_creatures_out(user), creature_pack=_pack_out(config),
        last_pack=[_creature_out(c, engine.CARD_FIGHTERS[engine.UNITS[c]["tier"]])
                   for c in (user.magic_creatures or {}).get("last_pack") or [] if c in engine.UNITS],
        essence=int((user.magic_creatures or {}).get("essence") or 0), wounded=_wounded_out(user),
        heal_essence=_heal_cost(config, user), heal_stars=config.magic_heal_stars or None, risk=_risk_out(config),
        refill_today=(user.magic_creatures or {}).get("refill_day") == _day_key(),
        revive=_revive_out(user), guard=await _guard_out(db, user, None),
        difficulties=[
            MagicDifficultyOut(code=code, label=d["label"], reward_pct=_reward_pct(config, code),
                               pack_chance_pct=_pack_chance(config, code),
                               rating_win=config.magic_rating_win * RATING_PCT[code] // 100)
            for code, d in engine.DIFFICULTY.items()
        ],
        army=stacks, leadership=budget, leadership_used=used, top=ranking.top,
        leadership_by_class={c: engine.leadership(engine.hero_level(user.magic_hero_xp), c) + _bonus(user, "leadership")
                             for c in engine.HERO_CLASSES},
        modes=[
            MagicModeOut(code=code, label=m["label"], days=config.magic_days + m["extra_days"],
                         cells=len(engine.BANDS[code]), reward_pct=MODE_REWARD_PCT[code], pack_chance_pct=MODE_PACK_PCT[code],
                         runs=1, moves=config.magic_moves_per_day + m["extra_moves"], **_runs_status(config, user, code))
            for code, m in engine.MODES.items()
        ],
        challenge=await _challenge(db, user),
    )


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

async def start_run(db: AsyncSession, user: User, faction: str, difficulty: str, mode: str = "quick",
                    challenge: bool = False, hero_class: str = "knight") -> MagicRunOut:
    config = await get_config(db)
    _require_enabled(config)
    locked = await lock_user_for_update(db, user.id)
    active = await _active_run(db, locked.id)
    if active is not None:
        raise ConflictError("Сначала доиграй текущий поход", details={"active_run_id": active})
    # A run takes a while: the day's runs may be played in a row (no shared hourly cap here).
    _ensure_hourly_reset(locked)
    await _ensure_starter(db, locked)
    _settle_creatures(locked)
    stacks, _, _, _, _ = await _army(db, locked, config, hero_class)
    if not stacks:
        raise ConflictError("Для похода нужна хотя бы одна карта существа")
    _ensure_daily_reset(locked)
    # Each mode has its own runs of the day: a free one first, then one bought for this mode.
    key = "challenge" if challenge else (mode if mode in engine.MODES else "quick")
    st = _runs_status(config, locked, key)
    row = _run_row(locked, key)
    if st["free_left"] > 0:
        row["free"] += 1
        locked.magic_rewarded_attempts_today += 1
    elif st["bank"] > 0:
        row["bank"] -= 1
    else:
        coins, stars = _extra_price(config, locked, key) if key != "challenge" else (None, None)
        label = "Испытание недели" if challenge else engine.MODES[key]["label"]
        raise ConflictError(f"{label}: походы на сегодня закончились", details={
            "reason": "no_runs", "mode": key, "price_coins": coins, "price_stars": stars,
        })
    _save_row(locked, key, row)
    # The creatures march under their captains (a footballer gives rating → atk/def, position → trait).
    cap_level = max(1, config.magic_challenge_level_cap) if challenge else None

    def capped(level: int, traits: list, levels: tuple) -> tuple[int, list]:
        if cap_level is None:
            return level, traits
        level = min(level, cap_level)
        return level, list(traits)[:engine.trait_slots(level, levels)]

    army = []
    for s in stacks:
        lv, tr = capped(s.captain_level, s.captain_traits, engine.CAPTAIN_TRAIT_LEVELS)
        army.append({
            "unit": s.unit, "count": s.count, "copies": 1,
            "rating": s.captain.rating if s.captain else 75, "position": s.captain.position if s.captain else None,
            "card": s.captain.model_dump() if s.captain else None, "captain_level": lv, "traits": tr,
        })
    guard = await _guard_for_run(db, locked)
    if guard and cap_level is not None:
        guard["level"], guard["traits"] = capped(guard["level"], guard["traits"], engine.GUARD_TRAIT_LEVELS)
        guard["count"] = min(guard["count"], engine.guard_size(guard["level"], guard["unit"]))
    level = engine.hero_level(locked.magic_hero_xp)
    week = None
    if challenge:
        # Everyone plays the same map this week (the seed), on the quick map at normal difficulty.
        week, _ = _week_key()
        mode, difficulty = "quick", "normal"
    try:
        state = engine.new_run(
            f"challenge-{week}" if week else secrets.token_hex(8), faction=faction, difficulty=difficulty, army=army, hero_level_=level,
            days=max(1, config.magic_days), moves_per_day=max(1, config.magic_moves_per_day),
            stack_cap=max(1, config.magic_stack_cap), mode=mode, hero_class=hero_class,
            mana_bonus=0 if challenge else _bonus(locked, "mana"), guard=guard,
            scaling_pct=config.magic_progress_scaling_pct,
        )
    except engine.EngineError as exc:
        raise ConflictError(str(exc))
    hero_skin, castle_skin = await _skins(db, locked)
    state["skins"] = {"hero": engine.skin_for(hero_skin, hero_class), "castle": castle_skin}
    state["rewarded"] = True
    state["marched"] = {"captains": [s.captain.player_id for s in stacks if s.captain],
                        "guard": guard["card"]["player_id"] if guard else None}
    locked.magic_hourly_attempts += 1
    db.add(locked)
    if week:
        state["challenge"] = week
    run = MagicRun(user_id=locked.id, faction=faction, difficulty=difficulty, server_state=state, challenge_week=week)
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return await _hydrate(db, run, [])


async def _lock_run(db: AsyncSession, run_id: int, user: User) -> MagicRun:
    run = (await db.execute(
        select(MagicRun).where(MagicRun.id == run_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if run is None or run.user_id != user.id:
        raise NotFoundError("Поход не найден")
    return run


def _battle_n(state: dict) -> int:
    b = state.get("battle")
    return b["n"] if b else 0


async def _mutate(db: AsyncSession, user: User, run_id: int, version: int, request: dict,
                  apply: Callable[[dict], None]) -> MagicRunOut:
    run = await _lock_run(db, run_id, user)
    if (run.server_state or {}).get("last_action") == {**request, "version": version}:
        return await _hydrate(db, run, [])  # a retried request
    if run.status != "in_progress":
        raise ConflictError("Поход окончен")
    if version != run.version:
        raise ConflictError("Поход ушёл вперёд — обнови экран", details={"version": run.version})
    state = copy.deepcopy(run.server_state)
    state["notice"] = None
    before_battle = state.get("battle")
    before = _battle_n(state)
    try:
        apply(state)
    except engine.EngineError as exc:
        raise ConflictError(str(exc))
    battle = state.get("battle")
    if battle is None:
        events = []
    elif before_battle is None or battle["n"] < before:  # a battle that started with this action
        events = list(battle["events"])
    else:
        events = [e for e in battle["events"] if e["n"] > before]
    if battle and len(battle["events"]) > 400:
        battle["events"] = battle["events"][-200:]
    state["last_action"] = {**request, "version": version}
    run.version += 1
    run.score = state["score"]
    if state["finished"]:
        await _finish(db, run, state)
    run.server_state = state
    flag_modified(run, "server_state")
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return await _hydrate(db, run, events, fresh=True)


async def move(db: AsyncSession, user: User, run_id: int, version: int, x: int, y: int) -> MagicRunOut:
    return await _mutate(db, user, run_id, version, {"a": "move", "x": x, "y": y},
                         lambda s: engine.move_hero(s, x, y))


async def end_day(db: AsyncSession, user: User, run_id: int, version: int) -> MagicRunOut:
    return await _mutate(db, user, run_id, version, {"a": "end_day"}, engine.end_day)


async def choose(db: AsyncSession, user: User, run_id: int, version: int, option: str) -> MagicRunOut:
    return await _mutate(db, user, run_id, version, {"a": "choose", "option": option},
                         lambda s: engine.choose(s, option))


async def buy(db: AsyncSession, user: User, run_id: int, version: int, object_id: str, index: int) -> MagicRunOut:
    return await _mutate(db, user, run_id, version, {"a": "buy", "object": object_id, "index": index},
                         lambda s: engine.buy(s, object_id, index))


async def accept_defeat(db: AsyncSession, user: User, run_id: int, version: int) -> MagicRunOut:
    return await _mutate(db, user, run_id, version, {"a": "accept"}, engine.accept_defeat)


# --- «Второй шанс»: replay a lost final (coins, or a credit bought with Stars) ---------

async def retry_final(db: AsyncSession, user: User, run_id: int, version: int, pay: str) -> MagicRunOut:
    config = await get_config(db)
    run = await _lock_run(db, run_id, user)
    if (run.server_state or {}).get("last_action") == {"a": "retry", "version": version}:
        return await _hydrate(db, run, [])  # a retried request: never charge twice
    state = run.server_state or {}
    if run.status != "in_progress" or state.get("phase") != "final_lost":
        raise ConflictError("Переиграть можно только проигранный финал")
    if state.get("retry_used"):
        raise ConflictError("Второй шанс в этом походе уже был")
    if version != run.version:
        raise ConflictError("Поход ушёл вперёд — обнови экран", details={"version": run.version})
    locked = await lock_user_for_update(db, user.id)
    _ensure_daily_reset(locked)
    if locked.magic_retries_today >= config.magic_retries_daily_limit:
        raise ConflictError("Вторые шансы на сегодня закончились")
    if pay == "credit":
        if locked.magic_retry_credits <= 0:
            raise ConflictError("Нет оплаченного второго шанса")
        locked.magic_retry_credits -= 1
    else:
        if config.magic_retry_coins <= 0:
            raise ConflictError("Второй шанс сейчас только за звёзды")
        await debit_coins(db, locked, config.magic_retry_coins, TransactionType.magic_purchase,
                          "«Мяч и Магия»: второй шанс в финале", RELATED, run.id)
    locked.magic_retries_today += 1
    db.add(locked)
    return await _mutate(db, user, run_id, version, {"a": "retry"}, engine.retry_final)


def _retry_check(config: GameConfig, user: User, run: MagicRun) -> tuple[bool, str]:
    state = run.server_state or {}
    if run.status != "in_progress" or state.get("phase") != "final_lost" or state.get("retry_used"):
        return False, "Переиграть можно только проигранный финал"
    if _today(user)[2] >= config.magic_retries_daily_limit:
        return False, "Вторые шансы на сегодня закончились"
    if config.magic_retry_stars <= 0:
        return False, "Второй шанс за звёзды сейчас не продаётся"
    return True, ""


async def retry_stars_order(db: AsyncSession, user: User, run_id: int) -> tuple[str, int, str, str]:
    config = await get_config(db)
    run = await db.get(MagicRun, run_id)
    if run is None or run.user_id != user.id:
        raise NotFoundError("Поход не найден")
    ok, reason = _retry_check(config, user, run)
    if not ok:
        raise ConflictError(reason)
    return (f"magic_retry:{run.id}", config.magic_retry_stars, "Второй шанс в финале",
            "«Мяч и Магия»: переиграть проигранную финальную битву с той же армией.")


async def validate_retry_stars(db: AsyncSession, user_id: int, run_id: str, stars_amount: int) -> tuple[bool, str]:
    config = await get_config(db)
    user = await db.get(User, user_id)
    run = await db.get(MagicRun, int(run_id)) if run_id.isdigit() else None
    if user is None or run is None or run.user_id != user_id:
        return False, "Поход не найден"
    ok, reason = _retry_check(config, user, run)
    if ok and stars_amount != config.magic_retry_stars:
        return False, "Цена изменилась — открой покупку заново"
    return ok, reason


async def deliver_retry_stars(db: AsyncSession, user: User) -> dict:
    """Paid: one second-chance credit (the client spends it right away). The caller commits."""
    locked = await lock_user_for_update(db, user.id)
    locked.magic_retry_credits += 1
    db.add(locked)
    return {"kind": "magic_retry", "credits": locked.magic_retry_credits}


# --- extra runs: the day's first for coins, the rest for Stars ------------------------

async def buy_extra_run(db: AsyncSession, user: User, mode: str = "quick") -> MagicExtraRunOut:
    """One more run of `mode` today for coins (the day's first bought one of that mode)."""
    mode = _run_mode(mode)
    config = await get_config(db)
    locked = await lock_user_for_update(db, user.id)
    _ensure_daily_reset(locked)
    st = _runs_status(config, locked, mode)
    if st["price_coins"] is None:
        raise ConflictError("Следующий поход сегодня — за звёзды" if st["price_stars"] else "Сегодня этот режим больше не купить")
    await debit_coins(db, locked, st["price_coins"], TransactionType.magic_purchase,
                      f"«Мяч и Магия»: ещё поход · {engine.MODES[mode]['label']}")
    row = _run_row(locked, mode)
    row["coins"] += 1
    row["bank"] += 1
    _save_row(locked, mode, row)
    locked.magic_extra_runs_today += 1
    db.add(locked)
    await db.commit()
    await db.refresh(locked)
    return MagicExtraRunOut(bonus_runs=row["bank"], balance=locked.balance, mode=mode)


async def extra_run_stars_order(db: AsyncSession, user: User, mode: str = "quick") -> tuple[str, int, str, str]:
    mode = _run_mode(mode)
    config = await get_config(db)
    st = _runs_status(config, user, mode)
    if st["price_coins"] is not None or st["price_stars"] is None:
        raise ConflictError("Сейчас купить поход за звёзды нельзя")
    label = engine.MODES[mode]["label"]
    return (f"magic_run:{mode}:{local_today().isoformat()}", st["price_stars"], f"Мяч и Магия: ещё поход · {label}",
            f"«Мяч и Магия»: ещё один поход сегодня в режиме «{label}», с наградой за него.")


async def validate_extra_run_stars(db: AsyncSession, user_id: int, arg: str, stars_amount: int) -> tuple[bool, str]:
    mode, day = _parse_run_arg(arg)
    if mode not in engine.MODES:
        return False, "Неизвестный режим"
    config = await get_config(db)
    user = await db.get(User, user_id)
    if user is None:
        return False, "Игрок не найден"
    if day != local_today().isoformat():
        return False, "День сменился — открой покупку заново"
    st = _runs_status(config, user, mode)
    if st["price_coins"] is not None or st["price_stars"] is None:
        return False, "Сейчас купить поход за звёзды нельзя"
    if st["price_stars"] != stars_amount:
        return False, "Цена изменилась — открой покупку заново"
    return True, ""


async def deliver_extra_run_stars(db: AsyncSession, user: User, arg: str = "") -> dict:
    """Paid: banks one run of its mode for today (never refuses — the payment is taken). The caller commits."""
    mode, _ = _parse_run_arg(arg)
    mode = mode if mode in engine.MODES else "quick"
    locked = await lock_user_for_update(db, user.id)
    _ensure_daily_reset(locked)
    row = _run_row(locked, mode)
    row["stars"] += 1
    row["bank"] += 1
    _save_row(locked, mode, row)
    locked.magic_extra_runs_today += 1
    db.add(locked)
    return {"kind": "magic_run", "mode": mode, "bonus_runs": row["bank"]}


# ---------------------------------------------------------------------------
# Creature cards («Магический пак», docs/magic-army.md)
# ---------------------------------------------------------------------------

def _creature_out(unit: str, fighters: int) -> MagicCreatureOut:
    u = engine.UNITS[unit]
    return MagicCreatureOut(unit=unit, faction=u["faction"], name=u["name"], emoji=u["emoji"], tier=u["tier"],
                            fighters=fighters)


def _creatures_out(user: User) -> list[MagicCreatureOut]:
    have = (user.magic_creatures or {}).get("have") or {}
    rows = [_creature_out(code, n) for code, n in have.items() if n > 0 and code in engine.UNITS]
    return sorted(rows, key=lambda c: (c.faction, -c.tier, c.unit))


def _pack_out(config: GameConfig) -> MagicCreaturePackOut:
    return MagicCreaturePackOut(
        size=engine.PACK_SIZE, coins=config.magic_creature_pack_coins or None, stars=config.magic_creature_pack_stars or None,
        odds={t: w / 10 for t, w in engine.PACK_ODDS}, fighters=dict(engine.CARD_FIGHTERS),
    )


def _add_cards(user: User, cards: list[str], *, last: bool = True) -> None:
    data = dict(user.magic_creatures or {})
    have = dict(data.get("have") or {})
    for code in cards:
        have[code] = have.get(code, 0) + engine.CARD_FIGHTERS[engine.UNITS[code]["tier"]]
    data["have"] = have
    if last:
        data["last_pack"] = list(cards)
    user.magic_creatures = data  # a new dict: the JSON column sees the change


async def _ensure_starter(db: AsyncSession, user: User) -> None:
    """The first visit: a starter set of creature cards of each faction. Later visits: the wounded
    whose time is up come back, and an emptied collection gets the free starter set once a day."""
    if user.magic_creatures is not None:
        if _creatures_due(user):
            locked = await lock_user_for_update(db, user.id)
            if _settle_creatures(locked):
                db.add(locked)
                await db.commit()
            await db.refresh(user)
        return
    locked = await lock_user_for_update(db, user.id)
    if locked.magic_creatures is None:
        r = random.Random(f"starter-{locked.id}")
        cards = [c for f in engine.FACTIONS for c in engine.starter_cards(r, f)]
        locked.magic_creatures = {}
        _add_cards(locked, cards, last=False)
        db.add(locked)
        await db.commit()
    await db.refresh(user)


def _day_key() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _fighters(have: dict) -> int:
    return sum(n for n in have.values() if n > 0)


def _creatures_due(user: User) -> bool:
    data = user.magic_creatures or {}
    now = datetime.now(timezone.utc)
    if any(datetime.fromisoformat(w["until"]) <= now for w in data.get("wounded") or []):
        return True
    return _fighters(data.get("have") or {}) == 0 and data.get("refill_day") != _day_key()


def _settle_creatures(user: User) -> bool:
    """On a locked user: the healed wounded rejoin the collection; an empty collection gets the
    free starter set (once a day). True when something changed."""
    data = dict(user.magic_creatures or {})
    have = dict(data.get("have") or {})
    now = datetime.now(timezone.utc)
    changed = False
    keep = []
    for w in data.get("wounded") or []:
        if datetime.fromisoformat(w["until"]) <= now:
            have[w["unit"]] = have.get(w["unit"], 0) + w["count"]
            changed = True
        else:
            keep.append(w)
    data["wounded"] = keep
    if _fighters(have) == 0 and data.get("refill_day") != _day_key():
        r = random.Random(f"refill-{user.id}-{_day_key()}")
        for code in engine.starter_cards(r, r.choice(sorted(engine.FACTIONS))):
            have[code] = have.get(code, 0) + engine.CARD_FIGHTERS[engine.UNITS[code]["tier"]]
        data["refill_day"] = _day_key()
        changed = True
    if changed:
        data["have"] = have
        user.magic_creatures = data
    return changed


def _wounded_out(user: User) -> list[MagicWoundedOut]:
    rows = []
    for w in (user.magic_creatures or {}).get("wounded") or []:
        if w["unit"] in engine.UNITS:
            u = engine.UNITS[w["unit"]]
            rows.append(MagicWoundedOut(unit=w["unit"], name=u["name"], emoji=u["emoji"], tier=u["tier"],
                                        count=w["count"], until=datetime.fromisoformat(w["until"])))
    return sorted(rows, key=lambda w: w.until)


def _heal_cost(config: GameConfig, user: User) -> int:
    value = sum(w["count"] * engine.ESSENCE[engine.UNITS[w["unit"]]["tier"]]
                for w in (user.magic_creatures or {}).get("wounded") or [] if w["unit"] in engine.UNITS)
    return -(-value * config.magic_heal_essence_pct // 100) if value else 0


def _risk_out(config: GameConfig) -> MagicRiskOut:
    hours = max(1, config.magic_wounded_hours)
    return MagicRiskOut(dead_pct=dict(engine.DEAD_PCT), wounded_hours=hours, wounded_hours_win=max(1, hours // 2),
                        essence_per_fighter=dict(engine.ESSENCE))


def _apply_casualties(config: GameConfig, user: User, state: dict, won: bool) -> None:
    """The run is over: the dead leave the collection for essence, the wounded leave until `until`.
    Captains (footballers) are never lost — only creatures."""
    cas = engine.casualties(state)
    hours = max(1, config.magic_wounded_hours)
    if won:
        hours = max(1, hours // 2)  # a won run: the wounded heal twice as fast
    until = datetime.now(timezone.utc) + timedelta(hours=hours)
    data = dict(user.magic_creatures or {})
    have = dict(data.get("have") or {})
    wounded = list(data.get("wounded") or [])
    for unit, n in {**cas["dead"]}.items():
        have[unit] = max(0, have.get(unit, 0) - n)
    for unit, n in cas["wounded"].items():
        take = min(n, have.get(unit, 0))
        if take:
            have[unit] -= take
            wounded.append({"unit": unit, "count": take, "until": until.isoformat()})
    essence = 0 if user.game_rewards_blocked else cas["essence"]
    data["essence"] = int(data.get("essence") or 0) + essence
    data["have"] = {k: v for k, v in have.items() if v > 0}
    data["wounded"] = wounded
    # The guard loses its share of the fallen; captains and the guard earn XP.
    marched = state.get("marched") or {}
    xp = engine.run_xp(state, config.magic_progress_xp_pct)
    caps = dict(data.get("captains") or {})
    for pid in marched.get("captains") or []:
        row = dict(caps.get(str(pid)) or {})
        row["xp"] = int(row.get("xp") or 0) + xp
        caps[str(pid)] = row
    data["captains"] = caps
    guard = dict(data.get("guard") or {})
    if marched.get("guard") and guard.get("player_id") == marched["guard"]:
        guard["count"] = max(0, int(guard.get("count") or 0) - cas.get("guard_lost", 0))
        guard["xp"] = int(guard.get("xp") or 0) + xp
        data["guard"] = guard
    # The one free revival: offered after a run with dead, until it's used.
    if cas["dead"] and not data.get("revive_used"):
        data["revive_offer"] = {"dead": cas["dead"], "essence": essence}
    user.magic_creatures = data
    state["casualties"] = {**cas, "essence": essence, "until": until.isoformat() if cas["wounded"] else None,
                           "won_faster": won and bool(cas["wounded"]), "captains_xp": xp}


def _casualties_out(cas: Optional[dict]) -> Optional[MagicCasualtiesOut]:
    if not cas:
        return None

    def rows(d: dict) -> list[MagicCasualtyOut]:
        return [MagicCasualtyOut(unit=k, name=engine.UNITS[k]["name"], emoji=engine.UNITS[k]["emoji"],
                                 tier=engine.UNITS[k]["tier"], count=v) for k, v in d.items() if k in engine.UNITS]
    return MagicCasualtiesOut(guard_lost=cas.get("guard_lost", 0), captains_xp=cas.get("captains_xp", 0),
                              dead=rows(cas["dead"]), wounded=rows(cas["wounded"]), essence=cas["essence"],
                              until=datetime.fromisoformat(cas["until"]) if cas.get("until") else None,
                              won_faster=bool(cas.get("won_faster")))


def _heal_all(user: User) -> int:
    data = dict(user.magic_creatures or {})
    have = dict(data.get("have") or {})
    healed = 0
    for w in data.get("wounded") or []:
        have[w["unit"]] = have.get(w["unit"], 0) + w["count"]
        healed += w["count"]
    data["have"] = have
    data["wounded"] = []
    user.magic_creatures = data
    return healed


async def heal_for_essence(db: AsyncSession, user: User) -> MagicHealOut:
    config = await get_config(db)
    _require_enabled(config)
    await _ensure_starter(db, user)
    locked = await lock_user_for_update(db, user.id)
    if not (locked.magic_creatures or {}).get("wounded"):
        raise ConflictError("Раненых нет")
    cost = _heal_cost(config, locked)
    have = int((locked.magic_creatures or {}).get("essence") or 0)
    if have < cost:
        raise ConflictError("Не хватает эссенции", details={"need": cost, "have": have})
    healed = _heal_all(locked)
    data = dict(locked.magic_creatures)
    data["essence"] = have - cost
    locked.magic_creatures = data
    db.add(locked)
    await db.commit()
    await db.refresh(locked)
    return MagicHealOut(healed=healed, essence=data["essence"], creatures=_creatures_out(locked))


async def heal_stars_order(db: AsyncSession, user: User) -> tuple[str, int, str, str]:
    config = await get_config(db)
    _require_enabled(config)
    if not config.magic_heal_stars:
        raise ConflictError("Лечение за звёзды сейчас недоступно")
    if not (user.magic_creatures or {}).get("wounded"):
        raise ConflictError("Раненых нет")
    return ("magic_heal:1", config.magic_heal_stars, "Лечение раненых",
            "«Мяч и Магия»: все раненые существа сразу возвращаются в коллекцию.")


async def validate_heal_stars(db: AsyncSession, user_id: int, stars_amount: int) -> tuple[bool, str]:
    config = await get_config(db)
    if not config.magic_heal_stars:
        return False, "Лечение за звёзды сейчас недоступно"
    if stars_amount != config.magic_heal_stars:
        return False, "Цена изменилась — открой покупку заново"
    user = await db.get(User, user_id)
    if user is None or not (user.magic_creatures or {}).get("wounded"):
        return False, "Раненых уже нет"
    return True, ""


async def deliver_heal_stars(db: AsyncSession, user: User) -> dict:
    """Paid: heals every wounded (never refuses — the payment is taken). The caller commits."""
    locked = await lock_user_for_update(db, user.id)
    healed = _heal_all(locked) if locked.magic_creatures is not None else 0
    db.add(locked)
    return {"kind": "magic_heal", "healed": healed}


# ---------------------------------------------------------------------------
# Captains (levels, traits, duplicates → XP) and the guard
# ---------------------------------------------------------------------------

RARITY_RANK = {"common": 1, "rare": 2, "epic": 3, "legendary": 4, "diamond": 5}


def _cap_row(user: Optional[User], pid: int) -> dict:
    return dict(((user.magic_creatures or {}).get("captains") or {}).get(str(pid)) or {}) if user else {}


def _cap_level(user: Optional[User], pid: int) -> int:
    return engine.level_of(int(_cap_row(user, pid).get("xp") or 0), engine.CAPTAIN_XP)


def _next(xp: int, table: tuple) -> Optional[int]:
    level = engine.level_of(xp, table)
    return table[level] if level < len(table) else None


def _fed_left(config: GameConfig, row: dict) -> int:
    fed = int(row.get("fed") or 0) if row.get("fed_day") == _day_key() else 0
    return max(0, config.magic_captain_dup_daily - fed)


def _captain_out(user: User, p: Player, copies: int, config: GameConfig) -> MagicCaptainOut:
    row = _cap_row(user, p.id)
    xp = int(row.get("xp") or 0)
    level = engine.level_of(xp, engine.CAPTAIN_XP)
    return MagicCaptainOut(card=_card_out(p), cap=_captain_cap(p), copies=copies, level=level, xp=xp,
                           next_xp=_next(xp, engine.CAPTAIN_XP), traits=list(row.get("traits") or []),
                           trait_slots=engine.trait_slots(level, engine.CAPTAIN_TRAIT_LEVELS),
                           dup_xp=config.magic_captain_dup_xp, fed_left=_fed_left(config, row))


def _traits_out() -> list[MagicTraitOut]:
    return [MagicTraitOut(code=c, emoji=t[0], name=t[1], text=t[2]) for c, t in engine.TRAITS.items()]


def _plain_copy(card: UserCard) -> bool:
    """A copy that may be burnt here: free, nothing invested into it."""
    return (card.can_burn() and not card.has_path_progress() and not card.skill_code and not card.stars
            and not card.star_progress and not card.diamond_rating_bonus and not card.artifact_rating_bonus
            and not card.equipment_rating_bonus)


async def _spares(db: AsyncSession, user_id: int, player_ids: Optional[set] = None) -> dict[int, list[UserCard]]:
    """Burnable copies per footballer — every copy but one (the best kept) stays out of it."""
    q = select(UserCard).where(UserCard.owner_id == user_id).order_by(UserCard.serial_number.desc())
    if player_ids is not None:
        q = q.where(UserCard.player_id.in_(player_ids))
    cards = list((await db.execute(q)).scalars())
    in_squad = await collection_service.personal_squad_card_ids(db, [c.id for c in cards])
    by: dict[int, list[UserCard]] = {}
    for c in cards:
        by.setdefault(c.player_id, []).append(c)
    out: dict[int, list[UserCard]] = {}
    for pid, copies in by.items():
        if len(copies) < 2:
            continue
        free = [c for c in copies if c.id not in in_squad and _plain_copy(c)]
        # Keep one copy at least: when every copy is free, the lowest serial stays.
        keep = len(copies) - len(free)
        out[pid] = free if keep >= 1 else free[:-1]
    return {pid: v for pid, v in out.items() if v}


async def _burn(db: AsyncSession, user_id: int, player_id: int, count: int) -> int:
    spares = (await _spares(db, user_id, {player_id})).get(player_id, [])
    if count < 1 or len(spares) < count:
        raise ConflictError("Столько лишних копий нет — одна копия всегда остаётся у тебя",
                            details={"spare": len(spares)})
    ids = [c.id for c in spares[:count]]
    locked = (await db.execute(select(UserCard).where(UserCard.id.in_(ids)).with_for_update()
                               .execution_options(populate_existing=True))).scalars().all()
    if len(locked) != count or not all(_plain_copy(c) and c.owner_id == user_id for c in locked):
        raise ConflictError("Карточки изменились — обнови экран и попробуй снова")
    for c in locked:
        await db.delete(c)
    return count


async def feed_captain(db: AsyncSession, user: User, player_id: int, count: int):
    """Spare copies of the captain's own footballer → captain XP."""
    config = await get_config(db)
    _require_enabled(config)
    await _ensure_starter(db, user)
    locked = await lock_user_for_update(db, user.id)
    row = _cap_row(locked, player_id)
    xp = int(row.get("xp") or 0)
    if engine.level_of(xp, engine.CAPTAIN_XP) >= len(engine.CAPTAIN_XP):
        raise ConflictError("Капитан уже на высшем уровне")
    left = _fed_left(config, row)
    if count > left:
        raise ConflictError("На сегодня капитан уже наелся дублей — приходи завтра" if not left
                            else f"Сегодня капитану можно скормить ещё {left}", details={"fed_left": left})
    await _burn(db, locked.id, player_id, count)
    row["xp"] = min(engine.CAPTAIN_XP[-1], xp + count * max(0, config.magic_captain_dup_xp))
    row["fed"] = (int(row.get("fed") or 0) if row.get("fed_day") == _day_key() else 0) + count
    row["fed_day"] = _day_key()
    data = dict(locked.magic_creatures or {})
    caps = dict(data.get("captains") or {})
    caps[str(player_id)] = row
    data["captains"] = caps
    locked.magic_creatures = data
    db.add(locked)
    await db.commit()
    await db.refresh(locked)
    return await get_army(db, locked)


async def set_captain_trait(db: AsyncSession, user: User, player_id: int, code: str):
    if code not in engine.TRAITS:
        raise NotFoundError("Такой черты нет")
    locked = await lock_user_for_update(db, user.id)
    row = _cap_row(locked, player_id)
    level = engine.level_of(int(row.get("xp") or 0), engine.CAPTAIN_XP)
    traits = list(row.get("traits") or [])
    if code in traits:
        raise ConflictError("Эта черта уже есть")
    if len(traits) >= engine.trait_slots(level, engine.CAPTAIN_TRAIT_LEVELS):
        raise ConflictError(f"Новая черта — на уровнях {', '.join(map(str, engine.CAPTAIN_TRAIT_LEVELS))}")
    row["traits"] = traits + [code]
    data = dict(locked.magic_creatures or {})
    caps = dict(data.get("captains") or {})
    caps[str(player_id)] = row
    data["captains"] = caps
    locked.magic_creatures = data
    db.add(locked)
    await db.commit()
    await db.refresh(locked)
    return await get_army(db, locked)


def _guard_row(user: User) -> dict:
    return dict((user.magic_creatures or {}).get("guard") or {})


def _points(guard: Player, p: Player) -> int:
    if p.id == guard.id:
        return engine.GUARD_POINTS["same"]
    a, b = RARITY_RANK.get(_val(p.rarity), 1), RARITY_RANK.get(_val(guard.rarity), 1)
    return engine.GUARD_POINTS["higher" if a > b else "same_rarity" if a == b else "lower"]


def _guard_unit(p: Optional[Player]) -> str:
    return engine.guard_unit(_val(p.rarity)) if p is not None else engine.GUARD


async def _guard_out(db: AsyncSession, user: User, owned: Optional[list]) -> MagicGuardOut:
    row = _guard_row(user)
    xp = int(row.get("xp") or 0)
    level = engine.level_of(xp, engine.GUARD_XP)
    pid = row.get("player_id")
    guard = await db.get(Player, pid) if pid else None
    unit = _guard_unit(guard)
    u = engine.UNITS[unit]
    out = MagicGuardOut(level=level, xp=xp, next_xp=_next(xp, engine.GUARD_XP), count=int(row.get("count") or 0),
                        size=engine.guard_size(level, unit), points=int(row.get("points") or 0),
                        fighter_points=engine.guard_fighter_points(unit), unit=unit, tier=u["tier"],
                        ability=u["ability_text"] or None, traits=list(row.get("traits") or []),
                        trait_slots=engine.trait_slots(level, engine.GUARD_TRAIT_LEVELS))
    if guard is None:
        return out
    out.card = _card_out(guard)
    if owned is not None:
        spares = await _spares(db, user.id)
        players = {p.id: p for p, _ in owned}
        mats = [MagicGuardMaterialOut(card=_card_out(players[k]), spare=len(v), points=_points(guard, players[k]))
                for k, v in spares.items() if k in players]
        out.materials = sorted(mats, key=lambda m: (-m.points, -m.spare, m.card.player_id))[:40]
    return out


async def _guard_for_run(db: AsyncSession, user: User) -> Optional[dict]:
    row = _guard_row(user)
    pid, count = row.get("player_id"), int(row.get("count") or 0)
    if not pid or count <= 0:
        return None
    owns = (await db.execute(select(func.count(UserCard.id)).where(
        UserCard.owner_id == user.id, UserCard.player_id == pid))).scalar_one()
    p = await db.get(Player, pid)
    if not owns or p is None:
        return None
    level = engine.level_of(int(row.get("xp") or 0), engine.GUARD_XP)
    unit = _guard_unit(p)
    return {"count": min(count, engine.guard_size(level, unit)), "level": level, "unit": unit,
            "traits": list(row.get("traits") or []),
            "card": _card_out(p).model_dump(), "rating": p.rating, "position": _val(p.position)}


async def _save_guard(db: AsyncSession, locked: User, row: dict):
    data = dict(locked.magic_creatures or {})
    data["guard"] = row
    locked.magic_creatures = data
    db.add(locked)
    await db.commit()
    await db.refresh(locked)
    return await get_army(db, locked)


async def set_guard(db: AsyncSession, user: User, player_id: int):
    """The guard's footballer. Changing it burns half the guard's XP; the fighters stay."""
    config = await get_config(db)
    _require_enabled(config)
    await _ensure_starter(db, user)
    owns = (await db.execute(select(func.count(UserCard.id)).where(
        UserCard.owner_id == user.id, UserCard.player_id == player_id))).scalar_one()
    if not owns:
        raise ForbiddenError("Гвардию ведёт только твой футболист")
    locked = await lock_user_for_update(db, user.id)
    row = _guard_row(locked)
    if row.get("player_id") == player_id:
        return await get_army(db, locked)
    if row.get("player_id"):
        row["xp"] = int(row.get("xp") or 0) // 2
        # The fighters keep their weight: a guard of another rarity has more (or fewer) of them.
        old, new = _guard_unit(await db.get(Player, row["player_id"])), _guard_unit(await db.get(Player, player_id))
        total = int(row.get("count") or 0) * engine.guard_fighter_points(old) + int(row.get("points") or 0)
        level = engine.level_of(int(row["xp"]), engine.GUARD_XP)
        per = engine.guard_fighter_points(new)
        row["count"] = min(engine.guard_size(level, new), total // per)
        row["points"] = total % per if row["count"] < engine.guard_size(level, new) else 0
    row["player_id"] = player_id
    return await _save_guard(db, locked, row)


async def refill_guard(db: AsyncSession, user: User, player_id: int, count: int):
    """Spare footballer copies → guard fighters: the same footballer 1 → 1, a rarer one 3 → 2,
    the same rarity 2 → 1, a lower one 3 → 1."""
    config = await get_config(db)
    _require_enabled(config)
    locked = await lock_user_for_update(db, user.id)
    row = _guard_row(locked)
    if not row.get("player_id"):
        raise ConflictError("Сначала выбери футболиста гвардии")
    guard, p = await db.get(Player, row["player_id"]), await db.get(Player, player_id)
    if guard is None or p is None:
        raise NotFoundError("Футболист не найден")
    level = engine.level_of(int(row.get("xp") or 0), engine.GUARD_XP)
    unit = _guard_unit(guard)
    size, have, per = engine.guard_size(level, unit), int(row.get("count") or 0), engine.guard_fighter_points(unit)
    if have >= size:
        raise ConflictError("Гвардия в полном составе")
    await _burn(db, locked.id, player_id, count)
    total = int(row.get("points") or 0) + count * _points(guard, p)
    gained = total // per
    row["count"] = min(size, have + gained)
    row["points"] = total % per if have + gained < size else 0
    return await _save_guard(db, locked, row)


async def set_guard_trait(db: AsyncSession, user: User, code: str):
    if code not in engine.TRAITS:
        raise NotFoundError("Такой черты нет")
    locked = await lock_user_for_update(db, user.id)
    row = _guard_row(locked)
    level = engine.level_of(int(row.get("xp") or 0), engine.GUARD_XP)
    traits = list(row.get("traits") or [])
    if code in traits:
        raise ConflictError("Эта черта уже есть")
    if len(traits) >= engine.trait_slots(level, engine.GUARD_TRAIT_LEVELS):
        raise ConflictError(f"Новая черта гвардии — на уровнях {', '.join(map(str, engine.GUARD_TRAIT_LEVELS))}")
    row["traits"] = traits + [code]
    return await _save_guard(db, locked, row)


# ---------------------------------------------------------------------------
# The one free revival
# ---------------------------------------------------------------------------

def _revive_out(user: User) -> Optional[MagicReviveOut]:
    data = user.magic_creatures or {}
    offer = data.get("revive_offer")
    if data.get("revive_used") or not offer:
        return None
    return MagicReviveOut(dead=[MagicCasualtyOut(unit=k, name=engine.UNITS[k]["name"], emoji=engine.UNITS[k]["emoji"],
                                                 tier=engine.UNITS[k]["tier"], count=v)
                                for k, v in (offer.get("dead") or {}).items() if k in engine.UNITS],
                          essence=int(offer.get("essence") or 0))


async def revive_free(db: AsyncSession, user: User) -> MagicHealOut:
    """Once per player: the creatures that died for good in the last run come back (their essence goes)."""
    config = await get_config(db)
    _require_enabled(config)
    locked = await lock_user_for_update(db, user.id)
    data = dict(locked.magic_creatures or {})
    offer = data.get("revive_offer")
    if data.get("revive_used") or not offer:
        raise ConflictError("Бесплатное воскрешение уже использовано")
    have = dict(data.get("have") or {})
    back = 0
    for unit, n in (offer.get("dead") or {}).items():
        have[unit] = have.get(unit, 0) + n
        back += n
    data["have"] = have
    data["essence"] = max(0, int(data.get("essence") or 0) - int(offer.get("essence") or 0))
    data["revive_used"] = True
    data.pop("revive_offer", None)
    locked.magic_creatures = data
    db.add(locked)
    await db.commit()
    await db.refresh(locked)
    return MagicHealOut(healed=back, essence=data["essence"], creatures=_creatures_out(locked))


# ---------------------------------------------------------------------------
# The essence shop
# ---------------------------------------------------------------------------

BONUS_TITLE = {"leadership": "+1 лидерство навсегда", "mana": "+1 мана навсегда"}
BONUS_TEXT = {"leadership": "Герой ведёт отряды дороже — в каждом походе, любым классом.",
              "mana": "Больше заклинаний за бой — в каждом походе, любым классом."}


def _bonus(user: User, key: str) -> int:
    return int(((user.magic_creatures or {}).get("bonus") or {}).get(key) or 0)


def _essence(user: User) -> int:
    return int((user.magic_creatures or {}).get("essence") or 0)


def _bonus_price(config: GameConfig, key: str, owned: int) -> tuple[int, int]:
    base = config.magic_essence_leadership if key == "leadership" else config.magic_essence_mana
    cap = config.magic_essence_leadership_max if key == "leadership" else config.magic_essence_mana_max
    return base * (owned + 1), cap


def _skin_price(config: GameConfig, cosmetic: Cosmetic) -> int:
    if cosmetic.stars_price > 0 and config.magic_essence_per_star:
        return cosmetic.stars_price * config.magic_essence_per_star
    if cosmetic.coins_price > 0 and config.magic_essence_per_100_coins:
        return -(-cosmetic.coins_price * config.magic_essence_per_100_coins // 100)
    return 0


async def _skins_for_essence(db: AsyncSession) -> list[Cosmetic]:
    rows = await db.execute(select(Cosmetic).where(
        Cosmetic.kind.in_(("magic_hero", "magic_castle")), Cosmetic.is_active.is_(True),
        Cosmetic.is_exclusive.is_(False)).order_by(Cosmetic.kind, Cosmetic.sort_order, Cosmetic.id))
    return list(rows.scalars())


async def get_shop(db: AsyncSession, user: User) -> MagicShopOut:
    config = await get_config(db)
    _require_enabled(config)
    await _ensure_starter(db, user)
    items: list[MagicShopItemOut] = []
    if config.magic_essence_pack:
        items.append(MagicShopItemOut(code="pack", kind="pack", title="Магический пак",
                                      text=f"{engine.PACK_SIZE} карт существ всех рас.", price=config.magic_essence_pack))
    for key in ("leadership", "mana"):
        owned = _bonus(user, key)
        price, cap = _bonus_price(config, key, owned)
        if price and cap:
            items.append(MagicShopItemOut(code=key, kind=key, title=BONUS_TITLE[key], text=BONUS_TEXT[key], price=price,
                                          owned=owned, max=cap, available=owned < cap))
    owned_skins = await cosmetic_service.owned_ids(db, user.id)
    for c in await _skins_for_essence(db):
        price = _skin_price(config, c)
        if price:
            items.append(MagicShopItemOut(code=f"skin:{c.id}", kind="skin", title=c.name, text=c.description or "",
                                          price=price, available=c.id not in owned_skins, skin_kind=c.kind,
                                          style_key=c.style_key))
    return MagicShopOut(essence=_essence(user), items=items)


async def buy_in_shop(db: AsyncSession, user: User, code: str) -> MagicShopBuyOut:
    config = await get_config(db)
    _require_enabled(config)
    await _ensure_starter(db, user)
    locked = await lock_user_for_update(db, user.id)
    have = _essence(locked)
    cards: list[str] = []
    if code == "pack":
        price = config.magic_essence_pack
        if not price:
            raise ConflictError("Пак за эссенцию сейчас не продаётся")
    elif code in ("leadership", "mana"):
        owned = _bonus(locked, code)
        price, cap = _bonus_price(config, code, owned)
        if not price or owned >= cap:
            raise ConflictError("Больше купить нельзя — это максимум")
    elif code.startswith("skin:") and code[5:].isdigit():
        cosmetic = await db.get(Cosmetic, int(code[5:]))
        if (cosmetic is None or cosmetic.kind not in ("magic_hero", "magic_castle") or not cosmetic.is_active
                or cosmetic.is_exclusive):
            raise NotFoundError("Облик не найден")
        price = _skin_price(config, cosmetic)
        if not price:
            raise ConflictError("Этот облик за эссенцию не продаётся")
        if cosmetic.id in await cosmetic_service.owned_ids(db, locked.id):
            raise ConflictError("Этот облик уже твой")
    else:
        raise NotFoundError("Такого товара нет")
    if have < price:
        raise ConflictError("Не хватает эссенции", details={"need": price, "have": have})
    data = dict(locked.magic_creatures or {})
    data["essence"] = have - price
    locked.magic_creatures = data
    if code == "pack":
        cards = _open_pack(locked)
    elif code in ("leadership", "mana"):
        data = dict(locked.magic_creatures)
        bonus = dict(data.get("bonus") or {})
        bonus[code] = int(bonus.get(code) or 0) + 1
        data["bonus"] = bonus
        locked.magic_creatures = data
    else:
        await cosmetic_service.grant(db, locked.id, int(code[5:]), "magic_essence")
    db.add(locked)
    await db.commit()
    await db.refresh(locked)
    return MagicShopBuyOut(essence=_essence(locked), item=code,
                           cards=[_creature_out(c, engine.CARD_FIGHTERS[engine.UNITS[c]["tier"]]) for c in cards])


def _open_pack(user: User) -> list[str]:
    cards = engine.open_pack(random.Random(secrets.token_hex(8)))
    _add_cards(user, cards)
    return cards


async def buy_creature_pack(db: AsyncSession, user: User) -> MagicPackOpenOut:
    config = await get_config(db)
    _require_enabled(config)
    if not config.magic_creature_pack_coins:
        raise ConflictError("Магический пак сейчас продаётся только за звёзды")
    await _ensure_starter(db, user)
    locked = await lock_user_for_update(db, user.id)
    await debit_coins(db, locked, config.magic_creature_pack_coins, TransactionType.magic_purchase,
                      "«Мяч и Магия»: магический пак")
    cards = _open_pack(locked)
    db.add(locked)
    await db.commit()
    await db.refresh(locked)
    return MagicPackOpenOut(cards=[_creature_out(c, engine.CARD_FIGHTERS[engine.UNITS[c]["tier"]]) for c in cards],
                            creatures=_creatures_out(locked), balance=locked.balance)


async def creature_pack_stars_order(db: AsyncSession, user: User) -> tuple[str, int, str, str]:
    config = await get_config(db)
    _require_enabled(config)
    if not config.magic_creature_pack_stars:
        raise ConflictError("Сейчас купить пак за звёзды нельзя")
    return ("magic_pack:1", config.magic_creature_pack_stars, "Магический пак",
            f"«Мяч и Магия»: {engine.PACK_SIZE} карт существ всех рас для твоей армии.")


async def validate_creature_pack_stars(db: AsyncSession, stars_amount: int) -> tuple[bool, str]:
    config = await get_config(db)
    if not config.magic_creature_pack_stars:
        return False, "Сейчас купить пак за звёзды нельзя"
    if stars_amount != config.magic_creature_pack_stars:
        return False, "Цена изменилась — открой покупку заново"
    return True, ""


async def deliver_creature_pack_stars(db: AsyncSession, user: User) -> dict:
    """Paid: opens the pack (never refuses — the payment is taken). The caller commits."""
    locked = await lock_user_for_update(db, user.id)
    if locked.magic_creatures is None:
        locked.magic_creatures = {}
    cards = _open_pack(locked)
    db.add(locked)
    return {"kind": "magic_pack", "cards": cards}


def _player_turn(state: dict) -> None:
    b = state.get("battle")
    if not b or state["phase"] != "battle" or b["auto"] or not b["turn_of"] or engine.bunit(state, b["turn_of"])["side"] != "me":
        raise engine.EngineError("Сейчас не твой ход")


async def battle_act(db: AsyncSession, user: User, run_id: int, version: int, unit: str, action: str,
                     target: Optional[str], x: Optional[int], y: Optional[int]) -> MagicRunOut:
    def apply(state: dict) -> None:
        _player_turn(state)
        if state["battle"]["turn_of"] != unit:
            raise engine.EngineError("Сейчас ходит другой отряд")
        engine.stack_act(state, unit, action, target, x, y)
        engine.run_until_input(state)

    return await _mutate(db, user, run_id, version,
                         {"a": "act", "unit": unit, "action": action, "target": target, "x": x, "y": y}, apply)


async def battle_cast(db: AsyncSession, user: User, run_id: int, version: int, spell: str,
                      target: Optional[str]) -> MagicRunOut:
    def apply(state: dict) -> None:
        _player_turn(state)
        engine.cast(state, "me", spell, target)
        engine.run_until_input(state)

    return await _mutate(db, user, run_id, version, {"a": "cast", "spell": spell, "target": target}, apply)


async def battle_auto(db: AsyncSession, user: User, run_id: int, version: int) -> MagicRunOut:
    def apply(state: dict) -> None:
        if state["phase"] != "battle":
            raise engine.EngineError("Боя нет")
        engine.set_auto(state)

    return await _mutate(db, user, run_id, version, {"a": "auto"}, apply)


async def battle_leave(db: AsyncSession, user: User, run_id: int, version: int) -> MagicRunOut:
    return await _mutate(db, user, run_id, version, {"a": "leave"}, engine.leave_battle)


async def forfeit(db: AsyncSession, user: User, run_id: int) -> MagicRunOut:
    run = await _lock_run(db, run_id, user)
    if run.status != "in_progress":
        raise ConflictError("Поход окончен")
    state = copy.deepcopy(run.server_state)
    engine.forfeit(state)
    run.version += 1
    await _finish(db, run, state)
    run.server_state = state
    flag_modified(run, "server_state")
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return await _hydrate(db, run, [])


async def get_run(db: AsyncSession, user: User, run_id: int) -> MagicRunOut:
    run = await db.get(MagicRun, run_id)
    if run is None or run.user_id != user.id:
        raise NotFoundError("Поход не найден")
    return await _hydrate(db, run, [])


async def _finish(db: AsyncSession, run: MagicRun, state: dict) -> None:
    from app.services.pack_service import grant_bonus_pack_opening

    config = await get_config(db)
    user = await lock_user_for_update(db, run.user_id)
    won = state["winner"] == "me"
    forfeited = bool(state.get("forfeit"))
    run.status = "finished"
    run.result = "win" if won else "loss"
    run.score = state["score"]
    run.resolved_at = datetime.now(timezone.utc)
    level_before = engine.hero_level(user.magic_hero_xp)
    if not forfeited:
        run.xp_gained = state["score"] * MODE_XP_PCT.get(state.get("mode", "quick"), 100) // 100
        user.magic_hero_xp += run.xp_gained
    state["level_up"] = engine.hero_level(user.magic_hero_xp) > level_before
    if won:
        user.magic_wins += 1
    delta = config.magic_rating_win * RATING_PCT[run.difficulty] // 100 if won else -config.magic_rating_loss
    if forfeited or not anti_bot_service.take_ranked_slot(user, config, "magic"):
        delta = min(0, delta) if forfeited else 0
    user.magic_rating = max(0, user.magic_rating + delta)
    run.rating_delta = delta
    reward = 0
    # Every run was paid for at the start (a free run of the day or a bought one).
    rewarded = bool(state.get("rewarded", True)) and not forfeited and not user.game_rewards_blocked
    if rewarded:
        base = config.magic_reward_win if won else config.magic_reward_loss
        reward = base * _reward_pct(config, run.difficulty) // 100 * MODE_REWARD_PCT.get(state.get("mode", "quick"), 100) // 100
        state["gold_coins"] = (state["hero"].get("gold", 0) * config.magic_gold_coins_pct // 100
                               * MODE_GOLD_PCT.get(state.get("mode", "quick"), 100) // 100)
        reward += state["gold_coins"]
        if reward > 0:
            await credit_coins(db, user, reward, TransactionType.magic_reward,
                               f"«Мяч и Магия»: {'победа' if won else 'поход'}", RELATED, run.id)
    run.reward_coins = reward
    _apply_casualties(config, user, state, won)
    chance = min(100, _pack_chance(config, run.difficulty) * MODE_PACK_PCT.get(state.get("mode", "quick"), 100) // 100)
    if rewarded and won and chance > 0 and random.Random(f"magic-pack:{run.id}").randint(1, 100) <= chance:
        opened = await grant_bonus_pack_opening(db, user, config.magic_pack_id, idempotency_prefix=f"magic-{run.id}",
                                                source=CardSource.game_reward)
        if opened is not None:
            run.pack_opening_id = opened.opening_id
            state["reward_pack"] = {
                "name": opened.pack.name,
                "cards": [{"name": c.card.player.display_name, "rarity": _val(c.card.player.rarity),
                           "image_path": c.card.player.image_path} for c in opened.cards],
            }
    db.add(user)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _stack_out(s: dict) -> MagicStackOut:
    u = engine.UNITS[s["unit"]]
    card = s.get("card")
    return MagicStackOut(
        id=s["id"], unit=s["unit"], unit_name=u["name"], emoji=u["emoji"], name=s["name"],
        card=MagicCardOut(**card) if card else None, tier=s["tier"], count=s["count"],
        max_count=s.get("start_count", s["max_count"]), hp=s["hp"], top_hp=s.get("top_hp", s["hp"]) if s["count"] else 0,
        atk=s["atk"], defence=s["def"], dmin=s["dmin"], dmax=s["dmax"], spd=s["spd"], ranged=s["ranged"],
        flying=s["flying"], ability_text=u["ability_text"],
        trait=engine.POSITION_TRAIT.get(s.get("group") or "") if card else None,
        side=s.get("side", "me"), x=s.get("x"), y=s.get("y"),
        effects=[MagicEffectOut(code=e["code"], label=EFFECT_LABELS.get(e["code"], e["code"]), turns=e["turns"])
                 for e in s.get("effects", [])],
        defending=bool(s.get("defending")),
    )


def _object_out(state: dict, o: dict) -> MagicMapObjectOut:
    kind = o["kind"]
    guards: list[str] = []
    hint = OBJECT_HINT.get(kind, "")
    emoji = OBJECT_EMOJI.get(kind, "❔")
    label = engine.object_label(o)
    variant = None
    danger = None
    offers: list[MagicOfferOut] = []
    if kind == "artifact":
        name, emoji, text = engine.ARTIFACTS[o["artifact"]]
        hint = text
        variant = o["artifact"]
    elif kind == "chest":
        hint = f"{o.get('gold', 0)} золота или {o.get('gold', 0) // 10 + engine.SCORE['chest']} опыта — на выбор"
    elif kind == "market":
        offers = [MagicOfferOut(unit=f["unit"], unit_name=engine.UNITS[f["unit"]]["name"],
                                tier=engine.UNITS[f["unit"]]["tier"], count=f["count"], price=engine.market_price(state, f),
                                bought=f["bought"]) for f in o.get("offers", [])]
    elif kind == "camp":
        unit = engine.UNITS[o["unit"]]
        emoji = unit["emoji"]
        variant = o["unit"]
        style_name = {"archers": "стрелков", "flyers": "летунов", "wall": "громил",
                      "dawn": "Рассвета", "ash": "Пепла"}.get(o.get("style", "mixed"))
        label = CAMP_LABEL[o["level"]] + (f" {style_name}" if style_name else "")
        foes = engine.camp_foes(state, o, "g")
        guards = [f"{engine.UNITS[f['unit']]['emoji']} {engine.UNITS[f['unit']]['name']} ×{f['count']}" for f in foes]
        hint = f"Боевой дух +{engine.CAMP_MORALE[o['level']]}% урона, +{engine.SCORE['camp'][o['level']]} очков"
        style_hint = engine.CAMP_STYLE_HINT.get(o.get("style", "mixed"))
        if style_hint:
            hint = f"{style_hint}. {hint}"
        ratio = engine.army_power(foes) / max(1, engine.army_power(state["army"]))
        danger = "easy" if ratio < 0.6 else "even" if ratio < 0.95 else "hard"
    elif kind == "medic" and o.get("ready_day", 1) > state["day"]:
        hint = f"Врачи отдыхают до {o['ready_day']}-го дня"
    elif kind == "reinforce":
        hint = f"{engine.UNITS[engine.FACTIONS[state['faction']]['units'][o['tier'] - 1]]['name']} в армию"
    elif kind == "castle":
        emoji = "🏰" if o.get("owner") == "me" else "🏯"
        solo = state["bot"].get("solo")
        label = "Твой замок" if o.get("owner") == "me" else "Логово Безликого" if solo else "Замок соперника"
        hint = "" if o.get("owner") == "me" else (
            "Финальный босс — Безликий: гипнотизирует твои отряды. Можно прийти раньше срока" if solo else OBJECT_HINT["castle"])
        if solo and o.get("owner") != "me":
            emoji = "🎭"
    return MagicMapObjectOut(id=o["id"], kind=kind, x=o["x"], y=o["y"], label=label, taken_by=o.get("taken_by"),
                             owner=o.get("owner"), level=o.get("level"), emoji=emoji, hint=hint, guards=guards,
                             variant=variant, offers=offers, danger=danger, style=o.get("style"))


def _battle_out(state: dict) -> Optional[MagicBattleOut]:
    b = state.get("battle")
    if not b:
        return None
    turn_of = b.get("turn_of")
    me_turn = (state["phase"] == "battle" and not b["auto"] and bool(turn_of) and not b.get("winner")
               and engine.bunit(state, turn_of)["side"] == "me")
    move_cells: list[list[int]] = []
    attack: list[MagicTargetOut] = []
    shoot: list[str] = []
    if me_turn:
        u = engine.bunit(state, turn_of)
        move_cells = [list(c) for c in engine.move_cells(state, u)]
        for e in engine._alive(state, "foe"):
            if engine.can_shoot(state, u):
                shoot.append(e["id"])
            cells = engine.attack_cells(state, u, e)
            if cells:
                attack.append(MagicTargetOut(target=e["id"], cells=[list(c) for c in cells]))
    result = b.get("result") or {}
    return MagicBattleOut(
        kind=b["kind"], foe_name=b["foe_name"], round=b["round"], max_rounds=engine.MAX_ROUNDS, turn_of=turn_of,
        can_act=me_turn, auto=b["auto"], can_cast=me_turn and b["my_cast_round"] < b["round"],
        units=[_stack_out(u) for u in b["units"]], move_cells=move_cells, attack_targets=attack, shoot_targets=shoot,
        foe_mana=(b.get("foe_hero") or {}).get("mana"), winner=b.get("winner"),
        won=result.get("won"), losses=result.get("losses", 0), rocks=b.get("rocks", []), pitch=b.get("pitch"),
    )


async def _retry_offer(db: AsyncSession, run: MagicRun, state: dict) -> Optional[dict]:
    if state.get("phase") != "final_lost" or run.status != "in_progress":
        return None
    config = await get_config(db)
    user = await db.get(User, run.user_id)
    left = max(0, config.magic_retries_daily_limit - _today(user)[2]) if user else 0
    return {"coins": config.magic_retry_coins or None, "stars": config.magic_retry_stars or None,
            "credits": user.magic_retry_credits if user else 0, "left": left,
            "available": left > 0 and not state.get("retry_used")}


def _event_out(state: dict) -> Optional[dict]:
    ev = state.get("event") or {}
    if not ev or ev.get("day") != state["day"] or ev.get("code") not in engine.EVENTS:
        return None
    icon, title, text = engine.EVENTS[ev["code"]]
    return {"code": ev["code"], "icon": icon, "title": title, "text": text}


def _bot_style_out(state: dict) -> Optional[dict]:
    code = state["bot"].get("style")
    if code not in engine.BOT_STYLES:
        return None
    label, text = engine.BOT_STYLES[code]
    return {"code": code, "label": label, "text": text}


async def _hydrate(db: AsyncSession, run: MagicRun, events: list[dict], fresh: bool = False) -> MagicRunOut:
    state = run.server_state or {}
    hero = state["hero"]
    m = state["map"]
    bot = state["bot"]
    finished = run.status != "in_progress"
    skins = state.get("skins") or {}

    def seen(x: int, y: int) -> bool:
        return finished or engine.is_seen(state, x, y)

    reachable = engine.reachable(state) if state["phase"] == "map" and run.status == "in_progress" else []
    pack = state.get("reward_pack") or {}
    return MagicRunOut(
        id=run.id, version=run.version, status=run.status, result=run.result, phase=state["phase"],
        faction=state["faction"], rival=state["rival"], difficulty=state["difficulty"], mode=state.get("mode", "quick"),
        challenge_week=run.challenge_week, day=state["day"],
        days=state["days"], score=state["score"],
        hero=MagicRunHeroOut(
            x=hero["x"], y=hero["y"], moves=hero["moves"], mana=hero["mana"], max_mana=hero["max_mana"],
            spell_power=hero["spell_power"], level=hero["level"], morale=hero.get("morale", 0),
            gold=hero.get("gold", 0), goal=hero.get("goal"),
            artifacts=[MagicArtifactOut(code=a, name=engine.ARTIFACTS[a][0], emoji=engine.ARTIFACTS[a][1],
                                        text=engine.ARTIFACTS[a][2]) for a in hero["artifacts"]],
            spells=[_spell_out(s) for s in hero["spells"]],
        ),
        bot={**({"x": bot["x"], "y": bot["y"], "visible": True, "gain_pct": bot["gain_pct"]}
                if seen(bot["x"], bot["y"]) and not bot.get("solo") else {"visible": False, "gain_pct": bot["gain_pct"]}),
             # Last night's footprints, only where the player can see.
             "trail": [c for c in bot.get("trail") or [] if seen(c[0], c[1])]},
        map_w=m["w"], map_h=m["h"], map_shape=m.get("shape"), biome=m.get("biome", "meadow"), blocks=m.get("blocks", []),
        road=m.get("road", []), tracks=m.get("tracks", []), decor=m.get("decor", []),
        river=m.get("river", []), bridges=m.get("bridges", []),
        seen=[(1 << m["w"]) - 1] * m["h"] if finished else state["seen"],
        seen_hex=[format((1 << m["w"]) - 1 if finished else row, "x") for row in
                  ([0] * m["h"] if finished else state["seen"])],
        objects=[_object_out(state, o) for o in m["objects"] if seen(o["x"], o["y"])], reachable=reachable,
        army=[_stack_out(s) for s in state["army"]], power=engine.army_power(state["army"]),
        battle=_battle_out(state), events=events, log=(state.get("log") or [])[-40:],
        reward_coins=run.reward_coins, rating_delta=run.rating_delta, xp_gained=run.xp_gained,
        level_up=bool(state.get("level_up")), pack_name=pack.get("name"),
        pack_cards=[MagicPackCardOut(**c) for c in pack.get("cards", [])], battles_won=state.get("battles_won", 0),
        notice=state.get("notice") if fresh else None, pending=state.get("pending"),
        quests=state.get("quests") or [], event=_event_out(state), bot_style=_bot_style_out(state),
        perks=[{"code": p, "emoji": engine.PERKS[p][0], "title": engine.PERKS[p][1], "text": engine.PERKS[p][2]}
               for p in state.get("perks") or []],
        retry=await _retry_offer(db, run, state), hero_skin=skins.get("hero", "default"),
        hero_class=state["hero"].get("class", "knight"),
        castle_skin=skins.get("castle", "default"), gold_coins=state.get("gold_coins", 0),
        casualties=_casualties_out(state.get("casualties")),
        created_at=run.created_at,
    )
