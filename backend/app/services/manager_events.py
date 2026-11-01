"""«Менеджер» between the rounds:

- «Установка на матч» — a plan for the club's next league match only
  (`manager_clubs.match_plan` = {league_id, round, code}): % on the lines
  and a factor on the injury chance of that match (pressing tires legs,
  rotation spares them);
- «События клуба» — after some rounds of the season (`event_rounds`) a
  situation with a choice comes (`manager_events`, one per club and slot):
  money (a % of the division grant, journalled), fans, and the form — % on
  every line for the next rounds (`manager_clubs.buffs`).

Numbers and texts: GameConfig.manager_finance over manager_finance.DEFAULTS
(`match_plans`, `event_rounds`, `events`)."""
import random
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import NotificationType
from app.models.manager_club import ManagerClub, ManagerEvent, ManagerLeague
from app.models.user import User
from app.services import manager_finance as finance
from app.services.game_config_service import get_config
from app.services.notification_service import notify

LINES = ("GK", "DEF", "MID", "FWD")
NORMAL = "normal"
RECENT = 5


def plans(config) -> list[dict]:
    return [p for p in finance.cfg(config)["match_plans"] if isinstance(p, dict) and p.get("code")]


def _plan(code: Optional[str], config) -> Optional[dict]:
    return next((p for p in plans(config) if p["code"] == code), None)


def _active_plan(club: ManagerClub, league_id: int, round_index: int, config) -> Optional[dict]:
    p = club.match_plan or {}
    if p.get("league_id") != league_id or p.get("round") != round_index:
        return None
    return _plan(p.get("code"), config)


def buff_pct(club: ManagerClub, league_id: int, round_index: int) -> float:
    return sum(finance._num(b.get("pct")) for b in (club.buffs or [])
               if b.get("league_id") == league_id and int(b.get("from", 0)) <= round_index < int(b.get("to", 0)))


def match_mods(mods: dict, club: ManagerClub, league_id: int, round_index: int, config) -> dict:
    """The plan of this match and the events' form on top of the tactics' %."""
    plan = _active_plan(club, league_id, round_index, config)
    extra = {line: finance._num((plan or {}).get("mods", {}).get(line)) for line in LINES}
    form = buff_pct(club, league_id, round_index)
    if not form and not any(extra.values()):
        return mods
    return {line: mods.get(line, 0) + extra[line] + form for line in LINES}


def injury_factor(club: ManagerClub, league_id: int, round_index: int, config) -> float:
    plan = _active_plan(club, league_id, round_index, config)
    return finance._num((plan or {}).get("injury_x"), 1.0) if plan else 1.0


async def _club_and_league(db: AsyncSession, user: User, lock: bool = False) -> tuple[ManagerClub, Optional[ManagerLeague]]:
    from app.services import manager_service as ms

    club = await ms._owned_club(db, user.id, lock=lock)
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    league = await db.get(ManagerLeague, club.league_id) if club.league_id else None
    return club, league


async def set_plan(db: AsyncSession, user: User, code: str) -> dict:
    config = await get_config(db)
    club, league = await _club_and_league(db, user, lock=True)
    if league is None or league.status != "active" or league.rounds_played >= len((league.state or {}).get("fixtures") or []):
        raise ConflictError("Установка — на следующий матч сезона, а его сейчас нет")
    if code == NORMAL:
        club.match_plan = None
    else:
        if _plan(code, config) is None:
            raise NotFoundError("Такой установки нет")
        club.match_plan = {"league_id": league.id, "round": league.rounds_played, "code": code}
    await db.commit()
    return await view(db, user)


def _template(code: str, config) -> Optional[dict]:
    return next((e for e in finance.cfg(config)["events"] if isinstance(e, dict) and e.get("code") == code), None)


async def after_round(db: AsyncSession, club: ManagerClub, league: ManagerLeague, config) -> None:
    """The (locked) club just played round `league.rounds_played - 1`: an event comes after the set rounds."""
    rounds = [int(r) for r in finance.cfg(config)["event_rounds"]]
    if league.rounds_played not in rounds:
        return
    slot = rounds.index(league.rounds_played)
    taken = set((await db.execute(
        select(ManagerEvent.code).where(ManagerEvent.club_id == club.id, ManagerEvent.season_key == league.season_key)
    )).scalars().all())
    pool = [e for e in finance.cfg(config)["events"] if isinstance(e, dict) and e.get("code") and e["code"] not in taken]
    if not pool:
        return
    template = random.Random(f"event:{league.id}:{club.id}:{slot}").choice(sorted(pool, key=lambda e: e["code"]))
    try:
        async with db.begin_nested():
            db.add(ManagerEvent(club_id=club.id, season_key=league.season_key, slot=slot, code=template["code"],
                                data={"title": template.get("title"), "text": template.get("text"), "emoji": template.get("emoji"),
                                      "options": template.get("options") or [], "league_id": league.id}))
    except IntegrityError:
        return  # this slot's event already came
    await notify(db, club.owner_id, NotificationType.manager_event, f"«{club.name}»: {template.get('emoji', '📰')} {template.get('title')}",
                 "Нужно твоё решение — загляни в «Менеджер»", related_object_type="manager_club", related_object_id=club.id)


