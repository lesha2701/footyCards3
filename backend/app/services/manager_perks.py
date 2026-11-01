"""«Менеджер»: the Stars passes and gifts — convenience and style only,
nothing here makes a club stronger or sells euros.

- «Помощник президента» (`assistant_stars` for `assistant_days`): signs the
  best sponsor at the season start if the club forgot to (the same offer any
  club signs with one tap in the window) and, `remind_hours` before the
  window closes, sends one reminder of what is still open (sponsor, kit
  sponsor, events waiting for a decision, budget left unspent).
- «Аналитика Pro» (`analytics_stars` for `analytics_days`): the next
  opponent's breakdown (lines against mine, style, form, goals) and share
  price alerts — a move of `price_alert_pct` % or more after a round of a
  club whose shares the club holds (or its own).
- Gifts: a style item for Stars bought for ANOTHER user's club (purchase key
  "manager:gift:<club_id>:<code>"), the giver named in a notification.

Passes live in `manager_clubs.perks` ({"assistant": iso, "analytics": iso,
"reminded": season key}); numbers in GameConfig.manager_finance."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.enums import NotificationType, Position
from app.models.manager_club import ManagerClub, ManagerCosmetic, ManagerLeague, ManagerShare, ManagerStock
from app.models.user import User
from app.services import manager_finance as finance
from app.services.game_config_service import get_config
from app.services.notification_service import notify

PASSES = {
    "assistant": ("Помощник президента", "Подпишет лучшего спонсора, если забудешь, и напомнит о делах до закрытия окна"),
    "analytics": ("Аналитика Pro", "Разбор соперника перед матчем и уведомления о курсе акций"),
}
LINES = ("GK", "DEF", "MID", "FWD")
RELATED = "manager_club"


def _price(code: str, config) -> tuple[int, int]:
    f = finance.cfg(config)
    return int(finance._num(f[f"{code}_stars"])), int(finance._num(f[f"{code}_days"], 30))


def until(club: Optional[ManagerClub], code: str) -> Optional[datetime]:
    raw = ((club.perks if club else None) or {}).get(code)
    return ensure_aware(datetime.fromisoformat(raw)) if raw else None


def active(club: Optional[ManagerClub], code: str, now: Optional[datetime] = None) -> bool:
    end = until(club, code)
    return end is not None and end > (now or datetime.now(timezone.utc))


def extend(club: ManagerClub, code: str, days: int, now: Optional[datetime] = None) -> None:
    now = now or datetime.now(timezone.utc)
    start = max(now, until(club, code) or now)
    club.perks = {**(club.perks or {}), code: (start + timedelta(days=days)).isoformat()}
    flag_modified(club, "perks")


def passes_out(club: Optional[ManagerClub], config, now: Optional[datetime] = None) -> list[dict]:
    out = []
    for code, (name, about) in PASSES.items():
        stars, days = _price(code, config)
        end = until(club, code)
        out.append({"code": code, "name": name, "about": about, "stars": stars, "days": days,
                    "active": active(club, code, now), "until": end.isoformat() if end else None})
    return out


# --- Stars: passes and gifts (through manager_shop's "manager:<code>" flow) ------------------------

def is_pass(code: str) -> bool:
    return code in PASSES


def pass_order(club: ManagerClub, code: str, config) -> tuple[str, str, str, int]:
    stars, days = _price(code, config)
    if stars <= 0:
        raise ConflictError("Сейчас не продаётся")
    name, about = PASSES[code]
    return f"manager:{code}", name, f"«{club.name}»: {about.lower()} — на {days} дн.", stars


def deliver_pass(club: ManagerClub, code: str, config) -> dict:
    _stars, days = _price(code, config)
    extend(club, code, days)
    return {"kind": f"manager_{code}", "name": PASSES[code][0]}


def parse_gift(code: str) -> Optional[tuple[int, str]]:
    """"gift:<club_id>:<item>" → (club_id, item)."""
    parts = code.split(":", 2)
    if len(parts) != 3 or parts[0] != "gift" or not parts[1].isdigit():
        return None
    return int(parts[1]), parts[2]


async def gift_check(db: AsyncSession, giver_id: int, club_id: int, item: Optional[dict]) -> ManagerClub:
    from app.services import manager_shop

    club = await db.get(ManagerClub, club_id)
    if club is None:
        raise NotFoundError("Клуб не найден")
    if club.owner_id == giver_id:
        raise ConflictError("Себе подарок не дарят — купи в «Стиле»")
    if item is None or item["stars"] <= 0:
        raise ConflictError("Этот предмет не дарится")
    if item["code"] in await manager_shop.owned(db, club.id):
        raise ConflictError("У этого клуба он уже есть")
    return club


async def deliver_gift(db: AsyncSession, giver: User, club_id: int, item: dict) -> dict:
    """Paid already — never refuses; an item the club got meanwhile stays as it is."""
    from app.services import manager_shop
    from app.services.manager_service import _name

    club = await db.get(ManagerClub, club_id)
    if club is None:
        return {"kind": "manager_gift", "name": item["name"]}
    if item["code"] not in await manager_shop.owned(db, club.id):
        db.add(ManagerCosmetic(club_id=club.id, code=item["code"]))
    await notify(db, club.owner_id, NotificationType.manager_event, f"🎁 Подарок клубу «{club.name}»",
                 f"{_name(giver)} дарит «{item['name']}» — примерь в «Стиле»", related_object_type=RELATED, related_object_id=club.id)
    return {"kind": "manager_gift", "name": f"{item['name']} для «{club.name}»"}


async def giftable(db: AsyncSession, user: User, club_id: int) -> dict:
    """Style items for Stars the club doesn't have yet."""
    from app.services import manager_shop

    config = await get_config(db)
    club = await db.get(ManagerClub, club_id)
    if club is None:
        raise NotFoundError("Клуб не найден")
    have = await manager_shop.owned(db, club.id)
    items = [i for i in manager_shop.catalog(config) if i["stars"] > 0 and i["code"] not in have and i["kind"] != "stadium_name"]
    return {"club_id": club.id, "club_name": club.name, "look": manager_shop.resolve_look(club),
            "items": sorted(items, key=lambda i: (i["stars"], i["kind"]))}


