"""«Менеджер» — «Помощник президента» (Stars pass "assistant", manager_perks).

Does what the president could do himself with one tap, by his rules
(`office["rules"]`) and within his limit — never sells a player for good,
never borrows, never spends above the limit of the window:
- in the window, `assistant_hours` before it closes (the bot's sweep,
  `window_sweep`): the season sponsor and the shirt sponsor, declining
  cheap bids for the club's players, extending expiring footballers and
  offering users' players a new contract at the same wage, loaning the best
  affordable footballers into empty places (with «Аналитик» — on their own
  positions);
- in the season (`after_round`, inside the round, no commit): the plan for
  the next match if none is set (with «Аналитик» — his advice) and answers
  to the events and press conferences the president left open for a round;
- the season sponsor at the season start (manager_perks.assistant_season_start).
Every action goes to the report «Пока тебя не было» (`office["log"]`).
The first `assistant_trial_days` are free once per club."""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models.manager_club import ManagerClub, ManagerContract, ManagerLeague
from app.models.user import User
from app.services import manager_budget as budget, manager_finance as finance, manager_perks as perks, manager_staff as staff
from app.services.game_config_service import get_config

STYLES = ("safe", "balanced", "bold", "off")
PLAN_RULES = ("auto", "normal", "off")


def _cfg(config) -> dict:
    return finance.cfg(config)


# --- trial, rules, log -----------------------------------------------------------------------

def trial_available(club: Optional[ManagerClub], config) -> bool:
    return (club is not None and int(finance._num(_cfg(config)["assistant_trial_days"])) > 0
            and not staff.office(club).get("trial") and perks.until(club, "assistant") is None)


async def start_trial(db: AsyncSession, user: User) -> dict:
    from app.services import manager_service as ms

    config = await get_config(db)
    club = await ms._owned_club(db, user.id, lock=True)
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    if not trial_available(club, config):
        raise ConflictError("Пробная неделя уже была")
    data = staff.office(club)
    data["trial"] = datetime.now(timezone.utc).isoformat()
    staff.save(club, data)
    perks.extend(club, "assistant", int(finance._num(_cfg(config)["assistant_trial_days"])))
    log(club, "👋", f"{staff.vip_name(club, 'assistant')} приступает к работе — настрой правила в «Штабе»", config)
    await db.commit()
    return await staff.view(db, user)


MODES = ("act", "advise")
KEEP_MAX = 11


def default_rules(club: ManagerClub, config) -> dict:
    grant = finance.grant_of(club.division, config)
    limit = int(grant * finance._num(_cfg(config)["assistant_limit_pct"]) / 100)
    return {"limit": limit, "transfer_limit": limit, "renew_limit": limit, "sponsor": True, "kit": True,
            "fill": True, "renew_min_rating": 60, "renew_max_wage": min(600, int(config.manager_live_wage_max)),
            "decline_below_pct": 80, "min_sale": 0, "keep": [], "mode": "act", "events": "balanced", "plan": "auto"}


def rules_of(club: ManagerClub, config) -> dict:
    return {**default_rules(club, config), **(staff.office(club).get("rules") or {})}


def clean_rules(raw: dict, club: ManagerClub, config) -> dict:
    base = rules_of(club, config)
    out = dict(base)
    grant = finance.grant_of(club.division, config)
    for key in ("sponsor", "kit", "fill"):
        if key in raw:
            out[key] = bool(raw[key])
    for key in ("limit", "transfer_limit", "renew_limit"):
        if key in raw:
            out[key] = max(0, min(int(grant * 2), int(finance._num(raw[key]))))
    if "min_sale" in raw:
        out["min_sale"] = max(0, min(int(grant * 20), int(finance._num(raw["min_sale"]))))
    if "keep" in raw:
        keep = raw["keep"] if isinstance(raw["keep"], list) else []
        clean = [str(k) for k in keep if isinstance(k, str) and k.split(":")[0] in ("npc", "live") and k.split(":")[-1].isdigit()]
        out["keep"] = list(dict.fromkeys(clean))[:KEEP_MAX]
    if "mode" in raw:
        if raw["mode"] not in MODES:
            raise ConflictError("Такого режима нет")
        out["mode"] = raw["mode"]
    if "renew_min_rating" in raw:
        out["renew_min_rating"] = max(0, min(99, int(finance._num(raw["renew_min_rating"]))))
    if "renew_max_wage" in raw:
        out["renew_max_wage"] = max(0, min(int(config.manager_live_wage_max), int(finance._num(raw["renew_max_wage"]))))
    if "decline_below_pct" in raw:
        out["decline_below_pct"] = max(0, min(300, int(finance._num(raw["decline_below_pct"]))))
    for key, allowed in (("events", STYLES), ("plan", PLAN_RULES)):
        if key in raw:
            if raw[key] not in allowed:
                raise ConflictError("Такого правила нет")
            out[key] = raw[key]
    return out


