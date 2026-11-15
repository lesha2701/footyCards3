"""«Менеджер» — the president's own decisions about money:

- «Бюджет сезона»: in the window the president splits the coming season's
  money (`pot` = the budget + the grant still to come) by articles
  (`budget_articles`, each a set of ledger kinds) and keeps the rest as a
  reserve (`office["budget"][key]`). The ledger is the spending; at the
  season's end (`season_end`, inside manager_service._settle) an article
  more than `budget_tolerance_pct` % over its plan costs fans, and a season
  inside every article pays a bonus from the unspent plan.
- «Финансовый отчёт аналитика» (`review`): the season's income and costs by
  lines, what the deals brought, the budget plan's result and advice.
- «Стиль управления»: who made the club's decisions in a season — the
  president or his assistant (`ACTOR`, set by manager_assistant around its
  chores; `act` is called by the decisions themselves). At the season's end
  a hands-on president gets fans and money by the share made by hand.
- «Достижения президента»: computed from the ledger, the loans and the
  office; each is claimed once (ledger ref "ach:<code>") for % of the grant.

Numbers: GameConfig.manager_finance over manager_finance.DEFAULTS."""
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import NotificationType
from app.models.manager_club import ManagerClub, ManagerDeal, ManagerLedger, ManagerLoan
from app.models.user import User
from app.services import manager_finance as finance, manager_staff as staff
from app.services.game_config_service import get_config
from app.services.notification_service import notify

ACTOR: ContextVar[str] = ContextVar("manager_actor", default="me")
ACTORS = ("me", "assistant")
KEEP_KEYS = 4


def _cfg(config) -> dict:
    return finance.cfg(config)


def _n(value, default: float = 0.0) -> float:
    return finance._num(value, default)


def articles(config) -> list[dict]:
    out = []
    for a in _cfg(config)["budget_articles"] or []:
        if isinstance(a, dict) and a.get("code") and a.get("kinds"):
            out.append({"code": str(a["code"])[:16], "name": str(a.get("name") or a["code"]), "emoji": str(a.get("emoji") or "📁"),
                        "kinds": [str(k) for k in a["kinds"]]})
    return out


def _trim(data: dict) -> dict:
    return {k: data[k] for k in sorted(data)[-KEEP_KEYS:]}


# --- who decides -----------------------------------------------------------------------------

def act(club: Optional[ManagerClub], key: str, actor: Optional[str] = None) -> None:
    """One decision of the club in season `key` — by the president, or by
    the assistant while `ACTOR` says so."""
    if club is None or not key:
        return
    who = actor or ACTOR.get()
    if who not in ACTORS:
        return
    data = staff.office(club)
    all_acts = dict(data.get("acts") or {})
    row = {a: int((all_acts.get(key) or {}).get(a, 0)) for a in ACTORS}
    row[who] += 1
    all_acts[key] = row
    data["acts"] = _trim(all_acts)
    staff.save(club, data)


def acts_of(club: ManagerClub, key: str) -> dict:
    row = (staff.office(club).get("acts") or {}).get(key) or {}
    me, helper = int(row.get("me", 0)), int(row.get("assistant", 0))
    total = me + helper
    return {"me": me, "assistant": helper, "total": total, "share": round(me * 100 / total) if total else 0}


def hands_on_reward(club: ManagerClub, key: str, config) -> dict:
    f = _cfg(config)
    a = acts_of(club, key)
    if a["total"] < int(_n(f["hands_on_min"], 5)):
        return {"fans": 0, "money": 0}
    share = a["me"] / a["total"]
    grant = finance.grant_of(club.division, config)
    return {"fans": round(_n(f["hands_on_fans"]) * share), "money": int(grant * _n(f["hands_on_bonus_pct"]) / 100 * share)}


# --- the season budget -----------------------------------------------------------------------

