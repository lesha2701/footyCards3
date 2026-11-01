"""«Кубок менеджеров» and friendlies of «Менеджер».

Both play one match between two clubs' current squads (`play_one`: the
owner's own player and academy card, the signed players, the club's
tactics against the other's style — the engine of the league).

Cup: created when the season starts (`create`, every club of the season,
a seeded draw, byes to fill the bracket), one round at each of
`cup_round_hours` after the preseason end, resolved by the bot's sweep
and lazily on reads (`resolve`, the cup row locked). A draw goes to
penalties. Prize money by the stage reached, % of the club's division
grant (`cup_prizes_pct`: winner, finalist, semi-finalists, …), journalled
once (ref).

Friendly: played at once against any other club's squad
(`friendly_per_day` a day), no table, no money — the head-to-head."""
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, NotFoundError, RateLimitedError
from app.core.timeutil import app_timezone, ensure_aware
from app.models.enums import NotificationType
from app.models.manager_club import ManagerClub, ManagerCup, ManagerFriendly
from app.models.user import User
from app.services import manager_finance as finance, manager_tactics as tactics, tournament_match_engine
from app.services.game_config_service import get_config
from app.services.notification_service import notify

RELATED = "manager_club"
HISTORY = 5


def _f(config) -> dict:
    return finance.cfg(config)


async def play_one(db: AsyncSession, a: ManagerClub, b: ManagerClub, config) -> dict:
    """One match of the clubs' current squads: {"hs", "as", "goals", "styles"} (a at home)."""
    from app.services import manager_service as ms

    sides, names, styles = {}, {}, {}
    for idx, club, other in ((0, a, b), (1, b, a)):
        entries, cards = await ms.build_pool(db, club, config)
        xi, _ = ms.pick_xi(entries, club.name, ms._division_rating(club.division, config) - ms.FILLER_GAP, club.formation)
        mods = tactics.modifiers(club.style, club.formation, other.style, config)
        sides[idx] = ms._side_from(xi, cards, idx, club.name, club.formation, mods, config)
        names[idx], styles[idx] = club.name, tactics.clean_style(club.style)
    match = tournament_match_engine.simulate_match(sides[0][0], sides[1][0], sides[0][1], sides[1][1], config, names[0], names[1])
    return {"hs": match.score_a, "as": match.score_b,
            "goals": ms._goal_events(match, {"a": sides[0][1], "b": sides[1][1]}), "styles": [styles[0], styles[1]]}


# --- cup ----------------------------------------------------------------------------------------

def _schedule(starts: datetime, rounds: int, config) -> list[str]:
    hours = [float(h) for h in _f(config)["cup_round_hours"]] or [43.0]
    out = []
    for r in range(rounds):
        h = hours[r] if r < len(hours) else hours[-1] + (r - len(hours) + 1)
        out.append((starts + timedelta(hours=h)).astimezone(timezone.utc).isoformat())
    return out


async def create(db: AsyncSession, key: str, starts: datetime, clubs: list[ManagerClub], config) -> Optional[ManagerCup]:
    """The season's cup with a seeded draw (called once from ensure_season)."""
    f = _f(config)
    if not f["cup_enabled"] or len(clubs) < int(finance._num(f["cup_min_clubs"], 4)):
        return None
    ids = sorted(c.id for c in clubs)
    random.Random(f"cup:{key}").shuffle(ids)
    size = 1 << math.ceil(math.log2(len(ids)))
    byes = size - len(ids)
    # The first `byes` drawn go through; the rest pair up.
    first = [{"a": i, "b": None, "w": i} for i in ids[:byes]]
    rest = ids[byes:]
    first += [{"a": rest[i], "b": rest[i + 1]} for i in range(0, len(rest), 2)]
    rounds = int(math.log2(size))
    cup = ManagerCup(season_key=key, status="active", state={
        "rounds": [first], "schedule": _schedule(starts, rounds, config), "total": rounds, "played": 0,
        "names": {str(c.id): c.name for c in clubs}, "winner": None,
    })
    try:
        async with db.begin_nested():
            db.add(cup)
    except IntegrityError:
        return None
    return cup


def _pens(rng: random.Random) -> tuple[int, int]:
    a, b = rng.randint(2, 5), rng.randint(2, 5)
    while a == b:
        if rng.random() < 0.5:
            a += 1
        else:
            b += 1
    return a, b


async def _prize(db: AsyncSession, club: ManagerClub, key: str, stage: int, config) -> int:
    pcts = [finance._num(x) for x in _f(config)["cup_prizes_pct"]]
    if stage >= len(pcts) or pcts[stage] <= 0:
        return 0
    amount = int(finance.grant_of(club.division, config) * pcts[stage] / 100)
    await finance.book(db, club, "cup", amount, key, ref=f"cup:{key}", note="Кубок менеджеров")
    return amount


STAGE_NAMES = ("победитель", "финал", "полуфинал", "1/4 финала", "1/8 финала", "1/16 финала", "1/32 финала", "1/64 финала")