async def set_rules(db: AsyncSession, user: User, raw: dict) -> dict:
    from app.services import manager_service as ms

    config = await get_config(db)
    club = await ms._owned_club(db, user.id, lock=True)
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    data = staff.office(club)
    data["rules"] = clean_rules(raw or {}, club, config)
    staff.save(club, data)
    await db.commit()
    return await staff.view(db, user)


def log(club: ManagerClub, icon: str, text: str, config, eur: int = 0, now: Optional[datetime] = None,
        action: Optional[dict] = None) -> None:
    """A line of the report; with `action` it is advice the president can
    do with one tap (mode "advise")."""
    data = staff.office(club)
    entry = {"id": secrets.token_hex(4), "at": (now or datetime.now(timezone.utc)).isoformat(), "icon": icon, "text": text[:160],
             "eur": int(eur)}
    if action:
        entry["action"] = action
    data["log"] = ([entry] + list(data.get("log") or []))[: int(finance._num(_cfg(config)["assistant_log_size"], 30))]
    staff.save(club, data)


def _advised(club: ManagerClub, ref: str) -> bool:
    return any((e.get("action") or {}).get("ref") == ref for e in staff.office(club).get("log") or [])


def report(club: ManagerClub) -> dict:
    data = staff.office(club)
    seen = data.get("seen")
    entries = list(data.get("log") or [])
    unseen = [e for e in entries if not seen or e["at"] > seen]
    todo = [e for e in entries if e.get("action") and not e.get("done")]
    return {"entries": entries[:12], "unseen": len(unseen), "spent": sum(-e["eur"] for e in unseen if e["eur"] < 0 and not e.get("action")),
            "earned": sum(e["eur"] for e in unseen if e["eur"] > 0 and not e.get("action")), "todo": len(todo)}


async def mark_seen(db: AsyncSession, user: User) -> dict:
    from app.services import manager_service as ms

    club = await ms._owned_club(db, user.id, lock=True)
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    data = staff.office(club)
    data["seen"] = datetime.now(timezone.utc).isoformat()
    staff.save(club, data)
    await db.commit()
    return report(club)


LIMITS = {"all": "limit", "transfer": "transfer_limit", "renew": "renew_limit"}


def _spent(club: ManagerClub, key: str, what: str = "all") -> int:
    row = (staff.office(club).get("spent") or {}).get(key, 0)
    if isinstance(row, int):  # before the separate limits: the total only
        return row if what == "all" else 0
    return int((row or {}).get(what, 0))


def _spend(club: ManagerClub, key: str, eur: int, what: str = "transfer") -> None:
    data = staff.office(club)
    row = {w: _spent(club, key, w) for w in LIMITS}
    row["all"] += int(eur)
    if what in row and what != "all":
        row[what] += int(eur)
    data["spent"] = {key: row}
    staff.save(club, data)


# --- in the window (the bot's sweep) ---------------------------------------------------------

async def window_sweep(db: AsyncSession, now: Optional[datetime] = None) -> int:
    """Clubs with the assistant: his chores once a window, `assistant_hours` before it closes."""
    from app.services import manager_service as ms

    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    pre_end = ms.preseason_end(now, config)
    hours = finance._num(_cfg(config)["assistant_hours"], 3)
    if not (now < pre_end <= now + timedelta(hours=hours)) or not await ms.window_open(db, now):
        return 0
    key = await finance.upcoming_key(db, now)
    clubs = (await db.execute(select(ManagerClub).where(ManagerClub.perks.is_not(None)))).scalars().all()
    todo = [c.id for c in clubs if perks.active(c, "assistant", now) and staff.office(c).get("chores") != key
            and not await ms.is_playing(db, c)]
    await db.commit()  # each chore runs in a session of its own
    for club_id in todo:
        await chores(db, club_id, key, now, config)
    return len(todo)