def _option_out(o: dict, grant: int) -> dict:
    money = int(grant * finance._num(o.get("money_pct")) / 100)
    return {"code": o.get("code"), "label": o.get("label"), "money": money, "fans": int(finance._num(o.get("fans"))),
            "form_pct": finance._num(o.get("form_pct")), "form_rounds": int(finance._num(o.get("form_rounds")))}


async def choose(db: AsyncSession, user: User, event_id: int, option: str, now: Optional[datetime] = None) -> dict:
    config = await get_config(db)
    club, league = await _club_and_league(db, user, lock=True)
    event = (await db.execute(
        select(ManagerEvent).where(ManagerEvent.id == event_id, ManagerEvent.club_id == club.id).with_for_update()
    )).scalar_one_or_none()
    if event is None:
        raise NotFoundError("Такого события нет")
    if event.status != "offered":
        raise ConflictError("Решение уже принято")
    if league is None or league.id != (event.data or {}).get("league_id") or league.status != "active":
        event.status = "expired"
        await db.commit()
        raise ConflictError("Сезон закончился — событие прошло без решения")
    raw = next((o for o in (event.data or {}).get("options") or [] if o.get("code") == option), None)
    if raw is None:
        raise NotFoundError("Такого варианта нет")
    out = _option_out(raw, finance.grant_of(club.division, config))
    if out["money"]:
        await finance.book(db, club, "event_in" if out["money"] > 0 else "event_out", out["money"], league.season_key,
                           ref=f"event:{event.id}", note=(event.data or {}).get("title"))
    if out["fans"]:
        club.fans_bonus = max(0, int(club.fans_bonus or 0) + out["fans"])
    if out["form_pct"] and out["form_rounds"] > 0:
        start = league.rounds_played
        club.buffs = [b for b in (club.buffs or []) if b.get("league_id") == league.id] + [
            {"pct": out["form_pct"], "league_id": league.id, "from": start, "to": start + out["form_rounds"], "event": event.id}]
        flag_modified(club, "buffs")
    event.status, event.choice, event.decided_at = "chosen", option, now or datetime.now(timezone.utc)
    event.data = {**(event.data or {}), "result": out}
    flag_modified(event, "data")
    await db.commit()
    return await view(db, user)


def _event_out(e: ManagerEvent, grant: int, open_: bool) -> dict:
    d = e.data or {}
    return {"id": e.id, "code": e.code, "title": d.get("title"), "text": d.get("text"), "emoji": d.get("emoji"),
            "status": "offered" if open_ else ("expired" if e.status == "offered" else e.status), "choice": e.choice,
            "options": [_option_out(o, grant) for o in d.get("options") or []], "result": d.get("result")}


async def open_events(db: AsyncSession, club: ManagerClub, league: Optional[ManagerLeague]) -> list[ManagerEvent]:
    if league is None or league.status != "active":
        return []
    return list((await db.execute(
        select(ManagerEvent).where(ManagerEvent.club_id == club.id, ManagerEvent.season_key == league.season_key,
                                   ManagerEvent.status == "offered")
        .order_by(ManagerEvent.slot)
    )).scalars().all())


async def view(db: AsyncSession, user: User) -> dict:
    """The plans with the one set for the next match, open events and the recent decisions."""
    config = await get_config(db)
    club, league = await _club_and_league(db, user)
    grant = finance.grant_of(club.division, config)
    opened = await open_events(db, club, league)
    recent = list((await db.execute(
        select(ManagerEvent).where(ManagerEvent.club_id == club.id, ManagerEvent.id.not_in([e.id for e in opened] or [0]))
        .order_by(ManagerEvent.id.desc()).limit(RECENT)
    )).scalars().all())
    next_round = None
    if league is not None and league.status == "active" and league.rounds_played < len((league.state or {}).get("fixtures") or []):
        next_round = league.rounds_played
    plan = _active_plan(club, league.id, next_round, config) if next_round is not None else None
    return {
        "plans": [{k: p.get(k) for k in ("code", "name", "emoji", "about", "mods", "injury_x")} for p in plans(config)],
        "plan": plan["code"] if plan else NORMAL,
        "can_plan": next_round is not None,
        "form_pct": buff_pct(club, league.id, next_round) if next_round is not None else 0,
        "events": [_event_out(e, grant, True) for e in opened],
        "recent": [_event_out(e, grant, False) for e in recent],
    }