# --- «Помощник президента» ------------------------------------------------------------------------

async def assistant_season_start(db: AsyncSession, club: ManagerClub, key: str, snap: dict, config) -> Optional[str]:
    """Before the (locked) club's season start: the best sponsor if none was signed."""
    from app.models.manager_club import ManagerDeal

    if not active(club, "assistant") or await finance._taken(db, club.id, "sponsor", key):
        return None
    terms = finance.sponsor_terms(club, snap, config)
    if not terms:
        return None
    best = max(terms, key=lambda s: (s["upfront"] + s["per_win"] * 5, s["code"]))
    deal = ManagerDeal(club_id=club.id, kind="sponsor", season_key=key, seasons=1, option=best["code"], amount=best["upfront"],
                       data={"keys": [key], "brand": best["brand"], "name": best["name"], "per_win": best["per_win"],
                             "places": best["places"], "rest": best["rest"], "relegated": best["relegated"], "assistant": True})
    try:
        await finance._add_deal(db, deal)
    except ConflictError:
        return None
    await finance.book(db, club, "sponsor", best["upfront"], key, ref=f"sponsor_up:{deal.id}", note=best["brand"])
    return f"🤵 Помощник подписал спонсора: {best['emoji']} {best['name']}"


async def _gaps(db: AsyncSession, club: ManagerClub, key: str) -> list[str]:
    from app.services import manager_events as events

    out = []
    if not await finance._taken(db, club.id, "sponsor", key):
        out.append("спонсор сезона не выбран (подпишу сам, если не успеешь)")
    if not await finance.kit_covering(db, club.id, key):
        out.append("нет спонсора на форме")
    league = await db.get(ManagerLeague, club.league_id) if club.league_id else None
    if await events.open_events(db, club, league):
        out.append("событие клуба ждёт решения")
    return out


async def remind(db: AsyncSession, now: Optional[datetime] = None) -> int:
    """The bot's sweep: one reminder per season to clubs with the assistant
    `remind_hours` before the window closes."""
    from app.services import manager_service as ms

    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    pre_end = ms.preseason_end(now, config)
    hours = finance._num(finance.cfg(config)["remind_hours"], 24)
    if not (now < pre_end <= now + timedelta(hours=hours)) or not await ms.window_open(db, now):
        return 0
    key = ms.season_key(now)
    clubs = (await db.execute(select(ManagerClub).where(ManagerClub.perks.is_not(None)))).scalars().all()
    sent = 0
    for club in clubs:
        if not active(club, "assistant", now) or (club.perks or {}).get("reminded") == key:
            continue
        gaps = await _gaps(db, club, await finance.upcoming_key(db, now))
        club.perks = {**(club.perks or {}), "reminded": key}
        flag_modified(club, "perks")
        left = max(1, round((pre_end - now).total_seconds() / 3600))
        body = ("Осталось: " + "; ".join(gaps)) if gaps else "Всё готово к сезону — можно проверить состав и тактику"
        await notify(db, club.owner_id, NotificationType.manager_event, f"🤵 Окно закрывается через {left} ч",
                     body, related_object_type=RELATED, related_object_id=club.id)
        sent += 1
    await db.commit()
    return sent