def _sessions(db: AsyncSession):
    return async_sessionmaker(bind=db.bind, expire_on_commit=False, class_=AsyncSession)


async def _step(db: AsyncSession, club_id: int, run) -> None:
    """One chore in its own session: `run(s, club, user)` does the
    president's own action (which commits) and notes it; a refusal (budget,
    window, a race) leaves nothing behind."""
    token = budget.ACTOR.set("assistant")
    try:
        async with _sessions(db)() as s:
            try:
                club = await s.get(ManagerClub, club_id)
                await run(s, club, await s.get(User, club.owner_id))
            except AppError:
                await s.rollback()
    finally:
        budget.ACTOR.reset(token)


async def _note(s: AsyncSession, club_id: int, icon: str, text: str, config, eur: int = 0, key: Optional[str] = None,
                spend: int = 0, what: str = "transfer", action: Optional[dict] = None) -> None:
    from app.services import manager_service as ms

    club = (await ms._lock_clubs(s, [club_id]))[club_id]
    log(club, icon, text, config, eur, action=action)
    if key and spend > 0:
        _spend(club, key, spend, what)
    await s.commit()


def _left(club: ManagerClub, key: str, config, what: str = "transfer") -> int:
    rules = rules_of(club, config)
    total = max(0, int(rules["limit"]) - _spent(club, key))
    if what == "all":
        return total
    return min(total, max(0, int(rules[LIMITS[what]]) - _spent(club, key, what)))


def _advise(club: ManagerClub, config) -> bool:
    return rules_of(club, config)["mode"] == "advise"