async def _spent(db: AsyncSession, club_id: int, key: str, config) -> dict[str, int]:
    rows = dict((await db.execute(
        select(ManagerLedger.kind, func.sum(ManagerLedger.amount))
        .where(ManagerLedger.club_id == club_id, ManagerLedger.season_key == key, ManagerLedger.amount < 0)
        .group_by(ManagerLedger.kind)
    )).all())
    return {a["code"]: -int(sum(int(rows.get(k) or 0) for k in a["kinds"])) for a in articles(config)}


def plan_of(club: ManagerClub, key: str) -> Optional[dict]:
    return ((staff.office(club).get("budget") or {}).get(key)) or None


async def pot_of(db: AsyncSession, club: ManagerClub, key: str, config) -> int:
    from app.services import manager_service as ms

    if club.budget_season == key:
        return max(0, int(club.budget))
    snap = await ms.base_snapshot(db, club.owner_id, config)
    return max(0, int(club.budget)) + int(ms.season_grant(club.division, snap, config)["total"])


async def set_plan(db: AsyncSession, user: User, alloc: dict, now: Optional[datetime] = None) -> dict:
    from app.services import manager_service as ms

    config = await get_config(db)
    now = now or datetime.now(timezone.utc)
    club = await ms._owned_club(db, user.id, lock=True)
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    if not await finance.window_open(db, club, now):
        raise ConflictError("Бюджет сезона составляют в трансферное окно")
    key = await finance.upcoming_key(db, now)
    pot = await pot_of(db, club, key, config)
    plan = {}
    for a in articles(config):
        value = int(_n((alloc or {}).get(a["code"])))
        if value < 0:
            raise ConflictError("Сумма статьи не может быть меньше нуля")
        plan[a["code"]] = value
    if sum(plan.values()) > pot:
        raise ConflictError(f"В плане больше денег, чем у клуба будет: {ms.money(pot)}")
    data = staff.office(club)
    budgets = dict(data.get("budget") or {})
    budgets[key] = {"pot": pot, "alloc": plan, "at": now.isoformat()}
    data["budget"] = _trim(budgets)
    staff.save(club, data)
    act(club, key)
    await db.commit()
    return await office_view(db, user, now)


def _bonus_cap(club: ManagerClub, config) -> int:
    return int(finance.grant_of(club.division, config) * _n(_cfg(config)["budget_bonus_max_pct"]) / 100)


def _judge(plan: dict, spent: dict[str, int], config, cap: int) -> dict:
    f = _cfg(config)
    tolerance = _n(f["budget_tolerance_pct"])
    over, unspent = [], 0
    for code, planned in (plan.get("alloc") or {}).items():
        used = int(spent.get(code, 0))
        if used > planned * (100 + tolerance) / 100:
            over.append(code)
        unspent += max(0, planned - used)
    bonus = 0 if over else min(cap, int(unspent * _n(f["budget_bonus_pct"]) / 100))
    return {"ok": not over, "over": over, "bonus": bonus, "fans": -int(_n(f["budget_fans_penalty"])) * len(over)}


async def view(db: AsyncSession, user: User, now: Optional[datetime] = None) -> dict:
    from app.services import manager_service as ms

    config = await get_config(db)
    now = now or datetime.now(timezone.utc)
    club = await ms._owned_club(db, user.id)
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    window = await finance.window_open(db, club, now)
    key = await finance.upcoming_key(db, now) if window else await finance.club_key(db, club, now)
    plan = plan_of(club, key)
    spent = await _spent(db, club.id, key, config)
    pot = int(plan["pot"]) if plan else await pot_of(db, club, key, config)
    rows = []
    for a in articles(config):
        planned = int((plan or {}).get("alloc", {}).get(a["code"], 0)) if plan else None
        used = spent.get(a["code"], 0)
        rows.append({"code": a["code"], "name": a["name"], "emoji": a["emoji"], "plan": planned, "spent": used,
                     "left": None if planned is None else planned - used,
                     "over": planned is not None and used > planned * (100 + _n(_cfg(config)["budget_tolerance_pct"])) / 100})
    # A suggestion from last season's spending (or a plain split).
    last = sorted(k for k in (staff.office(club).get("budget") or {}) if k < key)
    prev = (staff.office(club).get("budget") or {}).get(last[-1]) if last else None
    f = _cfg(config)
    return {
        "key": key, "window": window, "pot": pot, "plan": plan["alloc"] if plan else None,
        "reserve": pot - sum(plan["alloc"].values()) if plan else None, "articles": rows,
        "suggest": {r["code"]: s for r, s in zip(rows, _suggest(pot, len(rows)))},
        "tolerance_pct": _n(f["budget_tolerance_pct"]), "fans_penalty": int(_n(f["budget_fans_penalty"])),
        "bonus_pct": _n(f["budget_bonus_pct"]), "bonus_max": _bonus_cap(club, config),
        "result": (plan or {}).get("result"), "last": {"key": last[-1], **(prev.get("result") or {})} if prev and prev.get("result") else None,
        "acts": acts_of(club, key), "hands_on": hands_on_reward(club, key, config),
        "hands_on_min": int(_n(f["hands_on_min"], 5)),
    }