# --- «Аналитика Pro» ---------------------------------------------------------------------------------

def _line(position: Optional[str]) -> Optional[str]:
    from app.services.my_player_service import category_of

    try:
        return category_of(Position(position))
    except (ValueError, StopIteration):
        return None


def _lines(team: dict) -> dict:
    sums: dict[str, list[int]] = {line: [] for line in LINES}
    for p in team.get("xi") or team.get("players") or []:
        line = _line(p.get("position"))
        if line and p.get("rating") is not None:
            sums[line].append(int(p["rating"]))
    return {line: round(sum(v) / len(v)) if v else None for line, v in sums.items()}


def _record(state: dict, index: int) -> dict:
    form, gf, ga = [], 0, 0
    for round_results in state.get("results") or []:
        for m in round_results:
            for me, f, a in ((m["home"], m["hs"], m["as"]), (m["away"], m["as"], m["hs"])):
                if me == index:
                    gf, ga = gf + f, ga + a
                    form.append("W" if f > a else "D" if f == a else "L")
    return {"form": form[-5:], "gf": gf, "ga": ga, "played": len(form)}


async def analytics(db: AsyncSession, user: User) -> dict:
    from app.services import manager_service as ms

    config = await get_config(db)
    club = await ms._owned_club(db, user.id)
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    if not active(club, "analytics"):
        raise ForbiddenError("Разбор соперника — с «Аналитикой Pro»")
    league = await db.get(ManagerLeague, club.league_id) if club.league_id else None
    out: dict = {"opponent": None}
    if league is not None:
        nxt = await ms.next_match(db, league, club, config)
        state = league.state or {}
        teams = state.get("teams") or []
        mine = next((t for t in teams if t["club_id"] == club.id), None)
        other = next((t for t in teams if nxt and t["name"] == nxt["opponent"]), None)
        if nxt and mine and other:
            my_lines, their_lines = _lines(mine), _lines(other)
            out["opponent"] = {
                "name": other["name"], "home": nxt["home"], "at": nxt["at"], "style": nxt["style"], "formation": nxt["formation"],
                "edge": nxt["edge"], "rating": other.get("rating"), "my_rating": mine.get("rating"),
                "lines": [{"line": line, "mine": my_lines[line], "theirs": their_lines[line]} for line in LINES],
                "record": _record(state, other["index"]), "my_record": _record(state, mine["index"]),
                "injuries": sum(1 for v in ((state.get("injuries") or {}).get(str(other["club_id"])) or {}).values()
                                if int(v.get("back", 0)) > league.rounds_played) if other.get("club_id") else 0,
            }
    return out


async def price_alerts(db: AsyncSession, league: ManagerLeague, before: dict[int, int], config) -> None:
    """After a round (the exchange moved the prices of this league's listed
    clubs): holders with «Аналитика Pro» hear about big moves."""
    pct = finance._num(finance.cfg(config)["price_alert_pct"], 8)
    if pct <= 0 or not before:
        return
    stocks = (await db.execute(select(ManagerStock).where(ManagerStock.club_id.in_(list(before))))).scalars().all()
    moved = {s.club_id: (before[s.club_id], int(s.price)) for s in stocks
             if before.get(s.club_id) and abs(int(s.price) - before[s.club_id]) * 100 >= pct * before[s.club_id]}
    if not moved:
        return
    holders = (await db.execute(
        select(ManagerShare.club_id, ManagerShare.holder_club_id).where(ManagerShare.club_id.in_(list(moved)))
    )).all()
    watchers: dict[int, set[int]] = {cid: {cid} for cid in moved}
    for cid, holder in holders:
        watchers[cid].add(holder)
    names = dict((await db.execute(select(ManagerClub.id, ManagerClub.name).where(ManagerClub.id.in_(list(moved))))).all())
    clubs = {c.id: c for c in (await db.execute(
        select(ManagerClub).where(ManagerClub.id.in_({h for ws in watchers.values() for h in ws}))
    )).scalars().all()}
    for cid, (old, new) in moved.items():
        change = round((new - old) * 100 / old)
        for holder_id in watchers[cid]:
            holder = clubs.get(holder_id)
            if holder is None or not active(holder, "analytics"):
                continue
            arrow = "📈" if change > 0 else "📉"
            await notify(db, holder.owner_id, NotificationType.manager_event,
                         f"{arrow} Акции «{names.get(cid)}» {'+' if change > 0 else ''}{change}%",
                         f"После тура: {old} € → {new} € за акцию", related_object_type=RELATED, related_object_id=cid)
