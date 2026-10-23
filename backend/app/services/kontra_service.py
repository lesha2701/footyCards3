"""«Контратака» — DB layer around kontra_engine: the squad (also the arena
defence), arena attacks on other players' squads (or bots), the weekly boss,
«Тактические комплекты» (gear) and rewards.

A battle runs on the server: `kontra_engine.run_until_input` plays every
turn that doesn't need the player (the opponent's, and all of them on
autopilot); a manual battle stops at the player's fighter and waits for
`act`. Every action carries the battle `version` under the row lock — a
stale one gets 409, a retried one (same action, same version as the last
accepted) returns the battle unchanged.
"""
import random
import secrets
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.card import UserCard
from app.models.enums import TransactionType
from app.models.game_config import GameConfig
from app.models.kontra import KontraBattle, KontraGear
from app.models.player import Player
from app.models.user import User
from app.schemas.kontra import (
    KontraAbilityOut,
    KontraArenaOut,
    KontraBattleOut,
    KontraBossOut,
    KontraCardOut,
    KontraEffectOut,
    KontraFighterOut,
    KontraGearListOut,
    KontraGearOut,
    KontraHubOut,
    KontraOfferOut,
    KontraPassiveOut,
    KontraSquadOut,
    KontraUnitOut,
)
from app.schemas.ranking import RankingMetric
from app.services import kontra_catalog as catalog
from app.services import kontra_engine as engine
from app.services import my_player_service, ranking_service
from app.services.game_config_service import get_config
from app.services.match_service import BOT_NAMES
from app.services.player_stats_service import card_rating_bonus, effective_card_stats
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update

SQUAD_SIZE = 5
RELATED = "kontra_battle"
EVENTS_ON_READ = 40
CHEMISTRY_PCT = {3: 4, 4: 7, 5: 10}
ATTACK_SKILLS = frozenset({"sniper", "dribbler", "playmaker", "crosser", "one_on_one"})
LEADER_AURA = {
    "attacker": "Лидер-нападающий: +8% атаки отряду", "midfielder": "Лидер-полузащитник: +8% скорости отряду",
    "defender": "Лидер-защитник: +10% защиты отряду", "goalkeeper": "Лидер-вратарь: +10% HP отряду",
}


def _require_enabled(config: GameConfig) -> None:
    if not config.kontra_enabled:
        raise ConflictError("«Контратака» сейчас недоступна", details={"reason": "disabled"})


# ---------------------------------------------------------------------------
# Cards → fighters
# ---------------------------------------------------------------------------

def _tier(card) -> str:
    if getattr(card, "is_my_player", False):
        return "my_player"
    player = card.player
    if getattr(player, "path_talent_code", None):
        return "path"
    return player.rarity.value if hasattr(player.rarity, "value") else str(player.rarity)


def _numbers(card) -> tuple[int, int, int]:
    if getattr(card, "is_my_player", False):
        p = card.player
        return p.rating, p.attack_rating or p.rating, p.defense_rating or p.rating
    return effective_card_stats(card.player, card_rating_bonus(card))


def _position(card) -> str:
    pos = card.player.position
    return pos.value if hasattr(pos, "value") else str(pos)


def _card_out(card) -> KontraCardOut:
    rating, _, _ = _numbers(card)
    rarity = card.player.rarity
    return KontraCardOut(
        card_id=card.id, display_name=card.player.display_name, position=_position(card),
        rarity=rarity.value if hasattr(rarity, "value") else str(rarity), rating=rating,
        image_path=getattr(card.player, "image_path", None), tier=_tier(card),
    )


def _unit(uid: str, side: str, card, gear: list[KontraGear]) -> dict:
    rating, attack, defense = _numbers(card)
    crit = 5 * (getattr(card, "skill_level", 0) or 0) if getattr(card, "skill_code", None) in ATTACK_SKILLS else 0
    bonus = catalog.gear_bonus({"slot": g.slot, "set_code": g.set_code, "rarity": g.rarity} for g in gear)
    return engine.make_unit(
        uid, side, name=card.player.display_name, card=_card_out(card).model_dump(), position=_position(card),
        tier=_tier(card), rating=rating, attack=attack, defense=defense, crit_bonus=crit, gear=bonus,
    )


def _abilities_out(codes: list[str], cds: Optional[dict] = None) -> list[KontraAbilityOut]:
    out = []
    for code in codes:
        name, cooldown, _, description = engine.ABILITIES[code]
        cd = (cds or {}).get(code, 0)
        out.append(KontraAbilityOut(code=code, name=name, description=description, cooldown=cooldown, cd=cd, ready=cd == 0))
    return out


