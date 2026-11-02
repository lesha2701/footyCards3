"""«Менеджер» → «Кабинет президента»: the club's money as a game of its own.

Every euro is club money (`ManagerClub.budget`) and never becomes coins.
Numbers come from GameConfig.manager_finance over DEFAULTS; most amounts are
a % of the club's division grant (`G`), so they grow with the division.

- Ledger (`manager_ledger`): every change of the budget, by season, kind
  and an optional `ref` that makes a payout happen once — the income and
  expense report.
- Club value: the squad, the budget, deposits, «Клубная база» levels, fans
  and titles, minus the debt.
- Sponsor for a season, one of three types: safe (all at once), bonus (a
  little now, per win and for the top places), ambitious (big for the
  title, nothing on relegation). «Отдел маркетинга» raises them.
- Bank loan: a limit by the division grant and the club value, interest on
  the debt at every season start while it is outstanding, collected at the
  first season start after its term; not enough budget → overdue: a
  penalty and no transfers until it is repaid. «Бухгалтерия» cuts the rate.
- Deals (not buildings — the campus levels are their multipliers): a
  shirt sponsor for 1-3 seasons («Клубный магазин» raises the price; the
  stadium name stays the owner's — it is a Stars cosmetic), a preseason tour (income
  and fans, tired legs in the first rounds; «Клубный отель» cuts its costs,
  «Медиацентр» brings more fans), TV rights sold forward at a discount
  (the season's match income goes to the buyer; «Медиацентр» cuts the
  discount), a season deposit («Бухгалтерия» raises the rate; not while in
  debt), a venture fund (a chance to multiply, else lost; a share of the
  budget at most), a farm club (cheaper loans of footballers, stronger
  academy kids; «Тренировочный центр» makes them stronger still).

Deals are signed in the transfer window for the coming season (unique row
per club, kind and season). Their effects are frozen into the league state
at the season start (`season_start`), played per match (`match_money`) and
paid out when the season is settled (`season_end`) — all inside
manager_service's season flow, so lazily on reads and in the bot's sweep.
"""
import random
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import NotificationType
from app.models.manager_club import ManagerClub, ManagerDeal, ManagerLedger, ManagerLoan, ManagerMerch, ManagerSeason
from app.models.user import User
from app.services.game_config_service import get_config
from app.services.notification_service import notify

DEFAULTS: dict = {
    "enabled": True,
    # Sponsors: % of G. place_pct = by place (index 0 = champion); rest_pct =
    # any other place that is not relegated; relegated_pct = relegated.
    "sponsors": [
        {"code": "safe", "name": "Надёжный", "emoji": "🛡️", "brand": "Northbay Bank",
         "upfront_pct": 25, "win_pct": 0, "place_pct": [], "rest_pct": 0, "relegated_pct": 0},
        {"code": "bonus", "name": "Бонусный", "emoji": "🎯", "brand": "Volt Energy",
         "upfront_pct": 8, "win_pct": 2.5, "place_pct": [15, 10, 5], "rest_pct": 0, "relegated_pct": 0},
        {"code": "ambitious", "name": "Амбициозный", "emoji": "🚀", "brand": "Rocket Telecom",
         "upfront_pct": 0, "win_pct": 0, "place_pct": [80, 25, 25], "rest_pct": 10, "relegated_pct": 0},
    ],
    "sponsor_marketing_pct_per_level": 2,
    # Bank loan.
    "loan_grant_pct": 100, "loan_value_pct": 30, "loan_min_eur": 100_000, "loan_seasons_max": 3,
    "loan_rate_pct": 12, "loan_rate_cut_per_level": 0.16, "loan_rate_min_pct": 6, "loan_penalty_pct": 10,
    # Club value.
    "value_per_base_level": 300_000, "value_per_fan": 20_000, "value_per_title": 5_000_000,
    # Fans won on tours buy tickets: € per fan per home match (× % of the division).
    "fan_ticket_eur": 100,
    # Shirt sponsor: € per season = base + per «Клубный магазин» level (× % of the
    # division), +% per season beyond the first.
    "kit_base_eur": 300_000, "kit_eur_per_level": 60_000, "kit_long_bonus_pct": 10, "kit_seasons_max": 3,
    "kit_brands": ["Volt Energy", "Northbay Bank", "Pulse Mobile", "Golazo Pizza", "Tempo Watches", "Strike Boots"],
    # Preseason tours: revenue / costs in % of G; tired legs: −fatigue_pct to
    # every line in the first fatigue_rounds rounds.
    "tours": [
        {"code": "europe", "name": "Турне по Европе", "emoji": "🏰", "revenue_pct": 12, "cost_pct": 5,
         "fans": 150, "fatigue_pct": 2, "fatigue_rounds": 2},
        {"code": "usa", "name": "Турне по США", "emoji": "🗽", "revenue_pct": 22, "cost_pct": 9,
         "fans": 400, "fatigue_pct": 4, "fatigue_rounds": 3},
        {"code": "asia", "name": "Турне по Азии", "emoji": "🏯", "revenue_pct": 35, "cost_pct": 14,
         "fans": 900, "fatigue_pct": 6, "fatigue_rounds": 4},
    ],
    "tour_hotel_cut_per_level": 2, "tour_media_fans_pct_per_level": 4,
    # TV rights sold forward: the season's expected match income (draws) minus a discount.
    "tv_discount_pct": 30, "tv_media_cut_per_level": 0.8, "tv_discount_min_pct": 10,
    # Deposit for a season.
    "deposit_rate_pct": 4, "deposit_rate_per_level": 0.12, "deposit_max_budget_pct": 80, "deposit_min_eur": 100_000,
    # Venture fund.
    "venture_win_pct": 40, "venture_multiplier": 3, "venture_max_budget_pct": 20, "venture_min_eur": 100_000,
    # Farm club: fee in % of G, cheaper loans, stronger academy kids.
    "farm_fee_pct": 6, "farm_loan_cut_pct": 30, "farm_kid_rating": 3, "farm_kid_per_training_level": 0.2,
    # Exchange (manager_exchange): shares per club, IPO up to ipo_max_pct, one
    # holder up to holder_max_pct of a club, fee burnt on every trade, IPO
    # money per season up to ipo_season_cap_pct of G.
    "exchange_enabled": True, "shares_total": 1000, "ipo_max_pct": 49, "holder_max_pct": 25, "exchange_fee_pct": 2,
    "buyback_premium_pct": 10, "ipo_season_cap_pct": 50, "exchange_spread_pct": 5, "ask_band_pct": 15,
    # Price = the club value without its budget / shares × the form: +price_ppg_pct
    # per point a game above 1.4 (the season), +price_form_pct per point above
    # 1.4 (the last 5 games), within price_min_pct..price_max_pct.
    "price_ppg_pct": 20, "price_form_pct": 10, "price_min_pct": 50, "price_max_pct": 200,
    # Dividends: this % of the season's profit (income − expenses), per share.
    "dividend_pct": 20,
    # Bonds: coupon a season chosen within the range, sold in units; the
    # club owes at most min(G × bond_grant_pct, value × bond_value_pct).
    "bond_rate_min_pct": 4, "bond_rate_max_pct": 25, "bond_unit_eur": 100_000, "bond_grant_pct": 60,
    "bond_value_pct": 20, "bond_seasons_max": 3, "bond_holder_max_pct": 25,
    # Ticket price (% of the base): attendance = 100 − (price − 100) × elasticity
    # (within ticket_attendance_min..max %); home matches give every line
    # (attendance − 100) × ticket_support_pct % (a full stadium pushes, an empty
    # one doesn't); at the season end fans change by (attendance − 100) × ticket_fans_per_pct.
    "ticket_min_pct": 50, "ticket_max_pct": 200, "ticket_elasticity": 0.6, "ticket_attendance_min_pct": 20,
    "ticket_attendance_max_pct": 130, "ticket_support_pct": 0.1, "ticket_fans_per_pct": 20,
    # Injuries: after a match a club's player gets injured with this chance
    # («Медцентр» of «Клубная база» cuts it), misses injury_rounds_min..max
    # rounds; the treatment costs injury_treatment_pct of his value.
    "injury_chance_pct": 8, "injury_rounds_min": 1, "injury_rounds_max": 3, "injury_treatment_pct": 5,
    # Insurance for a season: the premium in % of G (−insurance_medical_cut_pct
    # per «Медцентр» level, at most −50 %), it pays insurance_cover_pct of treatments.
    "insurance_premium_pct": 3, "insurance_medical_cut_pct": 4, "insurance_cover_pct": 100,
    # «Лучший президент»: clubs shown.
    "rating_size": 20,
}