async def chores(db: AsyncSession, club_id: int, key: str, now: datetime, config) -> None:
    """The window's chores. In mode "advise" nothing is done — each would-be
    action is a line of advice with an `action` the president confirms."""
    from app.services import manager_service as ms
    from app.services.club_formation_service import get_formation_slots
    from app.services.lineup_service import on_ideal_position

    async def sponsors(s, club, user):
        rules = rules_of(club, config)
        snap = await ms.base_snapshot(s, club.owner_id, config)
        if rules["sponsor"] and not await finance._taken(s, club.id, "sponsor", key):
            terms = finance.sponsor_terms(club, snap, config)
            if terms:
                best = max(terms, key=lambda t: (t["upfront"] + t["per_win"] * 5, t["code"]))
                if _advise(club, config):
                    await _note(s, club_id, "🤝", f"Советую спонсора сезона: {best['emoji']} {best['name']}", config, best["upfront"],
                                action={"kind": "sponsor", "code": best["code"], "ref": f"sponsor:{key}"})
                    return
                await finance.sign(s, user, "sponsor", best["code"], now=now)
                await _note(s, club_id, "🤝", f"Подписала спонсора сезона: {best['emoji']} {best['name']}", config, best["upfront"])

    async def kit(s, club, user):
        if rules_of(club, config)["kit"] and not await finance.kit_covering(s, club.id, key):
            brand = str((_cfg(config)["kit_brands"] or ["Volt Energy"])[0])
            price = finance.kit_price(club.division, await ms.base_snapshot(s, club.owner_id, config), 1, config)
            if _advise(club, config):
                await _note(s, club_id, "👕", f"Советую спонсора на форме: {brand} на сезон", config, price,
                            action={"kind": "kit", "code": brand, "ref": f"kit:{key}"})
                return
            await finance.sign(s, user, "kit", brand, 1, now=now)
            await _note(s, club_id, "👕", f"Спонсор на форме: {brand} на сезон", config, price)

    async def bids(s, club, user):
        rules = rules_of(club, config)
        keep = set(rules["keep"])
        mine = [c.id for c in await ms._contracts(s, club.id)]
        rows = (await s.execute(select(ManagerContract).where(
            ManagerContract.from_contract_id.in_(mine or [0]), ManagerContract.status == "offered", ManagerContract.kind != ms.RENEW,
            ManagerContract.club_agreed.is_(False),
        ))).scalars().all()
        for bid in rows:
            parent = await s.get(ManagerContract, bid.from_contract_id)
            mp = await ms.my_player_service.get_my_player(s, bid.user_id)
            if parent is None or mp is None:
                continue
            value = ms.live_value(ms.my_player_service.rating_of(mp, config), parent, config)
            if f"live:{parent.id}" in keep:
                why = "он в списке неприкасаемых"
            elif bid.fee < int(rules["min_sale"]):
                why = f"меньше минимальной цены {ms.money(int(rules['min_sale']))}"
            elif bid.fee * 100 < value * int(rules["decline_below_pct"]):
                why = f"меньше {rules['decline_below_pct']}% стоимости"
            else:
                continue
            club = await s.get(ManagerClub, club_id)
            if _advise(club, config):
                if not _advised(club, f"decline:{bid.id}"):
                    await _note(s, club_id, "✋", f"Советую отклонить запрос на {mp.name}: {ms.money(bid.fee)} — {why}", config,
                                action={"kind": "decline", "id": bid.id, "ref": f"decline:{bid.id}"})
                continue
            await ms.respond_offer(s, user, bid.id, False)
            await _note(s, club_id, "✋", f"Отклонила запрос на {mp.name}: {ms.money(bid.fee)} — {why}", config)

    def extend_one(npc_id: int):
        async def run(s, club, user):
            rules = rules_of(club, config)
            n = await s.get(ms.ManagerNpc, npc_id)
            player = await s.get(ms.Player, n.player_id)
            kept = f"npc:{npc_id}" in set(rules["keep"])
            if player is None or (player.rating < int(rules["renew_min_rating"]) and not kept):
                return
            snap = await ms.base_snapshot(s, club.owner_id, config)
            terms = ms.npc_terms(player.rating, config, club.division, snap["discount_pct"], await ms._farm_loan_cut(s, club))
            fee = terms["loan_fee"] if n.kind == "loan" else 0
            loan = n.kind == "loan"
            what = "аренда ещё на сезон" if loan else "контракт на 2 сезона"
            if _advise(club, config):
                await _note(s, club_id, "✍️", f"Советую продлить {player.display_name} ({player.rating}) — {what}", config, -fee,
                            action={"kind": "extend", "id": npc_id, "seasons": 1 if loan else 2, "ref": f"extend:{npc_id}:{key}"})
                return
            if fee + terms["wage_now"] > _left(club, key, config, "renew"):
                await _note(s, club_id, "⏸", f"Не продлила {player.display_name}: нужно {ms.money(fee + terms['wage_now'])}, "
                            f"лимит {ms.money(_left(club, key, config, 'renew'))}", config)
                return
            await ms.extend_npc(s, user, npc_id, 1 if loan else 2)
            await _note(s, club_id, "✍️", f"Продлила {player.display_name} ({player.rating}){' ⭐' if kept else ''} — {what}",
                        config, -fee, key, fee + terms["wage_now"], "renew")
        return run

    def renew_one(contract_id: int):
        async def run(s, club, user):
            rules = rules_of(club, config)
            c = await s.get(ManagerContract, contract_id)
            if c.wage > int(rules["renew_max_wage"]) and f"live:{contract_id}" not in set(rules["keep"]):
                return
            mp = await ms.my_player_service.get_my_player(s, c.user_id)
            who = mp.name if mp else "игроку"
            if _advise(club, config):
                await _note(s, club_id, "✉️", f"Советую предложить {who} новый контракт: {c.wage} монет, 2 сезона", config,
                            action={"kind": "renew", "id": c.id, "wage": c.wage, "ref": f"renew:{c.id}:{key}"})
                return
            await ms.renew_offer(s, user, c.id, c.wage, 2)
            await _note(s, club_id, "✉️", f"Предложила {who} новый контракт: {c.wage} монет, 2 сезона", config)
        return run

    async def fill(s, club, user):
        if not rules_of(club, config)["fill"]:
            return
        analyst = perks.active(club, "analytics", now)
        squad = await ms.squad_view(s, club, config)
        slots = {sl.code: sl for sl in get_formation_slots(ms.tactics.clean_formation(club.formation))}
        advised: set[int] = set()
        for kid in [p for p in squad["xi"] if p["kind"] == "kid"]:
            slot = slots.get(kid["slot"])
            club = await s.get(ManagerClub, club_id)
            if slot is None:
                continue
            page = await ms.npc_catalog(s, user, slot.category, None, 0, "loan", "rating", True)
            options = [p for p in page["players"] if not p["taken_by"] and p["player_id"] not in advised
                       and p["loan_fee"] + p["wage_now"] <= _left(club, key, config, "transfer")]
            if analyst:  # on his own position first
                options.sort(key=lambda p: (not on_ideal_position(ms.Position(p["position"]), slot.ideal_position), -p["rating"]))
            if not options:
                continue
            pick = options[0]
            if _advise(club, config):
                advised.add(pick["player_id"])
                await _note(s, club_id, "📋", f"Советую взять в аренду {pick['name']} ({pick['position']}, {pick['rating']}) на пустое место",
                            config, -pick["loan_fee"], action={"kind": "loan", "id": pick["player_id"], "ref": f"loan:{pick['player_id']}:{key}"})
                continue
            await ms.sign_npc(s, user, pick["player_id"], "loan")
            await _note(s, club_id, "📋", f"Взяла в аренду {pick['name']} ({pick['position']}, {pick['rating']}) на пустое место",
                        config, -pick["loan_fee"], key, pick["loan_fee"] + pick["wage_now"], "transfer")

    await _step(db, club_id, sponsors)
    await _step(db, club_id, kit)
    await _step(db, club_id, bids)
    async with _sessions(db)() as s:
        club = await s.get(ManagerClub, club_id)
        expiring = [n.id for n in await ms._npcs(s, club_id) if n.seasons_left <= 0 and not n.auto]
        pending = {c.from_contract_id for c in await ms._contracts(s, club_id, ("offered",)) if c.kind == ms.RENEW}
        renewals = [c.id for c in await ms._contracts(s, club_id)
                    if c.seasons_left <= 0 and c.kind != "loan" and c.user_id != club.owner_id and c.id not in pending]
    for npc_id in expiring:
        await _step(db, club_id, extend_one(npc_id))
    for contract_id in renewals:
        await _step(db, club_id, renew_one(contract_id))
    await _step(db, club_id, fill)
    async with _sessions(db)() as s:
        club = (await ms._lock_clubs(s, [club_id]))[club_id]
        data = staff.office(club)
        data["chores"] = key
        staff.save(club, data)
        await s.commit()