def _passive_out(code: Optional[str]) -> Optional[KontraPassiveOut]:
    if not code:
        return None
    name, description = engine.PASSIVES[code]
    return KontraPassiveOut(code=code, name=name, description=description)


def _fighter_out(card, gear: list[KontraGear]) -> KontraFighterOut:
    u = _unit("x", "me", card, gear)
    return KontraFighterOut(
        card=KontraCardOut(**u["card"]), role=u["role"], role_label=engine.ROLE_LABELS[u["role"]],
        hp=u["max_hp"], atk=u["atk"], defence=u["def"], spd=u["spd"],
        abilities=_abilities_out([a["code"] for a in u["abilities"]]), passive=_passive_out(u["passive"]),
        gear_count=len(gear),
    )


async def _usable_cards(db: AsyncSession, user_id: int) -> list:
    rows = (await db.execute(
        select(UserCard).where(UserCard.owner_id == user_id, UserCard.is_locked_by_admin.is_(False))
        .options(joinedload(UserCard.player))
    )).unique().scalars().all()
    cards = list(rows)
    mine = await my_player_service.engine_card(db, user_id)
    if mine is not None:
        cards.append(mine)
    cards.sort(key=lambda c: (-_numbers(c)[0], c.id))
    return cards


async def _gear_by_card(db: AsyncSession, user_id: int) -> dict[int, list[KontraGear]]:
    rows = (await db.execute(
        select(KontraGear).where(KontraGear.user_id == user_id, KontraGear.card_id.is_not(None))
    )).scalars().all()
    out: dict[int, list[KontraGear]] = {}
    for g in rows:
        out.setdefault(g.card_id, []).append(g)
    return out


def _auto_pick(cards: list) -> list:
    """Strongest five, with a goalkeeper when there is one."""
    picked = cards[:SQUAD_SIZE]
    if not any(_position(c) == "GK" for c in picked):
        keeper = next((c for c in cards if _position(c) == "GK"), None)
        if keeper is not None and len(picked) == SQUAD_SIZE:
            picked = [*picked[:-1], keeper]
    return picked


async def _squad_cards(db: AsyncSession, user: User) -> tuple[list, Optional[int], list]:
    """(squad cards, leader id, all usable cards) — the saved squad cleaned
    of cards no longer owned, else an automatic pick."""
    cards = await _usable_cards(db, user.id)
    by_id = {c.id: c for c in cards}
    saved = user.kontra_squad or {}
    squad = [by_id[i] for i in saved.get("cards") or [] if i in by_id][:SQUAD_SIZE]
    if not squad:
        squad = _auto_pick(cards)
    leader = saved.get("leader")
    if leader not in {c.id for c in squad}:
        leader = squad[0].id if squad else None
    return squad, leader, cards


def _chemistry(cards: list) -> tuple[int, Optional[str]]:
    clubs = Counter(
        getattr(c.player, "club", None) for c in cards
        if not getattr(c, "is_my_player", False) and getattr(c.player, "club", None)
    )
    if not clubs:
        return 0, None
    club, n = clubs.most_common(1)[0]
    pct = CHEMISTRY_PCT.get(min(n, 5), 0)
    return pct, (f"{club} ×{n}" if pct else None)


def _build_side(side: str, prefix: str, cards: list, leader: Optional[int], gear: dict[int, list]) -> list[dict]:
    units = [_unit(f"{prefix}{i}", side, c, gear.get(c.id, [])) for i, c in enumerate(cards, 1)]
    leader_uid = next((u["id"] for u, c in zip(units, cards) if c.id == leader), None)
    chem, _ = _chemistry(cards)
    engine.apply_team_bonuses(units, leader_uid, chem)
    if any("captain" in u["sets"] for u in units):
        for u in units:
            u["atk"] = u["atk"] * 104 // 100
    return units


