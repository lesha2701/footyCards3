"""«Менеджер» at a glance, read-only and light (no season start, no league
resolution — the bot's sweep keeps those fresh every two minutes):

- `summary` for the home tile and the top of the mode: the season phase and
  window, my club in a line, its league place and next match, «Сегодня в
  клубе» (what to do now, most urgent first) and the first-season checklist;
- `claim_onboarding` pays the checklist bonus once (ledger ref)."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import app_timezone
from app.models.manager_club import ManagerClub, ManagerContract, ManagerDeal, ManagerLedger, ManagerLeague, ManagerNpc, ManagerSeason
from app.models.user import User
from app.services import manager_events as events, manager_finance as finance, manager_service as ms, manager_shop
from app.services.career_service import standings
from app.services.game_config_service import get_config

ONBOARDING_REF = "onboarding"
WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


async def _signed(db: AsyncSession, club: ManagerClub) -> bool:
    """The club signed somebody itself: a catalog footballer (not auto) or another user's player."""
    npc = (await db.execute(
        select(ManagerNpc.id).where(ManagerNpc.club_id == club.id, ManagerNpc.auto.is_(False)).limit(1)
    )).first()
    if npc is not None:
        return True
    live = (await db.execute(
        select(ManagerContract.id).where(
            ManagerContract.club_id == club.id, ManagerContract.user_id != club.owner_id,
            ManagerContract.status.in_(("active", "on_loan", "ended")),
        ).limit(1)
    )).first()
    return live is not None


async def checklist(db: AsyncSession, club: ManagerClub, config) -> Optional[dict]:
    """The first-season steps; None once the bonus is paid or after the first season."""
    paid = (await db.execute(
        select(ManagerLedger.id).where(ManagerLedger.club_id == club.id, ManagerLedger.ref == ONBOARDING_REF)
    )).first()
    if paid is not None or club.seasons_played > 0:
        return None
    kinds = set((await db.execute(select(ManagerDeal.kind).where(ManagerDeal.club_id == club.id))).scalars().all())
    steps = [
        {"code": "found", "title": "Основать клуб", "done": True, "tab": "club"},
        {"code": "sign", "title": "Подписать игрока на рынке", "done": await _signed(db, club), "tab": "transfers"},
        {"code": "sponsor", "title": "Выбрать спонсора сезона", "done": "sponsor" in kinds, "tab": "office"},
        {"code": "deal", "title": "Заключить сделку: турне, ТВ, депозит…", "done": bool(kinds - {"sponsor"}), "tab": "office"},
    ]
    return {"steps": steps, "bonus": int(finance._num(finance.cfg(config)["onboarding_bonus_eur"])),
            "ready": all(s["done"] for s in steps)}


async def claim_onboarding(db: AsyncSession, user: User, now: Optional[datetime] = None) -> dict:
    config = await get_config(db)
    club = await ms._owned_club(db, user.id, lock=True)
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    steps = await checklist(db, club, config)
    if steps is None:
        raise ConflictError("Бонус новичка уже получен")
    if not steps["ready"]:
        raise ConflictError("Сначала выполни все шаги")
    key = await finance.club_key(db, club, now)
    await finance.book(db, club, "onboarding", steps["bonus"], key, ref=ONBOARDING_REF, note="Первый сезон")
    await db.commit()
    return await summary(db, user, now)


def _hours(at: Optional[str | datetime], now: datetime) -> Optional[float]:
    if at is None:
        return None
    when = datetime.fromisoformat(at) if isinstance(at, str) else at
    when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
    return (when - now).total_seconds() / 3600


def _place(league: ManagerLeague, club_id: int) -> int:
    teams = (league.state or {}).get("teams") or []
    for place, row in enumerate(standings(league.state or {}), start=1):
        if teams[row["team_index"]]["club_id"] == club_id:
            return place
    return 0