def stage_name(stage: int) -> str:
    return STAGE_NAMES[stage] if stage < len(STAGE_NAMES) else f"{stage}-й круг с конца"


async def _play_round(db: AsyncSession, cup: ManagerCup, config) -> None:
    from app.services import manager_service as ms

    state = dict(cup.state)
    r = int(state["played"])
    matches = [dict(m) for m in state["rounds"][r]]
    ids = {i for m in matches for i in (m["a"], m["b"]) if i}
    clubs = await ms._lock_clubs(db, list(ids))
    total = int(state["total"])
    for m in matches:
        if m.get("b") is None or m["a"] not in clubs or m["b"] not in clubs:
            m["w"] = m["a"] if m["a"] in clubs else m.get("b")  # a bye, or a club gone
            continue
        a, b = clubs[m["a"]], clubs[m["b"]]
        res = await play_one(db, a, b, config)
        m.update({"hs": res["hs"], "as": res["as"], "goals": res["goals"]})
        if res["hs"] != res["as"]:
            m["w"] = a.id if res["hs"] > res["as"] else b.id
        else:
            m["pens"] = list(_pens(random.Random(f"cup:{cup.season_key}:{r}:{a.id}:{b.id}")))
            m["w"] = a.id if m["pens"][0] > m["pens"][1] else b.id
        loser = b if m["w"] == a.id else a
        stage = total - r  # lost the final → 1, the semis → 2…
        prize = await _prize(db, loser, cup.season_key, stage, config)
        await notify(db, loser.owner_id, NotificationType.manager_event, f"«{loser.name}»: вылет из Кубка 🏆",
                     f"Стадия: {stage_name(stage)}." + (f" Призовые {ms.money(prize)}" if prize else ""),
                     related_object_type=RELATED, related_object_id=loser.id)
    state["rounds"] = [*state["rounds"][:r], matches, *state["rounds"][r + 1:]]
    state["played"] = r + 1
    winners = [m["w"] for m in matches if m.get("w")]
    if len(winners) <= 1 or state["played"] >= total:
        champion = clubs.get(winners[0]) if winners else None
        state["winner"] = champion.id if champion else None
        cup.status, cup.finished_at = "finished", datetime.now(timezone.utc)
        if champion is not None:
            prize = await _prize(db, champion, cup.season_key, 0, config)
            await notify(db, champion.owner_id, NotificationType.manager_event, f"«{champion.name}» выиграл Кубок менеджеров! 🏆",
                         f"Призовые {ms.money(prize)}" if prize else "Кубок в витрине",
                         related_object_type=RELATED, related_object_id=champion.id)
    else:
        state["rounds"].append([{"a": winners[i], "b": winners[i + 1] if i + 1 < len(winners) else None}
                                for i in range(0, len(winners), 2)])
    cup.state = state
    flag_modified(cup, "state")


async def resolve(db: AsyncSession, now: Optional[datetime] = None) -> int:
    """Every due round of the running cups (the bot's sweep, reads)."""
    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    keys = (await db.execute(select(ManagerCup.season_key).where(ManagerCup.status == "active"))).scalars().all()
    played = 0
    for key in keys:
        cup = (await db.execute(
            select(ManagerCup).where(ManagerCup.season_key == key).with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )).scalar_one_or_none()
        while cup is not None and cup.status == "active":
            r = int(cup.state["played"])
            schedule = cup.state["schedule"]
            if r >= len(schedule) or ensure_aware(datetime.fromisoformat(schedule[r])) > now:
                break
            await _play_round(db, cup, config)
            played += 1
        await db.commit()
    return played


def _match_out(m: dict, names: dict, mine: Optional[int]) -> dict:
    name = lambda i: names.get(str(i)) if i else None  # noqa: E731
    return {"a": name(m["a"]), "b": name(m.get("b")), "hs": m.get("hs"), "as": m.get("as"), "pens": m.get("pens"),
            "winner": name(m.get("w")), "mine": mine is not None and mine in (m["a"], m.get("b")), "bye": m.get("b") is None}