def _power(units: list[dict]) -> int:
    return sum(u["atk"] + u["def"] + u["max_hp"] // 10 + u["spd"] for u in units)


async def get_squad(db: AsyncSession, user: User) -> KontraSquadOut:
    squad, leader, cards = await _squad_cards(db, user)
    gear = await _gear_by_card(db, user.id)
    units = _build_side("me", "m", squad, leader, gear)
    chem, chem_label = _chemistry(squad)
    leader_card = next((c for c in squad if c.id == leader), None)
    leader_role = engine.ROLE_BY_POSITION.get(_position(leader_card), "midfielder") if leader_card else None
    return KontraSquadOut(
        fighters=[_fighter_out(c, gear.get(c.id, [])) for c in squad], leader_id=leader, power=_power(units),
        chemistry_pct=chem, chemistry_label=chem_label, leader_aura=LEADER_AURA.get(leader_role) if leader_role else None,
        options=[_fighter_out(c, gear.get(c.id, [])) for c in cards if c.id not in {s.id for s in squad}],
        size=SQUAD_SIZE,
    )


async def set_squad(db: AsyncSession, user: User, card_ids: list[int], leader: int) -> KontraSquadOut:
    if not 1 <= len(card_ids) <= SQUAD_SIZE or len(set(card_ids)) != len(card_ids):
        raise ConflictError(f"В отряде от 1 до {SQUAD_SIZE} разных карточек")
    owned = {c.id for c in await _usable_cards(db, user.id)}
    if not set(card_ids) <= owned:
        raise ForbiddenError("Можно брать только свои карточки")
    if leader not in card_ids:
        raise ConflictError("Лидер должен быть в отряде")
    user.kontra_squad = {"cards": list(card_ids), "leader": leader}
    flag_modified(user, "kontra_squad")
    db.add(user)
    await db.commit()
    return await get_squad(db, user)


async def auto_squad(db: AsyncSession, user: User) -> KontraSquadOut:
    user.kontra_squad = None
    db.add(user)
    await db.commit()
    return await get_squad(db, user)


# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

def _ensure_hourly_reset(user: User) -> None:
    now = datetime.now(timezone.utc)
    if user.kontra_hour_started_at is None or now - ensure_aware(user.kontra_hour_started_at) >= timedelta(hours=1):
        user.kontra_hourly_attempts = 0
        user.kontra_hour_started_at = now


def _ensure_daily_reset(user: User) -> None:
    day = local_today(user.kontra_attempts_reset_at) if user.kontra_attempts_reset_at else None
    if day != local_today():
        user.kontra_rewarded_attempts_today = 0
        user.kontra_attempts_reset_at = datetime.now(timezone.utc)


def _boss_attempts_left(user: User, config: GameConfig) -> int:
    day = local_today(user.kontra_boss_reset_at) if user.kontra_boss_reset_at else None
    used = user.kontra_boss_attempts_today if day == local_today() else 0
    return max(0, config.kontra_boss_daily_attempts - used)


async def _active_battle(db: AsyncSession, user_id: int) -> Optional[int]:
    return (await db.execute(
        select(KontraBattle.id).where(KontraBattle.user_id == user_id, KontraBattle.status == "in_progress")
        .order_by(KontraBattle.id.desc()).limit(1)
    )).scalar_one_or_none()


async def _guard_active(db: AsyncSession, user_id: int) -> None:
    active = await _active_battle(db, user_id)
    if active is not None:
        raise ConflictError("Сначала доиграй текущий бой", details={"active_battle_id": active})


# ---------------------------------------------------------------------------
# Hub, arena
# ---------------------------------------------------------------------------

async def get_hub(db: AsyncSession, user: User) -> KontraHubOut:
    config = await get_config(db)
    squad, _, _ = await _squad_cards(db, user)
    gear_count = (await db.execute(select(func.count(KontraGear.id)).where(KontraGear.user_id == user.id))).scalar_one()
    return KontraHubOut(
        enabled=config.kontra_enabled, squad_ready=bool(squad), rating=user.kontra_rating,
        active_battle_id=await _active_battle(db, user.id), boss_name=catalog.boss_for(local_today())["name"],
        boss_attempts_left=_boss_attempts_left(user, config), gear_count=gear_count,
    )


async def _bot_offer(db: AsyncSession, user: User, power_rating: int, r: random.Random) -> dict:
    target = max(55, min(95, power_rating + r.randint(-3, 3)))
    rows = (await db.execute(
        select(Player.id).where(Player.is_active.is_(True), Player.rating.between(target - 5, target + 5)).order_by(Player.id)
    )).scalars().all()
    if len(rows) < SQUAD_SIZE:
        rows = (await db.execute(select(Player.id).where(Player.is_active.is_(True)).order_by(Player.id))).scalars().all()
    ids = r.sample(list(rows), min(SQUAD_SIZE, len(rows)))
    return {"kind": "bot", "name": r.choice(BOT_NAMES), "rating": max(0, user.kontra_rating + r.randint(-60, 60)),
            "player_ids": ids}


async def _make_offers(db: AsyncSession, user: User) -> list[dict]:
    r = random.Random(secrets.token_hex(8))
    squad, _, _ = await _squad_cards(db, user)
    avg = round(sum(_numbers(c)[0] for c in squad) / len(squad)) if squad else 75
    rivals = (await db.execute(
        select(User).where(User.kontra_squad.is_not(None), User.id != user.id, User.is_banned.is_(False))
        .order_by(func.abs(User.kontra_rating - user.kontra_rating)).limit(6)
    )).scalars().all()
    offers = [{"kind": "user", "user_id": u.id, "name": u.full_display_name(), "rating": u.kontra_rating}
              for u in r.sample(list(rivals), min(2, len(rivals)))]
    while len(offers) < 3:
        offers.append(await _bot_offer(db, user, avg, r))
    return offers


async def _offer_cards(db: AsyncSession, offer: dict) -> tuple[list, Optional[int], dict]:
    """(cards, leader, gear by card) of an offer's defence squad."""
    if offer["kind"] == "user":
        rival = await db.get(User, offer["user_id"])
        if rival is None:
            return [], None, {}
        squad, leader, _ = await _squad_cards(db, rival)
        return squad, leader, await _gear_by_card(db, rival.id)
    rows = (await db.execute(select(Player).where(Player.id.in_(offer["player_ids"])))).scalars().all()
    by_id = {p.id: p for p in rows}
    from types import SimpleNamespace

    cards = [SimpleNamespace(id=-(pid), player=by_id[pid], is_my_player=False) for pid in offer["player_ids"] if pid in by_id]
    return cards, (cards[0].id if cards else None), {}


async def get_arena(db: AsyncSession, user: User, refresh: bool = False) -> KontraArenaOut:
    config = await get_config(db)
    if refresh or not user.kontra_arena_offers:
        user.kontra_arena_offers = await _make_offers(db, user)
        flag_modified(user, "kontra_arena_offers")
        db.add(user)
        await db.commit()
    offers = []
    for i, offer in enumerate(user.kontra_arena_offers or []):
        cards, leader, gear = await _offer_cards(db, offer)
        units = _build_side("foe", "e", cards, leader, gear)
        offers.append(KontraOfferOut(
            index=i, name=offer["name"], rating=offer["rating"], power=_power(units), is_bot=offer["kind"] == "bot",
            cards=[_card_out(c) for c in cards],
        ))
    _ensure_daily_reset(user)
    ranking = await ranking_service.get_ranking(db, RankingMetric.kontra_rating, user)
    return KontraArenaOut(
        rating=user.kontra_rating, rank=ranking.me.rank if ranking.me else None, offers=offers,
        rewarded_today=user.kontra_rewarded_attempts_today, daily_limit=config.kontra_daily_limit,
        reward_win=config.kontra_arena_reward_win, reward_loss=config.kontra_arena_reward_loss,
        rating_win=config.kontra_rating_win, rating_loss=config.kontra_rating_loss,
    )


async def start_arena(db: AsyncSession, user: User, offer_index: int, manual: bool) -> KontraBattleOut:
    config = await get_config(db)
    _require_enabled(config)
    locked = await lock_user_for_update(db, user.id)
    await _guard_active(db, locked.id)
    offers = locked.kontra_arena_offers or []
    if not 0 <= offer_index < len(offers):
        raise NotFoundError("Соперник не найден — обнови список")
    _ensure_hourly_reset(locked)
    if locked.kontra_hourly_attempts >= config.hourly_game_limit:
        remaining = timedelta(hours=1) - (datetime.now(timezone.utc) - ensure_aware(locked.kontra_hour_started_at))
        raise ConflictError("Hourly play limit reached for this game", details={
            "hourly_limit": config.hourly_game_limit, "retry_after_seconds": max(0, int(remaining.total_seconds())),
        })
    squad, leader, _ = await _squad_cards(db, locked)
    if not squad:
        raise ConflictError("Для «Контратаки» нужна хотя бы одна карточка")
    offer = offers[offer_index]
    foe_cards, foe_leader, foe_gear = await _offer_cards(db, offer)
    if not foe_cards:
        raise ConflictError("Этот соперник больше недоступен — обнови список")
    locked.kontra_hourly_attempts += 1
    me = _build_side("me", "m", squad, leader, await _gear_by_card(db, locked.id))
    foe = _build_side("foe", "e", foe_cards, foe_leader, foe_gear)
    state = engine.new_battle(secrets.token_hex(8), me, foe, mode="arena",
                              max_rounds=config.kontra_arena_max_rounds, manual=manual)
    # The offer is used up: a fresh list next time (no re-rolling one fight).
    locked.kontra_arena_offers = None
    db.add(locked)
    battle = KontraBattle(
        user_id=locked.id, mode="arena", opponent_user_id=offer.get("user_id"), opponent_name=offer["name"],
        server_state=state,
    )
    db.add(battle)
    await db.flush()
    return await _run_and_save(db, battle, state, config, locked)


# ---------------------------------------------------------------------------
# Weekly boss
# ---------------------------------------------------------------------------

async def _week_damage(db: AsyncSession, week, user_ids: Optional[list[int]] = None) -> int:
    q = select(func.coalesce(func.sum(KontraBattle.damage), 0)).where(KontraBattle.boss_week == week)
    if user_ids is not None:
        q = q.where(KontraBattle.user_id.in_(user_ids or [0]))
    return int((await db.execute(q)).scalar_one())


async def get_boss(db: AsyncSession, user: User) -> KontraBossOut:
    from app.models.club import Club, ClubMember

    config = await get_config(db)
    today = local_today()
    boss = catalog.boss_for(today)
    week = catalog.week_start(today)
    total = await _week_damage(db, week)
    mine = await _week_damage(db, week, [user.id])
    best = int((await db.execute(
        select(func.coalesce(func.max(KontraBattle.damage), 0)).where(KontraBattle.user_id == user.id, KontraBattle.boss_week == week)
    )).scalar_one())
    club_name, club_damage = None, 0
    membership = (await db.execute(select(ClubMember).where(ClubMember.user_id == user.id))).scalar_one_or_none()
    if membership is not None:
        club = await db.get(Club, membership.club_id)
        member_ids = list((await db.execute(select(ClubMember.user_id).where(ClubMember.club_id == membership.club_id))).scalars())
        club_name, club_damage = (club.name if club else None), await _week_damage(db, week, member_ids)
    top_rows = (await db.execute(
        select(KontraBattle.user_id, func.sum(KontraBattle.damage).label("d"))
        .where(KontraBattle.boss_week == week).group_by(KontraBattle.user_id).order_by(func.sum(KontraBattle.damage).desc()).limit(10)
    )).all()
    names = dict((await db.execute(select(User.id, User.first_name).where(User.id.in_([r[0] for r in top_rows] or [0])))).all())
    return KontraBossOut(
        code=boss["code"], name=boss["name"], tagline=boss["tagline"],
        week_start=datetime.combine(week, datetime.min.time(), tzinfo=timezone.utc),
        week_hp=config.kontra_boss_week_hp, week_damage=total, phase=_phase(total, config),
        my_damage=mine, my_best=best, club_name=club_name, club_damage=club_damage,
        attempts_left=_boss_attempts_left(user, config), attempts_per_day=config.kontra_boss_daily_attempts,
        reward_tiers=[list(t) for t in config.kontra_boss_reward_tiers],
        top=[{"user_id": uid, "name": names.get(uid) or f"#{uid}", "damage": int(d)} for uid, d in top_rows],
    )


def _phase(total: int, config: GameConfig) -> int:
    if config.kontra_boss_week_hp <= 0:
        return 1
    return min(3, 1 + total * 3 // config.kontra_boss_week_hp)


async def start_boss(db: AsyncSession, user: User, manual: bool) -> KontraBattleOut:
    config = await get_config(db)
    _require_enabled(config)
    locked = await lock_user_for_update(db, user.id)
    await _guard_active(db, locked.id)
    if _boss_attempts_left(locked, config) <= 0:
        raise ConflictError("Попытки на босса на сегодня закончились — приходи завтра")
    day = local_today(locked.kontra_boss_reset_at) if locked.kontra_boss_reset_at else None
    if day != local_today():
        locked.kontra_boss_attempts_today = 0
        locked.kontra_boss_reset_at = datetime.now(timezone.utc)
    squad, leader, _ = await _squad_cards(db, locked)
    if not squad:
        raise ConflictError("Для «Контратаки» нужна хотя бы одна карточка")
    locked.kontra_boss_attempts_today += 1
    db.add(locked)
    today = local_today()
    week = catalog.week_start(today)
    info = catalog.boss_for(today)
    phase = _phase(await _week_damage(db, week), config)
    atk = info["atk"] * (100 + 15 * (phase - 1)) // 100
    boss = engine.make_boss("boss", name=info["name"], max_hp=config.kontra_boss_week_hp, atk=atk,
                            defense=info["def"], spd=info["spd"], abilities=info["abilities"])
    me = _build_side("me", "m", squad, leader, await _gear_by_card(db, locked.id))
    state = engine.new_battle(secrets.token_hex(8), me, [boss], mode="boss",
                              max_rounds=config.kontra_boss_max_rounds, manual=manual)
    state["boss"] = {"code": info["code"], "name": info["name"], "tagline": info["tagline"], "phase": phase}
    battle = KontraBattle(user_id=locked.id, mode="boss", opponent_name=info["name"], boss_week=week, server_state=state)
    db.add(battle)
    await db.flush()
    return await _run_and_save(db, battle, state, config, locked)


# ---------------------------------------------------------------------------
# Battle actions
# ---------------------------------------------------------------------------

async def _lock_battle(db: AsyncSession, battle_id: int, user: User) -> KontraBattle:
    battle = (await db.execute(
        select(KontraBattle).where(KontraBattle.id == battle_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if battle is None or battle.user_id != user.id:
        raise NotFoundError("Бой не найден")
    return battle


async def _run_and_save(db: AsyncSession, battle: KontraBattle, state: dict, config: GameConfig, user: User,
                        before: Optional[int] = None) -> KontraBattleOut:
    start = len(state["events"]) if before is None else before
    engine.run_until_input(state)
    battle.version += 1
    if state["finished"]:
        await _finish(db, battle, state, config)
    battle.server_state = state
    flag_modified(battle, "server_state")
    db.add(battle)
    await db.commit()
    await db.refresh(battle)
    return await _hydrate(db, battle, state["events"][start:])


async def act(db: AsyncSession, user: User, battle_id: int, version: int, unit_id: str, ability: str,
              target_id: Optional[str]) -> KontraBattleOut:
    battle = await _lock_battle(db, battle_id, user)
    state = dict(battle.server_state)
    last = state.get("last_action")
    request = {"version": version, "unit": unit_id, "ability": ability, "target": target_id}
    if last == request:
        return await _hydrate(db, battle, [])  # a retried request
    if battle.status != "in_progress":
        raise ConflictError("Бой окончен")
    if version != battle.version:
        raise ConflictError("Бой ушёл вперёд — обнови экран", details={"version": battle.version})
    if state.get("auto") or state.get("turn_of") != unit_id or engine.unit(state, unit_id)["side"] != "me":
        raise ConflictError("Сейчас не твой ход")
    before = len(state["events"])
    try:
        engine.act(state, unit_id, ability, target_id)
    except engine.EngineError as exc:
        raise ConflictError(str(exc))
    state["last_action"] = request
    return await _run_and_save(db, battle, state, await get_config(db), user, before)


async def autoplay(db: AsyncSession, user: User, battle_id: int, version: int) -> KontraBattleOut:
    """Switches the battle to autopilot and plays it to the end."""
    battle = await _lock_battle(db, battle_id, user)
    if battle.status != "in_progress":
        return await _hydrate(db, battle, [])
    if version != battle.version:
        raise ConflictError("Бой ушёл вперёд — обнови экран", details={"version": battle.version})
    state = dict(battle.server_state)
    state["auto"] = True
    return await _run_and_save(db, battle, state, await get_config(db), user)


async def forfeit(db: AsyncSession, user: User, battle_id: int) -> KontraBattleOut:
    battle = await _lock_battle(db, battle_id, user)
    if battle.status != "in_progress":
        raise ConflictError("Бой окончен")
    state = dict(battle.server_state)
    engine._finish(state, "foe")
    state["forfeit"] = True
    battle.version += 1
    await _finish(db, battle, state, await get_config(db))
    battle.server_state = state
    flag_modified(battle, "server_state")
    db.add(battle)
    await db.commit()
    await db.refresh(battle)
    return await _hydrate(db, battle, [])


async def get_battle(db: AsyncSession, user: User, battle_id: int) -> KontraBattleOut:
    battle = await db.get(KontraBattle, battle_id)
    if battle is None or battle.user_id != user.id:
        raise NotFoundError("Бой не найден")
    return await _hydrate(db, battle, (battle.server_state or {}).get("events", [])[-EVENTS_ON_READ:])


async def _drop_gear(db: AsyncSession, battle: KontraBattle, user: User, pct: int, source: str) -> None:
    r = random.Random(f"kontra-drop:{battle.id}")
    if pct <= 0 or r.randint(1, 100) > pct:
        return
    piece = catalog.roll_piece(r)
    gear = KontraGear(user_id=user.id, source=source, **piece)
    db.add(gear)
    await db.flush()
    battle.gear_drop_id = gear.id


async def _finish(db: AsyncSession, battle: KontraBattle, state: dict, config: GameConfig) -> None:
    user = await lock_user_for_update(db, battle.user_id)
    battle.status = "finished"
    battle.resolved_at = datetime.now(timezone.utc)
    if battle.mode == "boss":
        battle.result = "win" if state["winner"] == "me" else "loss"
        battle.damage = state["damage_to_foe"]
        reward = 0
        for threshold, coins in sorted(config.kontra_boss_reward_tiers):
            if battle.damage >= threshold:
                reward = coins
        if state.get("forfeit"):
            reward = 0
        if user.game_rewards_blocked:
            reward = 0
        if reward > 0:
            await credit_coins(db, user, reward, TransactionType.kontra_reward,
                               f"«Контратака»: босс {battle.opponent_name}", RELATED, battle.id)
        battle.reward_coins = reward
        if not state.get("forfeit"):
            await _drop_gear(db, battle, user, config.kontra_gear_drop_boss_pct, "boss")
    else:
        won = state["winner"] == "me"
        battle.result = "win" if won else "loss"
        delta = config.kontra_rating_win if won else -config.kontra_rating_loss
        user.kontra_rating = max(0, user.kontra_rating + delta)
        battle.rating_delta = delta
        _ensure_daily_reset(user)
        reward = 0
        if not state.get("forfeit") and not user.game_rewards_blocked and user.kontra_rewarded_attempts_today < config.kontra_daily_limit:
            reward = config.kontra_arena_reward_win if won else config.kontra_arena_reward_loss
            user.kontra_rewarded_attempts_today += 1
            if reward > 0:
                await credit_coins(db, user, reward, TransactionType.kontra_reward,
                                   f"«Контратака»: арена ({'победа' if won else 'поражение'})", RELATED, battle.id)
        battle.reward_coins = reward
        if won:
            await _drop_gear(db, battle, user, config.kontra_gear_drop_arena_pct, "arena")
    db.add(user)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _gear_out(g: KontraGear) -> KontraGearOut:
    slot_label, stat = catalog.SLOTS[g.slot]
    return KontraGearOut(
        id=g.id, slot=g.slot, slot_label=slot_label, set_code=g.set_code, set_name=catalog.SETS[g.set_code][0],
        rarity=g.rarity, rarity_label=catalog.RARITY_LABELS[g.rarity], stat=stat, pct=catalog.RARITY_PCT[g.rarity],
        card_id=g.card_id,
    )


def _unit_out(u: dict) -> KontraUnitOut:
    return KontraUnitOut(
        id=u["id"], side=u["side"], name=u["name"], card=KontraCardOut(**u["card"]) if u.get("card") else None,
        role=u["role"], tier=u["tier"], hp=u["hp"], max_hp=u["max_hp"],
        meter_pct=max(0, min(100, u["meter"] * 100 // engine.TURN_METER)), alive=u["alive"], leader=bool(u.get("leader")),
        effects=[KontraEffectOut(code=e["code"], label=engine.EFFECT_LABELS.get(e["code"], e["code"]), turns=e["turns"])
                 for e in u["effects"]],
        abilities=_abilities_out([a["code"] for a in u["abilities"]], {a["code"]: a["cd"] for a in u["abilities"]}),
        passive=_passive_out(u.get("passive")),
    )


async def _hydrate(db: AsyncSession, battle: KontraBattle, events: list[dict]) -> KontraBattleOut:
    state = battle.server_state or {}
    turn_of = state.get("turn_of")
    can_act = (
        battle.status == "in_progress" and not state.get("auto") and bool(turn_of)
        and any(u["id"] == turn_of and u["side"] == "me" for u in state.get("units", []))
    )
    drop = await db.get(KontraGear, battle.gear_drop_id) if battle.gear_drop_id else None
    boss = state.get("boss") or {}
    return KontraBattleOut(
        id=battle.id, version=battle.version, mode=battle.mode, status=battle.status, result=battle.result,
        opponent_name=battle.opponent_name, manual=bool(state.get("manual")), auto=bool(state.get("auto")),
        turn_of=turn_of, can_act=can_act, round=state.get("round", 0), max_rounds=state.get("max_rounds", 0),
        units=[_unit_out(u) for u in state.get("units", [])], events=events,
        damage=battle.damage if battle.status == "finished" else state.get("damage_to_foe", 0),
        reward_coins=battle.reward_coins, rating_delta=battle.rating_delta,
        gear_drop=_gear_out(drop) if drop else None, boss_name=boss.get("name"), boss_tagline=boss.get("tagline"),
        created_at=battle.created_at,
    )


# ---------------------------------------------------------------------------
# «Тактические комплекты»
# ---------------------------------------------------------------------------

async def list_gear(db: AsyncSession, user: User) -> KontraGearListOut:
    config = await get_config(db)
    rows = (await db.execute(select(KontraGear).where(KontraGear.user_id == user.id).order_by(KontraGear.id.desc()))).scalars().all()
    return KontraGearListOut(
        items=[_gear_out(g) for g in rows],
        sets=[{"code": code, "name": s[0], "description": s[3]} for code, s in catalog.SETS.items()],
        chest_coins=config.kontra_chest_coins, chest_stars=config.kontra_chest_stars, balance=user.balance,
    )


async def equip_gear(db: AsyncSession, user: User, gear_id: int, card_id: Optional[int]) -> KontraGearListOut:
    gear = await db.get(KontraGear, gear_id)
    if gear is None or gear.user_id != user.id:
        raise NotFoundError("Вещь не найдена")
    if card_id is not None:
        if card_id not in {c.id for c in await _usable_cards(db, user.id)}:
            raise ForbiddenError("Надеть можно только на свою карточку")
        worn = (await db.execute(select(KontraGear).where(
            KontraGear.user_id == user.id, KontraGear.card_id == card_id, KontraGear.slot == gear.slot, KontraGear.id != gear.id,
        ))).scalars().all()
        for old in worn:
            old.card_id = None
            db.add(old)
    gear.card_id = card_id
    db.add(gear)
    await db.commit()
    return await list_gear(db, user)


async def buy_chest(db: AsyncSession, user: User) -> tuple[KontraGearListOut, KontraGearOut]:
    config = await get_config(db)
    _require_enabled(config)
    if config.kontra_chest_coins <= 0:
        raise ConflictError("Сундук за монеты сейчас не продаётся")
    locked = await lock_user_for_update(db, user.id)
    await debit_coins(db, locked, config.kontra_chest_coins, TransactionType.kontra_chest_purchase,
                      "«Контратака»: сундук комплекта", "kontra_gear", None)
    piece = catalog.roll_piece(random.Random(secrets.token_hex(8)))
    gear = KontraGear(user_id=locked.id, source="chest", **piece)
    db.add(gear)
    await db.commit()
    await db.refresh(gear)
    await db.refresh(locked)
    return await list_gear(db, locked), _gear_out(gear)


async def stars_order(db: AsyncSession, user: User) -> tuple[str, int, str, str]:
    config = await get_config(db)
    _require_enabled(config)
    if config.kontra_chest_stars <= 0:
        raise ConflictError("Сундук за звёзды сейчас не продаётся")
    return ("kontra_chest", config.kontra_chest_stars, "Сундук комплекта",
            "«Контратака»: одна случайная вещь «Тактического комплекта».")


async def validate_stars(db: AsyncSession, user_id: int, stars_amount: int) -> tuple[bool, str]:
    config = await get_config(db)
    if not config.kontra_enabled or config.kontra_chest_stars <= 0:
        return False, "Сундук сейчас не продаётся"
    if config.kontra_chest_stars != stars_amount:
        return False, "Цена изменилась — открой покупку заново"
    return True, ""


async def deliver_stars(db: AsyncSession, user: User, invoice) -> dict:
    """Already paid: never refuses; one piece per invoice (source_ref unique)."""
    existing = (await db.execute(select(KontraGear).where(KontraGear.source_ref == invoice.payload_token))).scalar_one_or_none()
    if existing is None:
        piece = catalog.roll_piece(random.Random(f"kontra-chest:{invoice.payload_token}"))
        db.add(KontraGear(user_id=user.id, source="stars", source_ref=invoice.payload_token, **piece))
        await db.flush()
    return {"kind": "kontra_chest"}