DEAL_KINDS = ("sponsor", "kit", "tour", "tv", "deposit", "venture", "farm", "insurance")

# Report lines: kind → (group, label). Groups: income, expense, finance.
KINDS: dict[str, tuple[str, str]] = {
    "grant": ("income", "Грант и «Клубная база»"),
    "match": ("income", "Доход за матчи"),
    "tickets": ("income", "Билеты"),
    "prize": ("income", "Призовые"),
    "promotion": ("income", "Бонус за повышение"),
    "parachute": ("income", "Компенсация за вылет"),
    "merch": ("income", "Мерч болельщиков"),
    "transfer_in": ("income", "Продажа игроков"),
    "npc_sale": ("income", "Продажа футболистов"),
    "sponsor": ("income", "Спонсор"),
    "kit": ("income", "Спонсор на форме"),
    "tour": ("income", "Турне"),
    "tv": ("income", "ТВ-права"),
    "wages": ("expense", "Зарплаты"),
    "transfer_out": ("expense", "Покупка игроков"),
    "npc_buy": ("expense", "Покупка футболистов"),
    "npc_loan": ("expense", "Аренда футболистов"),
    "tour_cost": ("expense", "Расходы на турне"),
    "farm": ("expense", "Фарм-клуб"),
    "injury": ("expense", "Лечение травм"),
    "insurance": ("expense", "Страховка игроков"),
    "insurance_in": ("income", "Страховые выплаты"),
    "loan_in": ("finance", "Кредит банка"),
    "loan_repay": ("finance", "Погашение кредита"),
    "deposit_out": ("finance", "Вклад на депозит"),
    "deposit_in": ("finance", "Депозит с процентами"),
    "venture_out": ("finance", "Венчурный фонд"),
    "venture_in": ("finance", "Доход венчура"),
    "ipo": ("finance", "Продажа акций (IPO)"),
    "buyback": ("finance", "Выкуп своих акций"),
    "shares_buy": ("finance", "Покупка акций"),
    "shares_sell": ("finance", "Продажа акций"),
    "dividend_in": ("income", "Дивиденды"),
    "dividend_out": ("expense", "Дивиденды акционерам"),
    "bond_in": ("finance", "Облигации клуба"),
    "bond_buy": ("finance", "Покупка облигаций"),
    "coupon_in": ("income", "Купоны облигаций"),
    "coupon_out": ("expense", "Купоны по облигациям"),
    "bond_back": ("finance", "Погашение облигаций (получено)"),
    "bond_repay": ("finance", "Погашение своих облигаций"),
}
REPORT_SEASONS = 6


def cfg(config) -> dict:
    stored = getattr(config, "manager_finance", None) or {}
    return {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}