async def view(db: AsyncSession, user: User, now: Optional[datetime] = None) -> dict:
    from app.services import manager_service as ms

    await resolve(db, now)
    config = await get_config(db)
    club = await ms._owned_club(db, user.id)
    cup = (await db.execute(select(ManagerCup).order_by(ManagerCup.created_at.desc()).limit(1))).scalar_one_or_none()
    history = (await db.execute(
        select(ManagerCup).where(ManagerCup.status == "finished").order_by(ManagerCup.created_at.desc()).limit(HISTORY)
    )).scalars().all()
    pcts = [finance._num(x) for x in _f(config)["cup_prizes_pct"]]
    grant = finance.grant_of(club.division, config) if club else 0
    prizes = [{"stage": stage_name(i), "amount": int(grant * p / 100)} for i, p in enumerate(pcts) if p > 0]
    out = {"enabled": bool(_f(config)["cup_enabled"]), "cup": None, "prizes": prizes,
           "history": [{"season_key": c.season_key, "winner": (c.state.get("names") or {}).get(str(c.state.get("winner")))}
                       for c in history if c.state.get("winner")]}
    if cup is None:
        return out
    state = cup.state or {}
    names = state.get("names") or {}
    mine = club.id if club and str(club.id) in names else None
    total = int(state.get("total", 0))
    alive, stage = None, None
    if mine is not None:
        alive = True
        for r, matches in enumerate(state.get("rounds") or []):
            m = next((x for x in matches if mine in (x["a"], x.get("b"))), None)
            if m is None:
                alive = False
                break
            if m.get("w") and m["w"] != mine:
                alive, stage = False, total - r
                break
        if state.get("winner") == mine:
            stage = 0
    schedule = state.get("schedule") or []
    played = int(state.get("played", 0))
    out["cup"] = {
        "season_key": cup.season_key, "status": cup.status, "clubs": len(names), "total_rounds": total, "played": played,
        "next_at": schedule[played] if cup.status == "active" and played < len(schedule) else None,
        "rounds": [{"index": r, "name": stage_name(total - r) if total - r > 0 else "", "at": schedule[r] if r < len(schedule) else None,
                    "matches": [_match_out(m, names, mine) for m in matches
                                if mine is not None and mine in (m["a"], m.get("b")) or r >= min(total - 2, played - 1)]}
                   for r, matches in enumerate(state.get("rounds") or [])],
        "mine": None if mine is None else {"alive": alive, "stage": stage_name(stage) if stage is not None else None},
        "winner": names.get(str(state.get("winner"))) if state.get("winner") else None,
    }
    return out


# --- friendlies ----------------------------------------------------------------------------------

async def friendly(db: AsyncSession, user: User, club_id: int, now: Optional[datetime] = None) -> dict:
    from app.services import manager_service as ms

    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    me = await ms._owned_club(db, user.id)
    if me is None:
        raise NotFoundError("Сначала основай клуб")
    if club_id == me.id:
        raise ConflictError("Со своим клубом не сыграть")
    other = await db.get(ManagerClub, club_id)
    if other is None:
        raise NotFoundError("Клуб не найден")
    clubs = await ms._lock_clubs(db, [me.id, other.id])
    me, other = clubs[me.id], clubs[other.id]
    day = now.astimezone(app_timezone()).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    today = int((await db.execute(
        select(func.count(ManagerFriendly.id)).where(ManagerFriendly.home_club_id == me.id, ManagerFriendly.created_at >= day)
    )).scalar_one())
    limit = int(finance._num(_f(config)["friendly_per_day"], 3))
    if today >= limit:
        raise RateLimitedError(f"Товарищеских матчей — {limit} в день. Завтра можно снова")
    res = await play_one(db, me, other, config)
    row = ManagerFriendly(home_club_id=me.id, away_club_id=other.id, home_score=res["hs"], away_score=res["as"],
                          data={"goals": res["goals"], "styles": res["styles"]}, created_at=now)
    db.add(row)
    await notify(db, other.owner_id, NotificationType.manager_event, f"Товарищеский матч: «{me.name}» — «{other.name}»",
                 f"Счёт {res['hs']}:{res['as']}. Ответь — вызови их на матч!", related_object_type=RELATED, related_object_id=me.id)
    await db.commit()
    return {"match": {"home": me.name, "away": other.name, "hs": res["hs"], "as": res["as"], "goals": res["goals"]},
            **(await head_to_head(db, me, other, config, now))}


async def head_to_head(db: AsyncSession, me: ManagerClub, other: ManagerClub, config, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    rows = (await db.execute(
        select(ManagerFriendly).where(or_(
            (ManagerFriendly.home_club_id == me.id) & (ManagerFriendly.away_club_id == other.id),
            (ManagerFriendly.home_club_id == other.id) & (ManagerFriendly.away_club_id == me.id),
        )).order_by(ManagerFriendly.id.desc())
    )).scalars().all()
    wins = draws = losses = 0
    for f in rows:
        mine, theirs = (f.home_score, f.away_score) if f.home_club_id == me.id else (f.away_score, f.home_score)
        wins += mine > theirs
        draws += mine == theirs
        losses += mine < theirs
    day = now.astimezone(app_timezone()).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    today = int((await db.execute(
        select(func.count(ManagerFriendly.id)).where(ManagerFriendly.home_club_id == me.id, ManagerFriendly.created_at >= day)
    )).scalar_one())
    return {
        "h2h": {"wins": wins, "draws": draws, "losses": losses,
                "last": [{"home": f.home_club_id == me.id, "hs": f.home_score, "as": f.away_score} for f in rows[:5]]},
        "left_today": max(0, int(finance._num(_f(config)["friendly_per_day"], 3)) - today),
    }


async def h2h_view(db: AsyncSession, user: User, club_id: int) -> dict:
    from app.services import manager_service as ms

    config = await get_config(db)
    me = await ms._owned_club(db, user.id)
    other = await db.get(ManagerClub, club_id)
    if me is None or other is None or me.id == other.id:
        raise NotFoundError("Клуб не найден")
    return await head_to_head(db, me, other, config)