async def _today(db: AsyncSession, user: User, club: Optional[ManagerClub], season: dict, league: Optional[dict],
                 next_match: Optional[dict], now: datetime, config) -> list[dict]:
    """What to do now, most urgent first: {code, icon, text, tab, urgent}."""
    items: list[dict] = []
    # Grouped by the plain column: an expression with a bound value in both
    # SELECT and GROUP BY gets two parameters, and Postgres refuses it.
    mine = dict((await db.execute(
        select(ManagerContract.kind, func.count(ManagerContract.id))
        .where(ManagerContract.user_id == user.id, ManagerContract.status == "offered").group_by(ManagerContract.kind)
    )).all())
    renew_me = mine.pop(ms.RENEW, 0)
    offers_to_me = sum(mine.values())
    if renew_me:
        items.append({"code": "renew_me", "icon": "✍️", "text": "Клуб предлагает тебе новый контракт", "tab": "me", "urgent": True})
    if club is None:
        if offers_to_me:
            items.append({"code": "offers_me", "icon": "✍️", "text": f"Тебя зовут в клуб: {offers_to_me}", "tab": "me", "urgent": True})
        return items
    incoming = int((await db.execute(
        select(func.count(ManagerContract.id)).where(
            ManagerContract.status == "offered", ManagerContract.kind != ms.RENEW,
            ManagerContract.from_contract_id.in_(
                select(ManagerContract.id).where(ManagerContract.club_id == club.id, ManagerContract.status == "active")
            ),
        )
    )).scalar_one())
    if incoming:
        items.append({"code": "incoming", "icon": "📨", "text": f"Предложения по твоим игрокам: {incoming}", "tab": "club", "urgent": True})
    if offers_to_me:
        items.append({"code": "offers_me", "icon": "✍️", "text": f"Тебя зовут в другой клуб: {offers_to_me}", "tab": "me", "urgent": False})
    league_row = await db.get(ManagerLeague, club.league_id) if club.league_id else None
    for event in await events.open_events(db, club, league_row):
        d = event.data or {}
        items.append({"code": "event", "icon": d.get("emoji") or "📰", "text": f"{d.get('title')} — нужно твоё решение", "tab": "club", "urgent": True})
    if season["transfers_open"] and not await ms.is_playing(db, club):
        left = _hours(season["preseason_ends_at"], now)
        if left is not None and 0 < left <= 48:
            text = f"Окно закрывается через {max(1, round(left))} ч" if left >= 1 else "Окно закрывается меньше чем через час"
            items.append({"code": "window", "icon": "⏳", "text": text, "tab": "transfers", "urgent": left <= 12})
        key = await finance.upcoming_key(db, now)
        if not await finance._taken(db, club.id, "sponsor", key):
            items.append({"code": "sponsor", "icon": "🤝", "text": "Спонсор на сезон не выбран", "tab": "office", "urgent": False})
    for hurt in await ms.injuries_of(db, club):
        rounds = hurt["rounds_left"]
        items.append({"code": "injury", "icon": "🩹", "text": f"Травма: {hurt['name']} — ещё {rounds} тур{'а' if 2 <= rounds <= 4 else '' if rounds == 1 else 'ов'}",
                      "tab": "club", "urgent": False})
    if next_match is not None:
        where = "дома" if next_match["home"] else "в гостях"
        at = next_match.get("at")
        clock = ""
        if at:
            local = datetime.fromisoformat(at).astimezone(app_timezone())
            day = "" if local.date() == now.astimezone(app_timezone()).date() else f"{WEEKDAYS[local.weekday()]} "
            clock = f"{day}{local:%H:%M}"
        text = f"Матч {where} с «{next_match['opponent']}»{f' в {clock}' if clock else ''}"
        if next_match.get("edge") == "lose":
            items.append({"code": "edge", "icon": "⚠️", "text": f"{text}: его стиль бьёт твой — проверь тактику", "tab": "club", "urgent": True})
        else:
            items.append({"code": "match", "icon": "⚽", "text": text, "tab": "league", "urgent": False})
    if league is not None and league["status"] == "finished":
        items.append({"code": "settle", "icon": "🏁", "text": "Сезон сыгран — итоги и призовые после последнего тура во всех лигах",
                      "tab": "league", "urgent": False})
    return sorted(items, key=lambda i: not i["urgent"])


async def summary(db: AsyncSession, user: User, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    club = await ms._owned_club(db, user.id)
    pre_end = ms.preseason_end(now, config)
    started = await db.get(ManagerSeason, ms.season_key(now)) is not None
    transfers_open = await ms.window_open(db, now)
    next_pre_end = pre_end if now < pre_end else ms.preseason_end(ms.week_start(now) + timedelta(days=7), config)
    season = {
        "phase": "preseason" if not started else "offseason" if transfers_open else "season",
        "transfers_open": transfers_open,
        "preseason_ends_at": next_pre_end.astimezone(timezone.utc).isoformat(),
        "first_round_at": ms.season_schedule(next_pre_end, config)[0],
        "rounds": ms.rounds_of(config),
    }
    club_out = league_out = next_match = None
    if club is not None:
        league_row = await db.get(ManagerLeague, club.league_id) if club.league_id else None
        if league_row is not None:
            state = league_row.state or {}
            league_out = {
                "status": league_row.status, "rounds_played": league_row.rounds_played,
                "total_rounds": len(state.get("fixtures") or []), "place": _place(league_row, club.id),
                "size": len(state.get("teams") or []),
            }
            next_match = await ms.next_match(db, league_row, club, config)
        club_out = {
            "id": club.id, "name": club.name, "look": manager_shop.resolve_look(club),
            "division": club.division, "division_name": ms.division_name(club.division), "budget": club.budget,
            "trade_locked": await ms.is_playing(db, club) or not transfers_open,
            "seasons_played": club.seasons_played,
            "next_match": None if next_match is None else {
                k: next_match[k] for k in ("opponent", "home", "at", "edge")
            },
            "checklist": await checklist(db, club, config),
        }
    return {
        "enabled": bool(config.manager_enabled),
        "season": season,
        "club": club_out,
        "league": league_out,
        "today": await _today(db, user, club, season, league_out, next_match, now, config),
    }