async def do_advice(db: AsyncSession, user: User, entry_id: str) -> dict:
    """The president does what the assistant advised: his own action (each
    commits), then the line is marked done."""
    from app.services import manager_events as events, manager_service as ms

    club = await ms._owned_club(db, user.id)
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    entry = next((e for e in staff.office(club).get("log") or [] if e.get("id") == entry_id), None)
    if entry is None or not entry.get("action"):
        raise NotFoundError("Такого совета нет")
    if entry.get("done"):
        raise ConflictError("Уже сделано")
    a = entry["action"]
    kind = a.get("kind")
    if kind == "sponsor":
        await finance.sign(db, user, "sponsor", a["code"])
    elif kind == "kit":
        await finance.sign(db, user, "kit", a["code"], 1)
    elif kind == "decline":
        await ms.respond_offer(db, user, int(a["id"]), False)
    elif kind == "extend":
        await ms.extend_npc(db, user, int(a["id"]), int(a.get("seasons", 1)))
    elif kind == "renew":
        await ms.renew_offer(db, user, int(a["id"]), int(a["wage"]), 2)
    elif kind == "loan":
        await ms.sign_npc(db, user, int(a["id"]), "loan")
    elif kind == "event":
        await events.choose(db, user, int(a["id"]), str(a["option"]))
    elif kind == "plan":
        await events.set_plan(db, user, str(a["code"]))
    else:
        raise NotFoundError("Такого совета нет")
    club = await ms._owned_club(db, user.id, lock=True)
    data = staff.office(club)
    data["log"] = [{**e, "done": True} if e.get("id") == entry_id else e for e in data.get("log") or []]
    staff.save(club, data)
    await db.commit()
    return await office_view(db, user)


# --- in the season (inside a round, no commit) -----------------------------------------------

def _score(out: dict, style: str, grant: int) -> float:
    m = out["money"] * 100 / max(1, grant)
    form = out["form_pct"] * max(1, out["form_rounds"])
    if style == "safe":
        return 3 * min(m, 0) + 0.5 * m + 0.5 * form + out["fans"] / 200
    if style == "bold":
        return 2 * form + out["fans"] / 100 + 0.5 * m
    return m + form + out["fans"] / 150