def _num(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def validate(raw: dict) -> dict:
    """Admin input: known keys only, numbers non-negative, lists of objects
    for sponsors / tours."""
    out = {}
    for key, value in (raw or {}).items():
        if key not in DEFAULTS:
            raise ValueError(f"неизвестный параметр «{key}»")
        default = DEFAULTS[key]
        if isinstance(default, bool):
            out[key] = bool(value)
        elif isinstance(default, (int, float)):
            number = _num(value, -1)
            if number < 0:
                raise ValueError(f"{key}: нужно неотрицательное число")
            out[key] = number if isinstance(value, float) and not number.is_integer() else int(number)
        elif key in ("sponsors", "tours"):
            if not isinstance(value, list) or not 1 <= len(value) <= 6 or not all(isinstance(x, dict) and x.get("code") for x in value):
                raise ValueError(f"{key}: нужен список из 1–6 объектов с code")
            out[key] = value
        elif key == "kit_brands":
            if not isinstance(value, list) or not value:
                raise ValueError("kit_brands: нужен список названий")
            out[key] = [str(x)[:24] for x in value]
    return out


# --- seasons -------------------------------------------------------------------------------

def shift_key(key: str, weeks: int) -> str:
    year, week = key.split("-W")
    day = date.fromisocalendar(int(year), int(week), 1) + timedelta(weeks=weeks)
    y, w, _ = day.isocalendar()
    return f"{y}-W{w:02d}"


def keys_from(key: str, seasons: int) -> list[str]:
    return [shift_key(key, i) for i in range(max(1, seasons))]


async def upcoming_key(db: AsyncSession, now: datetime) -> str:
    """The season a club out of play prepares for: this week's, unless it has
    already started (then next week's)."""
    from app.services import manager_service as ms

    key = ms.season_key(now)
    return shift_key(key, 1) if await db.get(ManagerSeason, key) is not None else key


async def club_key(db: AsyncSession, club: ManagerClub, now: Optional[datetime] = None) -> str:
    """The season money of this moment belongs to: the league's while it
    runs, the coming one otherwise."""
    from app.services import manager_service as ms
    from app.models.manager_club import ManagerLeague

    if club.league_id:
        row = (await db.execute(
            select(ManagerLeague.season_key, ManagerLeague.status).where(ManagerLeague.id == club.league_id)
        )).first()
        if row is not None and row.status == "active":
            return row.season_key
    return await upcoming_key(db, now or datetime.now(timezone.utc))


# --- money -------------------------------------------------------------------------------------

async def book(
    db: AsyncSession, club: ManagerClub, kind: str, amount: int, key: str, ref: Optional[str] = None, note: Optional[str] = None,
) -> bool:
    """Changes the (locked) club's budget and journals it. With `ref` the
    entry happens once per club; False = it already did."""
    amount = int(amount)
    if ref is not None:
        exists = (await db.execute(
            select(ManagerLedger.id).where(ManagerLedger.club_id == club.id, ManagerLedger.ref == ref)
        )).first()
        if exists is not None:
            return False
    if amount == 0 and ref is None:
        return True
    club.budget += amount
    db.add(ManagerLedger(club_id=club.id, season_key=key, kind=kind, amount=amount, ref=ref, note=(note or None) and note[:120]))
    return True


def grant_of(division: int, config) -> int:
    from app.services import manager_service as ms

    return ms._pick(config.manager_division_budget, division - 1, 2_000_000)


def _division_pct(division: int, config) -> int:
    from app.services import manager_service as ms

    return ms._pct(config.manager_division_income_pct, division)


def _share(grant: int, pct) -> int:
    from app.services import manager_service as ms

    return ms._nice(grant * _num(pct) / 100)


def _lvl(snap: dict, code: str) -> int:
    return int((snap or {}).get(code, 0) or 0)


def sponsor_terms(club: ManagerClub, snap: dict, config) -> list[dict]:
    f = cfg(config)
    grant = grant_of(club.division, config)
    boost = 100 + _num(f["sponsor_marketing_pct_per_level"]) * _lvl(snap, "marketing")
    out = []
    for s in f["sponsors"]:
        def eur(pct) -> int:
            return _share(grant, _num(pct) * boost / 100)

        out.append({
            "code": str(s["code"]), "name": str(s.get("name") or s["code"]), "emoji": str(s.get("emoji") or "🤝"),
            "brand": str(s.get("brand") or ""), "upfront": eur(s.get("upfront_pct")), "per_win": eur(s.get("win_pct")),
            "places": [eur(p) for p in (s.get("place_pct") or [])], "rest": eur(s.get("rest_pct")),
            "relegated": eur(s.get("relegated_pct")),
        })
    return out


def loan_rate_bp(snap: dict, config) -> int:
    f = cfg(config)
    rate = max(_num(f["loan_rate_min_pct"]), _num(f["loan_rate_pct"]) - _num(f["loan_rate_cut_per_level"]) * _lvl(snap, "accounting"))
    return int(round(rate * 100))


def deposit_rate_bp(snap: dict, config) -> int:
    f = cfg(config)
    return int(round((_num(f["deposit_rate_pct"]) + _num(f["deposit_rate_per_level"]) * _lvl(snap, "accounting")) * 100))


def tv_discount_pct(snap: dict, config) -> float:
    f = cfg(config)
    return max(_num(f["tv_discount_min_pct"]), _num(f["tv_discount_pct"]) - _num(f["tv_media_cut_per_level"]) * _lvl(snap, "media"))


def tv_estimate(division: int, config) -> int:
    from app.services import manager_service as ms

    return ms.rounds_of(config) * config.manager_income_draw * _division_pct(division, config) // 100


def kit_price(division: int, snap: dict, seasons: int, config) -> int:
    """€ per season, frozen when signed."""
    from app.services import manager_service as ms

    f = cfg(config)
    base = (int(_num(f["kit_base_eur"])) + int(_num(f["kit_eur_per_level"])) * _lvl(snap, "shop")) * _division_pct(division, config) // 100
    return ms._nice(base * (100 + _num(f["kit_long_bonus_pct"]) * (seasons - 1)) / 100)


def tour_terms(division: int, snap: dict, config) -> list[dict]:
    f = cfg(config)
    grant = grant_of(division, config)
    hotel_cut = min(90.0, _num(f["tour_hotel_cut_per_level"]) * _lvl(snap, "hotel"))
    fans_boost = 100 + _num(f["tour_media_fans_pct_per_level"]) * _lvl(snap, "media")
    out = []
    for t in f["tours"]:
        cost = _share(grant, _num(t.get("cost_pct")) * (100 - hotel_cut) / 100)
        out.append({
            "code": str(t["code"]), "name": str(t.get("name") or t["code"]), "emoji": str(t.get("emoji") or "✈️"),
            "revenue": _share(grant, t.get("revenue_pct")), "cost": cost, "fans": int(_num(t.get("fans")) * fans_boost / 100),
            "fatigue_pct": _num(t.get("fatigue_pct")), "fatigue_rounds": int(_num(t.get("fatigue_rounds"))),
        })
    return out


def farm_terms(division: int, snap: dict, config) -> dict:
    f = cfg(config)
    return {
        "fee": _share(grant_of(division, config), f["farm_fee_pct"]), "loan_cut_pct": int(_num(f["farm_loan_cut_pct"])),
        "kid_bonus": int(round(_num(f["farm_kid_rating"]) + _num(f["farm_kid_per_training_level"]) * _lvl(snap, "training"))),
    }


# --- club value & loans ------------------------------------------------------------------------

async def fans_of(db: AsyncSession, club: ManagerClub) -> int:
    buyers = (await db.execute(
        select(func.count(func.distinct(ManagerMerch.user_id))).where(ManagerMerch.club_id == club.id)
    )).scalar_one()
    return int(buyers) + int(club.fans_bonus or 0)


async def open_loan(db: AsyncSession, club_id: int, lock: bool = False) -> Optional[ManagerLoan]:
    stmt = select(ManagerLoan).where(ManagerLoan.club_id == club_id, ManagerLoan.status != "repaid")
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalar_one_or_none()


async def loan_due(db: AsyncSession, club: ManagerClub) -> int:
    """The debt the next season start collects (the last season of the term,
    or an overdue loan) — set aside in the window like the squad's wages."""
    loan = await open_loan(db, club.id)
    if loan is None or (loan.status == "active" and loan.seasons_left > 0):
        return 0
    return int(loan.debt)


async def _invested(db: AsyncSession, club_id: int, kinds: tuple[str, ...] = ("deposit", "venture")) -> int:
    """Money parked in deposits and the venture fund that has not come back."""
    return int((await db.execute(
        select(func.coalesce(func.sum(ManagerDeal.amount), 0)).where(
            ManagerDeal.club_id == club_id, ManagerDeal.kind.in_(kinds), ManagerDeal.status == "active",
        )
    )).scalar_one())


async def club_value(db: AsyncSession, club: ManagerClub, config, squad_value: Optional[int] = None, snap: Optional[dict] = None) -> dict:
    from app.services import manager_service as ms

    f = cfg(config)
    if squad_value is None:
        squad = await ms.squad_view(db, club, config)
        squad_value = sum(p.get("value", 0) for p in (*squad["xi"], *squad["bench"]))
    snap = snap or await ms.base_snapshot(db, club.owner_id, config)
    loan = await open_loan(db, club.id)
    parts = {
        "squad": int(squad_value), "budget": max(0, int(club.budget)), "invested": await _invested(db, club.id),
        "base": int(_num(f["value_per_base_level"])) * int(snap.get("level", 0)),
        "fans": int(_num(f["value_per_fan"])) * await fans_of(db, club),
        "titles": int(_num(f["value_per_title"])) * int(club.titles or 0),
        "debt": -int(loan.debt) if loan else 0,
    }
    return {"total": max(0, sum(parts.values())), "parts": parts}


def loan_limit(division: int, value: int, config) -> int:
    from app.services import manager_service as ms

    f = cfg(config)
    by_grant = grant_of(division, config) * _num(f["loan_grant_pct"]) / 100
    by_value = value * _num(f["loan_value_pct"]) / 100
    return ms._nice(max(0.0, min(by_grant, by_value)))


async def transfer_block(db: AsyncSession, club: ManagerClub) -> Optional[str]:
    from app.services import manager_exchange

    if reason := await manager_exchange.default_block(db, club):
        return reason
    loan = await open_loan(db, club.id)
    if loan is not None and loan.status == "overdue":
        from app.services import manager_service as ms

        return f"Кредит просрочен — трансферы закрыты, пока не погасишь долг {ms.money(loan.debt)}"
    return None


async def ensure_can_transfer(db: AsyncSession, club: ManagerClub) -> None:
    if reason := await transfer_block(db, club):
        raise ConflictError(reason)


# --- season flow (called by manager_service under the club locks) ---------------------------------

async def _deals(db: AsyncSession, club_id: int, key: Optional[str] = None, status: str = "active") -> list[ManagerDeal]:
    stmt = select(ManagerDeal).where(ManagerDeal.club_id == club_id, ManagerDeal.status == status)
    if key is not None:
        stmt = stmt.where(ManagerDeal.season_key == key)
    return list((await db.execute(stmt.order_by(ManagerDeal.id))).scalars().all())


async def farm_for(db: AsyncSession, club_id: int, key: str) -> Optional[dict]:
    deal = (await db.execute(
        select(ManagerDeal).where(ManagerDeal.club_id == club_id, ManagerDeal.kind == "farm", ManagerDeal.season_key == key)
    )).scalar_one_or_none()
    return dict(deal.data or {}) if deal is not None and deal.status in ("active", "done") else None


async def _process_loan(db: AsyncSession, club: ManagerClub, key: str, config) -> list[str]:
    from app.services import manager_service as ms

    loan = await open_loan(db, club.id, lock=True)
    if loan is None or loan.last_season == key:
        return []
    loan.last_season = key
    if loan.status == "active" and loan.seasons_left > 0:
        loan.debt += loan.debt * loan.rate_bp // 10_000
        loan.seasons_left -= 1
        return []
    if club.budget >= loan.debt:
        await book(db, club, "loan_repay", -loan.debt, key, ref=f"loan:{loan.id}:{key}", note="Кредит погашен")
        loan.debt = 0
        loan.status = "repaid"
        loan.closed_at = datetime.now(timezone.utc)
        return ["кредит погашен"]
    loan.debt += loan.debt * int(_num(cfg(config)["loan_penalty_pct"])) // 100
    loan.status = "overdue"
    await notify(
        db, club.owner_id, NotificationType.manager_event, f"«{club.name}»: кредит просрочен ⚠️",
        f"Не хватило бюджета. Штраф — долг теперь {ms.money(loan.debt)}, трансферы закрыты до погашения",
        related_object_type=ms.RELATED, related_object_id=club.id,
    )
    return ["кредит просрочен — трансферы закрыты"]


async def season_start(db: AsyncSession, club: ManagerClub, key: str, snap: dict, config) -> dict:
    """At the club's season start (after the grant, before wages): the
    shirt sponsor's money of this season, the loan; returns the season's frozen finance
    effects (stored in the league team)."""
    out: dict = {"notes": []}
    for deal in await _deals(db, club.id):
        keys = (deal.data or {}).get("keys") or [deal.season_key]
        if deal.kind == "kit" and key in keys:
            await book(db, club, "kit", deal.amount, key, ref=f"kit:{deal.id}:{key}", note=deal.option)
        if deal.season_key != key:
            continue
        data = deal.data or {}
        if deal.kind == "sponsor":
            out["sponsor_win"] = int(data.get("per_win", 0))
            out["sponsor_deal"] = deal.id
        elif deal.kind == "tour":
            out["fatigue_pct"] = _num(data.get("fatigue_pct"))
            out["fatigue_rounds"] = int(data.get("fatigue_rounds", 0))
        elif deal.kind == "tv":
            out["tv_sold"] = True
        elif deal.kind == "insurance":
            out["insured_pct"] = _num(data.get("cover_pct"))
    out["ticket_pct"] = int(club.ticket_pct or 100)
    out["notes"] += await _process_loan(db, club, key, config)
    out["fans"] = int(club.fans_bonus or 0)
    return out


def attendance_pct(ticket_pct: int, config) -> float:
    f = cfg(config)
    att = 100 - (int(ticket_pct) - 100) * _num(f["ticket_elasticity"])
    return max(_num(f["ticket_attendance_min_pct"]), min(_num(f["ticket_attendance_max_pct"]), att))


def ticket_factor(ticket_pct: int, config) -> int:
    """% of the base ticket money a home match brings: price × attendance."""
    return round(int(ticket_pct) * attendance_pct(ticket_pct, config) / 100)


def support_pct(ticket_pct: int, config) -> float:
    """% to every line of the home side: the crowd."""
    return round((attendance_pct(ticket_pct, config) - 100) * _num(cfg(config)["ticket_support_pct"]), 2)


def support_mods(mods: dict, finance: dict, config) -> dict:
    pct = support_pct(int((finance or {}).get("ticket_pct", 100)), config)
    if not pct:
        return mods
    return {line: mods.get(line, 0) + pct for line in ("GK", "DEF", "MID", "FWD")}


def insurance_premium(division: int, snap: dict, config) -> int:
    from app.services import manager_service as ms

    f = cfg(config)
    cut = min(50.0, _num(f["insurance_medical_cut_pct"]) * int(snap.get("medical", 0)))
    return ms._nice(grant_of(division, config) * _num(f["insurance_premium_pct"]) / 100 * (100 - cut) / 100)


def injury_chance(snap: dict, config) -> float:
    return _num(cfg(config)["injury_chance_pct"]) * (100 - min(90, int(snap.get("injury_pct", 0)))) / 100


async def set_tickets(db: AsyncSession, user: User, pct: int, now: Optional[datetime] = None) -> dict:
    """The ticket price for the coming season (in the window)."""
    config = await get_config(db)
    f = cfg(config)
    club = await _locked_club(db, user, config)
    await _window(db, club, now)
    low, high = int(_num(f["ticket_min_pct"])), int(_num(f["ticket_max_pct"]))
    pct = int(pct)
    if not low <= pct <= high:
        raise ConflictError(f"Цена билета — от {low}% до {high}% базовой")
    club.ticket_pct = pct
    await db.commit()
    return await view(db, user, now)


async def rating(db: AsyncSession, user: User, now: Optional[datetime] = None) -> dict:
    """«Лучший президент»: the season's profit (income − expenses of the
    report, financing aside) and the capital (budget + deposits and venture +
    shares at the price + bonds held − the loan − own bonds)."""
    from app.models.manager_club import ManagerBond, ManagerBondHolding, ManagerShare, ManagerStock
    from app.services import manager_service as ms, manager_shop

    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    size = int(_num(cfg(config)["rating_size"], 20)) or 20
    me = await ms._owned_club(db, user.id)
    week = ms.season_key(now)
    key = week if await db.get(ManagerSeason, week) is not None else shift_key(week, -1)
    kinds = [k for k, (group, _l) in KINDS.items() if group in ("income", "expense")]
    profit = dict((await db.execute(
        select(ManagerLedger.club_id, func.sum(ManagerLedger.amount))
        .where(ManagerLedger.season_key == key, ManagerLedger.kind.in_(kinds)).group_by(ManagerLedger.club_id)
    )).all())
    clubs = {c.id: c for c in (await db.execute(select(ManagerClub))).scalars().all()}
    capital = {cid: max(0, int(c.budget)) for cid, c in clubs.items()}
    for d in (await db.execute(select(ManagerDeal).where(ManagerDeal.status == "active", ManagerDeal.kind.in_(("deposit", "venture"))))).scalars():
        capital[d.club_id] = capital.get(d.club_id, 0) + int(d.amount)
    prices = dict((await db.execute(select(ManagerStock.club_id, ManagerStock.price))).all())
    for h in (await db.execute(select(ManagerShare).where(ManagerShare.shares > 0))).scalars():
        capital[h.holder_club_id] = capital.get(h.holder_club_id, 0) + h.shares * int(prices.get(h.club_id, 0))
    live = {b.id: b for b in (await db.execute(select(ManagerBond).where(ManagerBond.status.in_(("selling", "active", "default"))))).scalars()}
    for b in live.values():
        capital[b.club_id] = capital.get(b.club_id, 0) - b.units_sold * b.unit_eur
    for h in (await db.execute(select(ManagerBondHolding).where(ManagerBondHolding.units > 0))).scalars():
        b = live.get(h.bond_id)
        if b is not None:
            capital[h.holder_club_id] = capital.get(h.holder_club_id, 0) + h.units * b.unit_eur
    for loan in (await db.execute(select(ManagerLoan).where(ManagerLoan.status.in_(("active", "overdue"))))).scalars():
        capital[loan.club_id] = capital.get(loan.club_id, 0) - int(loan.debt)

    def table(scores: dict[int, int]) -> dict:
        ranked = sorted(((v, cid) for cid, v in scores.items() if cid in clubs), key=lambda x: (-x[0], x[1]))
        place = next((i + 1 for i, (_v, cid) in enumerate(ranked) if me and cid == me.id), None)
        rows = [{"place": i + 1, "club_id": cid, "name": clubs[cid].name, "division": clubs[cid].division,
                 "look": manager_shop.resolve_look(clubs[cid]), "score": int(v), "mine": bool(me and cid == me.id)}
                for i, (v, cid) in enumerate(ranked[:size])]
        return {"rows": rows, "my_place": place, "my_score": int(scores.get(me.id, 0)) if me else 0, "total": len(ranked)}

    return {"season_key": key, "profit": table({cid: int(v) for cid, v in profit.items()}), "capital": table(capital)}


def fatigue_mods(mods: dict, finance: dict, round_index: int) -> dict:
    pct = _num((finance or {}).get("fatigue_pct"))
    if pct <= 0 or round_index >= int((finance or {}).get("fatigue_rounds", 0)):
        return mods
    return {line: mods.get(line, 0) - pct for line in ("GK", "DEF", "MID", "FWD")}


async def match_money(db: AsyncSession, club: ManagerClub, finance: dict, key: str, won: bool, home: bool,
                      division: int, income: int, config) -> None:
    """A league match's money beyond the tickets of the stadium: the match
    income (unless the TV rights were sold), the fans on tours, the
    sponsor's win bonus."""
    finance = finance or {}
    if not finance.get("tv_sold"):
        await book(db, club, "match", income, key)
    if home and finance.get("fans"):
        fans_eur = int(finance["fans"]) * int(_num(cfg(config)["fan_ticket_eur"])) * _division_pct(division, config) // 100
        await book(db, club, "tickets", fans_eur * ticket_factor(int(finance.get("ticket_pct", 100)), config) // 100, key)
    if won and finance.get("sponsor_win"):
        await book(db, club, "sponsor", int(finance["sponsor_win"]), key, note="бонус за победу")


async def season_end(db: AsyncSession, club: ManagerClub, key: str, place: Optional[int], relegated: bool, config) -> None:
    """Settles the season's deals once the pyramid moves are known (the club
    is locked by manager_service._settle)."""
    from app.services import manager_service as ms

    now = datetime.now(timezone.utc)
    lines = []
    for deal in await _deals(db, club.id):
        data = deal.data or {}
        keys = data.get("keys") or [deal.season_key]
        if deal.kind == "kit":
            if keys[-1] == key:
                deal.status, deal.settled_at = "done", now
            continue
        if deal.season_key != key:
            continue
        payout = 0
        if deal.kind == "sponsor":
            places = data.get("places") or []
            if relegated:
                payout = int(data.get("relegated", 0))
            elif place is not None and place <= len(places):
                payout = int(places[place - 1])
            else:
                payout = int(data.get("rest", 0))
            if payout:
                await book(db, club, "sponsor", payout, key, ref=f"sponsor:{deal.id}", note="итог сезона")
                lines.append(f"спонсор {ms.money(payout)}")
        elif deal.kind == "deposit":
            payout = deal.amount + deal.amount * int(data.get("rate_bp", 0)) // 10_000
            await book(db, club, "deposit_in", payout, key, ref=f"deposit:{deal.id}")
            lines.append(f"депозит {ms.money(payout)}")
        elif deal.kind == "venture":
            rng = random.Random(f"venture:{deal.id}:{deal.season_key}")
            won = rng.random() * 100 < _num(data.get("win_pct"))
            payout = int(deal.amount * _num(data.get("multiplier"))) if won else 0
            if payout:
                await book(db, club, "venture_in", payout, key, ref=f"venture:{deal.id}")
            lines.append(f"венчур {'×' + str(data.get('multiplier')) if won else 'прогорел'}")
            deal.status = "done" if won else "lost"
        deal.result = payout
        if deal.status == "active":
            deal.status = "done"
        deal.settled_at = now
    # The crowd of the season: cheap tickets win fans, dear ones lose them.
    att = attendance_pct(int(club.ticket_pct or 100), config)
    delta = round((att - 100) * _num(cfg(config)["ticket_fans_per_pct"]))
    if delta:
        club.fans_bonus = max(0, int(club.fans_bonus or 0) + delta)
        lines.append(f"болельщиков {'+' if delta > 0 else ''}{delta}")
    from app.services import manager_exchange

    lines += await manager_exchange.season_end(db, club, key, config)
    if lines:
        await notify(
            db, club.owner_id, NotificationType.manager_event, f"«{club.name}»: финансы сезона 💼",
            ", ".join(lines).capitalize(), related_object_type=ms.RELATED, related_object_id=club.id,
        )


# --- actions -----------------------------------------------------------------------------------

async def _locked_club(db: AsyncSession, user: User, config) -> ManagerClub:
    from app.services import manager_service as ms

    ms._enabled(config)
    if not cfg(config)["enabled"]:
        raise ConflictError("«Кабинет президента» сейчас закрыт")
    club = await ms._owned_club(db, user.id, lock=True)
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    return club


async def window_open(db: AsyncSession, club: ManagerClub, now: Optional[datetime] = None) -> bool:
    """The office keeps the transfer window: shut while the club plays and
    while this week's season runs for anybody (a club founded too late too)."""
    from app.services import manager_service as ms

    return not await ms.is_playing(db, club) and await ms.window_open(db, now)


async def _window(db: AsyncSession, club: ManagerClub, now: Optional[datetime] = None) -> None:
    if not await window_open(db, club, now):
        raise ConflictError("Идёт сезон — сделки заключаются в межсезонье")


async def _add_deal(db: AsyncSession, deal: ManagerDeal) -> None:
    try:
        async with db.begin_nested():
            db.add(deal)
    except IntegrityError:
        raise ConflictError("На этот сезон такая сделка уже заключена")


async def _taken(db: AsyncSession, club_id: int, kind: str, key: str) -> bool:
    return (await db.execute(
        select(ManagerDeal.id).where(ManagerDeal.club_id == club_id, ManagerDeal.kind == kind, ManagerDeal.season_key == key)
    )).first() is not None


async def kit_covering(db: AsyncSession, club_id: int, key: str) -> Optional[ManagerDeal]:
    """The shirt sponsor whose contract covers this season."""
    for deal in await _deals(db, club_id):
        if deal.kind == "kit" and key in ((deal.data or {}).get("keys") or [deal.season_key]):
            return deal
    return None


def _amount(value, low: int, high: int, what: str) -> int:
    from app.services import manager_service as ms

    amount = int(value or 0)
    if high < low:
        raise ConflictError(f"{what}: сейчас недоступно — нужно хотя бы {ms.money(low)}")
    if not low <= amount <= high:
        raise ConflictError(f"{what}: от {ms.money(low)} до {ms.money(high)}")
    return amount


async def sign(db: AsyncSession, user: User, kind: str, option: Optional[str] = None, seasons: int = 1,
               amount: Optional[int] = None, now: Optional[datetime] = None) -> dict:
    """Signs a deal for the coming season."""
    from app.services import manager_service as ms

    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    if kind not in DEAL_KINDS:
        raise NotFoundError("Такой сделки нет")
    club = await _locked_club(db, user, config)
    await _window(db, club, now)
    key = await upcoming_key(db, now)
    if await _taken(db, club.id, kind, key):
        raise ConflictError("На этот сезон такая сделка уже заключена")
    f = cfg(config)
    snap = await ms.base_snapshot(db, club.owner_id, config)
    grant = grant_of(club.division, config)
    # Spending deals use the budget above what the next season start takes (wages, a loan due).
    free = max(0, club.budget - await ms.start_bill(db, club, config, snap))
    deal = ManagerDeal(club_id=club.id, kind=kind, season_key=key, seasons=1, option=option, data={"keys": [key]})
    if kind == "sponsor":
        terms = next((s for s in sponsor_terms(club, snap, config) if s["code"] == option), None)
        if terms is None:
            raise NotFoundError("Такого спонсора нет")
        deal.option = terms["code"]
        deal.amount = terms["upfront"]
        deal.data = {"keys": [key], "brand": terms["brand"], "name": terms["name"], "per_win": terms["per_win"],
                     "places": terms["places"], "rest": terms["rest"], "relegated": terms["relegated"]}
        await _add_deal(db, deal)
        await book(db, club, "sponsor", terms["upfront"], key, ref=f"sponsor_up:{deal.id}", note=terms["brand"])
    elif kind == "kit":
        seasons = int(seasons or 1)
        if not 1 <= seasons <= int(_num(f["kit_seasons_max"], 3)):
            raise ConflictError(f"Контракт — на 1–{int(_num(f['kit_seasons_max'], 3))} сезона")
        brands = [str(b) for b in f["kit_brands"]]
        if option not in brands:
            raise NotFoundError("Такого спонсора нет")
        if await kit_covering(db, club.id, key):
            raise ConflictError("Спонсор на форме уже есть на этот сезон")
        price = kit_price(club.division, snap, seasons, config)
        deal.seasons, deal.amount = seasons, price
        deal.data = {"keys": keys_from(key, seasons), "shop": _lvl(snap, "shop")}
        await _add_deal(db, deal)
        await book(db, club, "kit", price, key, ref=f"kit:{deal.id}:{key}", note=option)
    elif kind == "tour":
        terms = next((t for t in tour_terms(club.division, snap, config) if t["code"] == option), None)
        if terms is None:
            raise NotFoundError("Такого турне нет")
        if free < terms["cost"]:
            raise ConflictError(f"На турне нужно {ms.money(terms['cost'])}, свободно {ms.money(free)} (зарплаты состава отложены)")
        deal.amount = terms["cost"]
        deal.result = terms["revenue"]
        deal.data = {"keys": [key], **{k: terms[k] for k in ("name", "revenue", "cost", "fans", "fatigue_pct", "fatigue_rounds")}}
        await _add_deal(db, deal)
        await book(db, club, "tour_cost", -terms["cost"], key, ref=f"tour_cost:{deal.id}", note=terms["name"])
        await book(db, club, "tour", terms["revenue"], key, ref=f"tour:{deal.id}", note=terms["name"])
        club.fans_bonus = int(club.fans_bonus or 0) + terms["fans"]
    elif kind == "tv":
        estimate = tv_estimate(club.division, config)
        discount = tv_discount_pct(snap, config)
        advance = ms._nice(estimate * (100 - discount) / 100)
        deal.amount = advance
        deal.data = {"keys": [key], "estimate": estimate, "discount_pct": discount}
        await _add_deal(db, deal)
        await book(db, club, "tv", advance, key, ref=f"tv:{deal.id}")
    elif kind == "deposit":
        if await open_loan(db, club.id):
            raise ConflictError("Банк не открывает депозит, пока у клуба есть кредит")
        high = free * int(_num(f["deposit_max_budget_pct"])) // 100
        stake = _amount(amount, int(_num(f["deposit_min_eur"])), high, "Депозит")
        deal.amount = stake
        deal.data = {"keys": [key], "rate_bp": deposit_rate_bp(snap, config)}
        await _add_deal(db, deal)
        await book(db, club, "deposit_out", -stake, key, ref=f"deposit_out:{deal.id}")
    elif kind == "venture":
        high = free * int(_num(f["venture_max_budget_pct"])) // 100
        stake = _amount(amount, int(_num(f["venture_min_eur"])), high, "Венчурный фонд")
        deal.amount = stake
        deal.data = {"keys": [key], "win_pct": _num(f["venture_win_pct"]), "multiplier": _num(f["venture_multiplier"])}
        await _add_deal(db, deal)
        await book(db, club, "venture_out", -stake, key, ref=f"venture_out:{deal.id}")
    elif kind == "insurance":
        premium = insurance_premium(club.division, snap, config)
        if free < premium:
            raise ConflictError(f"Страховка стоит {ms.money(premium)}, свободно {ms.money(free)} (зарплаты состава отложены)")
        deal.amount = premium
        deal.data = {"keys": [key], "cover_pct": _num(f["insurance_cover_pct"])}
        await _add_deal(db, deal)
        await book(db, club, "insurance", -premium, key, ref=f"insurance:{deal.id}")
    elif kind == "farm":
        terms = farm_terms(club.division, snap, config)
        if free < terms["fee"]:
            raise ConflictError(f"Фарм-клуб стоит {ms.money(terms['fee'])}, свободно {ms.money(free)} (зарплаты состава отложены)")
        deal.amount = terms["fee"]
        deal.data = {"keys": [key], "loan_cut_pct": terms["loan_cut_pct"], "kid_bonus": terms["kid_bonus"]}
        await _add_deal(db, deal)
        await book(db, club, "farm", -terms["fee"], key, ref=f"farm:{deal.id}")
    await db.commit()
    return await view(db, user, now)


async def take_loan(db: AsyncSession, user: User, amount: int, seasons: int, now: Optional[datetime] = None) -> dict:
    from app.services import manager_service as ms

    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    club = await _locked_club(db, user, config)
    await _window(db, club, now)
    f = cfg(config)
    seasons = int(seasons or 1)
    if not 1 <= seasons <= int(_num(f["loan_seasons_max"], 3)):
        raise ConflictError(f"Кредит — на 1–{int(_num(f['loan_seasons_max'], 3))} сезона")
    if await open_loan(db, club.id):
        raise ConflictError("Сначала погаси текущий кредит")
    if await _invested(db, club.id, ("deposit",)):
        raise ConflictError("Пока деньги на депозите, банк кредит не даст")
    snap = await ms.base_snapshot(db, club.owner_id, config)
    value = (await club_value(db, club, config, snap=snap))["total"]
    principal = _amount(amount, int(_num(f["loan_min_eur"])), loan_limit(club.division, value, config), "Кредит")
    try:
        async with db.begin_nested():
            loan = ManagerLoan(club_id=club.id, principal=principal, debt=principal, rate_bp=loan_rate_bp(snap, config),
                               seasons_total=seasons, seasons_left=seasons, status="active")
            db.add(loan)
    except IntegrityError:
        raise ConflictError("Сначала погаси текущий кредит")
    await db.flush()
    key = await upcoming_key(db, now)
    await book(db, club, "loan_in", principal, key, ref=f"loan_in:{loan.id}")
    await db.commit()
    return await view(db, user, now)


async def repay_loan(db: AsyncSession, user: User, amount: Optional[int] = None, now: Optional[datetime] = None) -> dict:
    """Any part of the debt, any time; an overdue loan opens transfers again
    when it is fully repaid."""
    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    club = await _locked_club(db, user, config)
    loan = await open_loan(db, club.id, lock=True)
    if loan is None:
        raise NotFoundError("Кредита нет")
    pay = loan.debt if amount is None else max(0, min(int(amount), loan.debt))
    if pay <= 0:
        raise ConflictError("Сумма погашения — больше нуля")
    if pay > club.budget:
        raise ConflictError("В бюджете столько нет")
    await book(db, club, "loan_repay", -pay, await club_key(db, club, now))
    loan.debt -= pay
    if loan.debt <= 0:
        loan.status = "repaid"
        loan.closed_at = now
    await db.commit()
    return await view(db, user, now)


# --- view --------------------------------------------------------------------------------------

async def report(db: AsyncSession, club: ManagerClub) -> list[dict]:
    rows = (await db.execute(
        select(ManagerLedger.season_key, ManagerLedger.kind, func.sum(ManagerLedger.amount))
        .where(ManagerLedger.club_id == club.id).group_by(ManagerLedger.season_key, ManagerLedger.kind)
    )).all()
    seasons: dict[str, dict] = {}
    for key, kind, total in rows:
        group, label = KINDS.get(kind, ("finance", kind))
        s = seasons.setdefault(key, {"key": key, "income": 0, "expense": 0, "finance": 0, "lines": []})
        s[group] += int(total)
        s["lines"].append({"kind": kind, "label": label, "group": group, "amount": int(total)})
    out = sorted(seasons.values(), key=lambda s: s["key"], reverse=True)[:REPORT_SEASONS]
    for s in out:
        s["lines"].sort(key=lambda line: (("income", "expense", "finance").index(line["group"]), -abs(line["amount"])))
        s["profit"] = s["income"] + s["expense"]
    return out


def _deal_out(deal: ManagerDeal) -> dict:
    return {"id": deal.id, "kind": deal.kind, "season_key": deal.season_key, "seasons": deal.seasons, "option": deal.option,
            "amount": deal.amount, "result": deal.result, "status": deal.status, "data": deal.data or {}}


async def view(db: AsyncSession, user: User, now: Optional[datetime] = None) -> dict:
    from app.services import manager_service as ms, manager_shop

    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    f = cfg(config)
    club = await ms._owned_club(db, user.id)
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    snap = await ms.base_snapshot(db, club.owner_id, config)
    value = await club_value(db, club, config, snap=snap)
    key = await upcoming_key(db, now)
    playing = not await window_open(db, club, now)
    current = await club_key(db, club, now)
    deals = list((await db.execute(
        select(ManagerDeal).where(ManagerDeal.club_id == club.id).order_by(ManagerDeal.id.desc()).limit(40)
    )).scalars().all())
    taken = {d.kind for d in deals if d.season_key == key}
    kit_now = await kit_covering(db, club.id, key)
    kit_worn = await kit_covering(db, club.id, current)
    loan = await open_loan(db, club.id)
    division = club.division
    grant = grant_of(division, config)
    estimate = tv_estimate(division, config)
    discount = tv_discount_pct(snap, config)
    free = max(0, club.budget - await ms.start_bill(db, club, config, snap))
    return {
        "enabled": bool(f["enabled"]),
        "club_id": club.id, "name": club.name, "look": manager_shop.resolve_look(club), "division": division, "budget": club.budget, "free_budget": free, "grant": grant,
        "window_open": not playing, "season_key": key, "current_key": current,
        "value": value, "fans": await fans_of(db, club),
        "levels": {code: _lvl(snap, code) for code in ("stadium", "hotel", "media", "marketing", "accounting", "training", "shop")},
        "report": await report(db, club),
        "sponsors": {"taken": "sponsor" in taken, "offers": sponsor_terms(club, snap, config),
                     "marketing_pct": _num(f["sponsor_marketing_pct_per_level"]) * _lvl(snap, "marketing")},
        "loan": {
            "open": {"id": loan.id, "principal": loan.principal, "debt": loan.debt, "rate_pct": loan.rate_bp / 100,
                     "seasons_total": loan.seasons_total, "seasons_left": loan.seasons_left, "status": loan.status} if loan else None,
            "limit": loan_limit(division, value["total"], config), "min": int(_num(f["loan_min_eur"])),
            "rate_pct": loan_rate_bp(snap, config) / 100, "base_rate_pct": _num(f["loan_rate_pct"]),
            "seasons_max": int(_num(f["loan_seasons_max"], 3)), "penalty_pct": _num(f["loan_penalty_pct"]),
        },
        "offers": {
            "kit": {"taken": kit_now is not None, "shop": _lvl(snap, "shop"), "brands": [str(b) for b in f["kit_brands"]],
                    "worn": (kit_worn or kit_now).option if (kit_worn or kit_now) else None,
                    "prices": [kit_price(division, snap, n, config) for n in range(1, int(_num(f["kit_seasons_max"], 3)) + 1)]},
            "tour": {"taken": "tour" in taken, "options": tour_terms(division, snap, config),
                     "hotel_cut_pct": min(90.0, _num(f["tour_hotel_cut_per_level"]) * _lvl(snap, "hotel")),
                     "media_fans_pct": _num(f["tour_media_fans_pct_per_level"]) * _lvl(snap, "media")},
            "tv": {"taken": "tv" in taken, "estimate": estimate, "discount_pct": discount,
                   "advance": ms._nice(estimate * (100 - discount) / 100)},
            "deposit": {"taken": "deposit" in taken, "rate_pct": deposit_rate_bp(snap, config) / 100,
                        "min": int(_num(f["deposit_min_eur"])), "max": free * int(_num(f["deposit_max_budget_pct"])) // 100,
                        "blocked": loan is not None},
            "venture": {"taken": "venture" in taken, "win_pct": _num(f["venture_win_pct"]), "multiplier": _num(f["venture_multiplier"]),
                        "min": int(_num(f["venture_min_eur"])), "max": free * int(_num(f["venture_max_budget_pct"])) // 100,
                        "max_pct": _num(f["venture_max_budget_pct"])},
            "farm": {"taken": "farm" in taken, **farm_terms(division, snap, config)},
            "insurance": {"taken": "insurance" in taken, "premium": insurance_premium(division, snap, config),
                          "cover_pct": _num(f["insurance_cover_pct"]), "medical": int(snap.get("medical", 0)),
                          "chance_pct": round(injury_chance(snap, config), 2), "treatment_pct": _num(f["injury_treatment_pct"]),
                          "rounds": [int(_num(f["injury_rounds_min"])), int(_num(f["injury_rounds_max"]))]},
        },
        "tickets": {
            "pct": int(club.ticket_pct or 100), "min": int(_num(f["ticket_min_pct"])), "max": int(_num(f["ticket_max_pct"])),
            "elasticity": _num(f["ticket_elasticity"]), "attendance_min": _num(f["ticket_attendance_min_pct"]),
            "attendance_max": _num(f["ticket_attendance_max_pct"]), "support_per_pct": _num(f["ticket_support_pct"]),
            "fans_per_pct": _num(f["ticket_fans_per_pct"]),
            "base_per_match": ms.ticket_income(division, snap, config), "capacity": int(snap.get("capacity", 0)),
        },
        "injuries": await ms.injuries_of(db, club),
        "deals": [_deal_out(d) for d in deals],
    }