def _suggest(pot: int, n: int) -> list[int]:
    """Wages 55 %, transfers 25 %, the club 10 %, the rest reserve."""
    shares = [55, 25, 10][:n] + [0] * max(0, n - 3)
    return [pot * s // 100 for s in shares]


async def season_end(db: AsyncSession, club: ManagerClub, key: str, config) -> list[str]:
    """The (locked) club's season `key` is over: the budget plan and the
    hands-on bonus. Paid once (ledger refs); returns the report lines."""
    from app.services import manager_service as ms

    lines: list[str] = []
    data = staff.office(club)
    budgets = dict(data.get("budget") or {})
    plan = budgets.get(key)
    if plan and not plan.get("result"):
        result = _judge(plan, await _spent(db, club.id, key, config), config, _bonus_cap(club, config))
        if result["bonus"]:
            await finance.book(db, club, "budget_bonus", result["bonus"], key, ref=f"budget:{key}", note="план бюджета выполнен")
            lines.append(f"бюджет выполнен: бонус {ms.money(result['bonus'])}")
        if result["fans"]:
            club.fans_bonus = max(0, int(club.fans_bonus or 0) + result["fans"])
            names = {a["code"]: a["name"].lower() for a in articles(config)}
            lines.append(f"перерасход ({', '.join(names.get(c, c) for c in result['over'])}): болельщиков {result['fans']}")
        budgets[key] = {**plan, "result": result}
        data["budget"] = budgets
        if result["ok"]:
            data["budget_ok"] = int(data.get("budget_ok", 0)) + 1
    reward = hands_on_reward(club, key, config)
    a = acts_of(club, key)
    if reward["money"] or reward["fans"]:
        if await finance.book(db, club, "hands_on", reward["money"], key, ref=f"hands_on:{key}", note=f"сам решил {a['share']}%"):
            club.fans_bonus = max(0, int(club.fans_bonus or 0) + reward["fans"])
            lines.append(f"стиль управления {a['share']}% сам: +{reward['fans']} болельщиков, {ms.money(reward['money'])}")
            if a["assistant"] == 0:
                data["hands_on_full"] = int(data.get("hands_on_full", 0)) + 1
    staff.save(club, data)
    if lines:
        await notify(db, club.owner_id, NotificationType.manager_event, f"«{club.name}»: решения президента 📒",
                     "; ".join(lines).capitalize(), related_object_type=ms.RELATED, related_object_id=club.id)
    return lines


# --- the analyst's finance review ------------------------------------------------------------

DEAL_LINES = {  # deal → the ledger kinds of its money in and out
    "sponsor": ("Спонсор сезона", ("sponsor",)),
    "kit": ("Спонсор на форме", ("kit",)),
    "tour": ("Турне", ("tour", "tour_cost")),
    "tv": ("ТВ-права", ("tv",)),
    "deposit": ("Депозит", ("deposit_in", "deposit_out")),
    "venture": ("Венчурный фонд", ("venture_in", "venture_out")),
    "insurance": ("Страховка", ("insurance_in", "insurance")),
    "farm": ("Фарм-клуб", ("farm",)),
    "staff": ("Штаб клуба", ("staff_wages",)),
}


async def review(db: AsyncSession, club: ManagerClub, config, now: Optional[datetime] = None) -> Optional[dict]:
    """The latest finished season (or the running one) through the analyst's eyes."""
    from app.services import manager_service as ms

    now = now or datetime.now(timezone.utc)
    seasons = await finance.report(db, club)
    if not seasons:
        return None
    current = await finance.club_key(db, club, now)
    done = [s for s in seasons if s["key"] < current]
    season = done[0] if done else seasons[0]
    by_kind = {line["kind"]: line["amount"] for line in season["lines"]}
    income, expense = season["income"], season["expense"]
    costs = sorted((line for line in season["lines"] if line["group"] == "expense"), key=lambda line: line["amount"])[:3]
    deals = []
    for code, (label, kinds) in DEAL_LINES.items():
        if any(k in by_kind for k in kinds):
            deals.append({"code": code, "label": label, "net": sum(int(by_kind.get(k, 0)) for k in kinds)})
    deals.sort(key=lambda d: -d["net"])
    advice: list[str] = []
    profit = income + expense
    if costs and profit < 0:
        advice.append(f"Сезон в минусе на {ms.money(-profit)}: больше всего ушло на «{costs[0]['label']}» — начни экономию с неё.")
    wages = -int(by_kind.get("wages", 0)) - int(by_kind.get("staff_wages", 0))
    if income > 0 and wages * 100 > income * 70:
        advice.append(f"Зарплаты съели {wages * 100 // income}% дохода — не продлевай дорогих запасных, ищи замену дешевле.")
    loans = -int(by_kind.get("npc_loan", 0))
    if loans and income > 0 and loans * 100 > income * 25:
        advice.append(f"Аренды обошлись в {ms.money(loans)} — сильных игроков выгоднее покупать на 2–3 сезона.")
    if "venture_out" in by_kind and "venture_in" not in by_kind:
        advice.append("Венчурный фонд прогорел — держи на нём не больше десятой части свободных денег.")
    if "tv" not in by_kind:
        advice.append("ТВ-права не проданы — это деньги заранее и без риска.")
    if "tour" not in by_kind:
        advice.append("Турне не было — оно приносит деньги и болельщиков между сезонами.")
    if "sponsor" not in by_kind:
        advice.append("Сезон без спонсора — это потерянные деньги: выбирай его в каждое окно.")
    if "deposit_out" not in by_kind and club.budget > finance.grant_of(club.division, config):
        advice.append(f"На счету {ms.money(club.budget)} лежит без дела — часть можно положить на депозит.")
    plan = plan_of(club, season["key"])
    budget = None
    if plan:
        spent = await _spent(db, club.id, season["key"], config)
        names = {a["code"]: a for a in articles(config)}
        budget = {"result": plan.get("result"), "rows": [
            {"code": c, "name": names[c]["name"] if c in names else c, "emoji": names[c]["emoji"] if c in names else "📁",
             "plan": int(v), "spent": int(spent.get(c, 0))} for c, v in (plan.get("alloc") or {}).items()]}
        over = [r for r in budget["rows"] if r["spent"] > r["plan"]]
        if over:
            advice.append(f"Статья «{over[0]['name']}» превысила план — заложи на неё больше или трать меньше.")
    else:
        advice.append("Составь бюджет сезона в окне: уложишься в план — получишь бонус.")
    if not advice:
        advice.append("Финансы в порядке — так держать.")
    return {"key": season["key"], "finished": season["key"] < current, "income": income, "expense": expense, "profit": profit,
            "costs": [{"label": c["label"], "amount": -c["amount"], "share": round(-c["amount"] * 100 / -expense) if expense else 0}
                      for c in costs],
            "deals": deals, "budget": budget, "advice": advice[:5]}


# --- the president's achievements ------------------------------------------------------------

def _achievement_list(config) -> list[dict]:
    return [a for a in _cfg(config)["president_achievements"] or [] if isinstance(a, dict) and a.get("code")]


async def _progress(db: AsyncSession, club: ManagerClub, config) -> dict[str, int]:
    rows = (await db.execute(
        select(ManagerLedger.season_key, ManagerLedger.kind, ManagerLedger.amount).where(ManagerLedger.club_id == club.id)
    )).all()
    current = await finance.club_key(db, club)
    profit: dict[str, int] = {}
    kinds: set[str] = set()
    best_sale = 0
    for key, kind, amount in rows:
        kinds.add(kind)
        group = finance.KINDS.get(kind, ("finance", ""))[0]
        if group != "finance":
            profit[key] = profit.get(key, 0) + int(amount)
        if kind in ("transfer_in", "npc_sale"):
            best_sale = max(best_sale, int(amount))
    profitable = sum(1 for k, v in profit.items() if v > 0 and k < current)
    loans = int((await db.execute(select(func.count(ManagerLoan.id)).where(ManagerLoan.club_id == club.id))).scalar_one())
    data = staff.office(club)
    rows_staff = await staff.staff_of(db, club.id)
    return {
        "first_profit": profitable, "profit_3": profitable,
        "no_loan": 0 if loans else int(club.seasons_played or 0),
        "ipo": int("ipo" in kinds), "budget_keeper": int(data.get("budget_ok", 0)),
        "hands_on": int(data.get("hands_on_full", 0)),
        "full_staff": int(len(rows_staff) >= staff.slots_of(club.division, config)),
        "promotion": int("promotion" in kinds), "investor": int(bool(kinds & {"deposit_in", "venture_in"})),
        "big_sale": best_sale,
    }


async def achievements(db: AsyncSession, club: ManagerClub, config) -> list[dict]:
    progress = await _progress(db, club, config)
    claimed = set((await db.execute(
        select(ManagerLedger.ref).where(ManagerLedger.club_id == club.id, ManagerLedger.ref.like("ach:%"))
    )).scalars().all())
    grant = finance.grant_of(club.division, config)
    out = []
    for a in _achievement_list(config):
        goal = max(1, int(_n(a.get("goal"), 1)))
        have = int(progress.get(a["code"], 0))
        out.append({"code": a["code"], "emoji": a.get("emoji", "🏅"), "name": a.get("name", a["code"]), "about": a.get("about", ""),
                    "goal": goal, "progress": min(have, goal), "done": have >= goal, "claimed": f"ach:{a['code']}" in claimed,
                    "reward": int(grant * _n(a.get("reward_pct")) / 100)})
    out.sort(key=lambda a: (a["claimed"], not a["done"], -a["progress"] / a["goal"]))
    return out


async def claim(db: AsyncSession, user: User, code: str, now: Optional[datetime] = None) -> dict:
    from app.services import manager_service as ms

    config = await get_config(db)
    club = await ms._owned_club(db, user.id, lock=True)
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    found = next((a for a in await achievements(db, club, config) if a["code"] == code), None)
    if found is None:
        raise NotFoundError("Такого достижения нет")
    if not found["done"]:
        raise ConflictError("Достижение ещё не получено")
    key = await finance.club_key(db, club, now)
    if not await finance.book(db, club, "achievement", found["reward"], key, ref=f"ach:{code}", note=found["name"]):
        raise ConflictError("Награда уже получена")
    await db.commit()
    return await office_view(db, user, now)


async def office_view(db: AsyncSession, user: User, now: Optional[datetime] = None) -> dict:
    """«Решения президента»: the budget, the hands-on meter, achievements
    and — with «Аналитик» — his finance review."""
    from app.services import manager_perks as perks, manager_service as ms

    config = await get_config(db)
    club = await ms._owned_club(db, user.id)
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    analyst = perks.active(club, "analytics", now)
    return {
        "budget": await view(db, user, now),
        "achievements": await achievements(db, club, config),
        "analyst": analyst,
        "review": await review(db, club, config, now) if analyst else None,
    }