async def after_round(db: AsyncSession, club: ManagerClub, league: ManagerLeague, config, now: Optional[datetime] = None) -> None:
    from app.services import manager_events as events

    now = now or datetime.now(timezone.utc)
    if not perks.active(club, "assistant", now):
        return
    rules = rules_of(club, config)
    advise = rules["mode"] == "advise"
    grant = finance.grant_of(club.division, config)
    if rules["events"] != "off":
        for e in await events.open_events(db, club, league):
            if int((e.data or {}).get("round", 0)) >= league.rounds_played and not advise:
                continue  # came with this round — the president has a round to answer
            options = [o for o in (e.data or {}).get("options") or [] if o.get("code")]
            if not options:
                continue
            boost = await events.boost_of(db, club, e, config)
            pick = max(options, key=lambda o: (_score(events._option_out(o, grant, boost), rules["events"], grant), o["code"]))
            icon = "🎙" if events.is_press(e) else "📰"
            if advise:
                if not _advised(club, f"event:{e.id}"):
                    log(club, icon, f"{e.data.get('title')}: советую «{pick.get('label')}»", config, 0, now,
                        action={"kind": "event", "id": e.id, "option": pick["code"], "ref": f"event:{e.id}"})
                continue
            await events.apply_choice(db, club, league, e, pick, config, now, by="assistant")
            log(club, icon, f"{e.data.get('title')}: «{pick.get('label')}»", config,
                events._option_out(pick, grant, boost)["money"], now)
    nxt = league.rounds_played
    if rules["plan"] != "off" and nxt < len((league.state or {}).get("fixtures") or []) and events._active_plan(club, league.id, nxt, config) is None:
        code, why = None, None
        if rules["plan"] == "auto" and perks.active(club, "analytics", now):
            advice = await perks.advice_for(db, league, club, config)
            if advice and advice.get("plan"):
                code, why = advice["plan"], advice.get("why")
        if code:
            plan = events._plan(code, config) or {}
            text = f"Установка на следующий матч: {plan.get('name', code)}" + (f" — {why}" if why else "")
            if advise:
                ref = f"plan:{league.id}:{nxt}"
                if not _advised(club, ref):
                    log(club, plan.get("emoji", "📋"), f"Советую. {text}", config, 0, now, action={"kind": "plan", "code": code, "ref": ref})
                return
            club.match_plan = {"league_id": league.id, "round": nxt, "code": code, "by": "assistant"}
            budget.act(club, league.season_key, "assistant")
            log(club, plan.get("emoji", "📋"), text, config, 0, now)


# --- the season start (manager_perks) --------------------------------------------------------

def season_start_note(club: ManagerClub, text: str, eur: int, config) -> None:
    if perks.active(club, "assistant"):
        log(club, "🤝", text, config, eur)


async def _squad(db: AsyncSession, club: ManagerClub) -> list[dict]:
    """The players the president may mark untouchable: "npc:<id>" / "live:<contract id>"."""
    from app.services import manager_service as ms

    out = []
    for n in await ms._npcs(db, club.id):
        p = await db.get(ms.Player, n.player_id)
        if p is not None:
            out.append({"key": f"npc:{n.id}", "name": p.display_name, "rating": p.rating, "kind": n.kind})
    for c in await ms._contracts(db, club.id):
        if c.user_id == club.owner_id:
            continue
        mp = await ms.my_player_service.get_my_player(db, c.user_id)
        if mp is not None:
            out.append({"key": f"live:{c.id}", "name": mp.name, "rating": None, "kind": c.kind})
    return out


async def office_view(db: AsyncSession, user: User) -> dict:
    """The assistant's report for «Кабинет» (empty without a club)."""
    from app.services import manager_service as ms

    config = await get_config(db)
    club = await ms._owned_club(db, user.id)
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    return {"active": perks.active(club, "assistant"), "name": staff.vip_name(club, "assistant"),
            "rules": rules_of(club, config), "report": report(club), "trial": trial_available(club, config),
            "press_rounds": [int(r) for r in _cfg(config)["press_rounds"] or []], "squad": await _squad(db, club)}
