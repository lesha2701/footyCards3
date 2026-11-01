"""«Кабинет президента», phase 2: the club exchange and bonds. Club euros
only (`ManagerClub.budget`), never coins; every move goes through
manager_finance.book (the ledger) under the club row locks.

Shares: every club has `shares_total` (1000). Its president may float up to
`ipo_max_pct` of them (IPO): the unsold ones sit on the exchange and their
buyers pay the club (up to `ipo_season_cap_pct` of G a season). Holders sell
back to the exchange (the `pool`); a pool share bought again pays nobody —
the exchange is the counterparty, `exchange_fee_pct` of every trade is
burnt. One club holds at most `holder_max_pct` of another; nobody trades
his own club except the buyback.

The price is not a market price: it is the club value without its budget
(squad, «Клубная база», fans, titles, minus the debt) per share, set at the
listing and at each season start, times the form — points a game this
season and in the last 5 games — recomputed after every round
(`after_round`). Trading can't move it, so pumping a price with other
accounts does nothing; trades of a club whose round is due wait for the
round (`_fresh`). Buyers pass the trade anti-farming rules
(`trade_guard_service`).

Dividends: at the season end `dividend_pct` of the season's profit (income
− expenses of the report) is paid per share to the holders.

Buyback: unsold IPO shares are withdrawn free, pool shares cost the price,
then holders are bought out pro rata at the price + `buyback_premium_pct`.

Bonds: a club borrows from other clubs — `units_total` units of
`bond_unit_eur` at a coupon it picks within the admin range, 1–3 seasons,
sold in its window for the coming season (unsold units are dropped at its
season start). A coupon at every season end, the principal at the last one;
not enough budget → default: the holders wait, the club can't transfer until
it repays (`repay_bond`). The club owes at most min(G × bond_grant_pct,
value × bond_value_pct) in bonds.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import NotificationType
from app.models.manager_club import (
    ManagerBond,
    ManagerBondHolding,
    ManagerClub,
    ManagerLeague,
    ManagerLedger,
    ManagerShare,
    ManagerStock,
    ManagerTrade,
)
from app.models.user import User
from app.services import manager_finance as finance, trade_guard_service
from app.services.game_config_service import get_config
from app.services.notification_service import notify

HISTORY_KEEP = 40
TAPE_SHOWN = 30


def _f(config) -> dict:
    return finance.cfg(config)


def _int(config, key: str) -> int:
    return int(finance._num(_f(config)[key]))


def _fee(amount: int, config) -> int:
    return amount * _int(config, "exchange_fee_pct") // 100


# --- price ---------------------------------------------------------------------------------------

async def base_price(db: AsyncSession, club: ManagerClub, config, shares_total: int) -> int:
    """The club value without its budget (and money parked in deposits) per share."""
    value = await finance.club_value(db, club, config)
    parts = value["parts"]
    worth = max(0, value["total"] - parts["budget"] - parts["invested"])
    return max(1, worth // max(1, shares_total))


def form_of(state: dict, team_index: int) -> tuple[float, float, int]:
    """Points a game this season and in the last 5 games, games played."""
    points: list[int] = []
    for round_results in state.get("results", []):
        for m in round_results:
            for me, gf, ga in ((m["home"], m["hs"], m["as"]), (m["away"], m["as"], m["hs"])):
                if me == team_index:
                    points.append(3 if gf > ga else 1 if gf == ga else 0)
    if not points:
        return 1.4, 1.4, 0
    last = points[-5:]
    return sum(points) / len(points), sum(last) / len(last), len(points)


def price_from(base: int, ppg: float, form: float, config) -> int:
    f = _f(config)
    pct = 100 + (ppg - 1.4) * finance._num(f["price_ppg_pct"]) + (form - 1.4) * finance._num(f["price_form_pct"])
    pct = min(finance._num(f["price_max_pct"]), max(finance._num(f["price_min_pct"]), pct))
    return max(1, int(base * pct / 100))


def _mark(stock: ManagerStock, key: str, round_no: int) -> None:
    point = {"k": key, "r": round_no, "p": int(stock.price)}
    history = [h for h in (stock.history or []) if not (h.get("k") == key and h.get("r") == round_no)]
    stock.history = (history + [point])[-HISTORY_KEEP:]
    stock.updated_at = datetime.now(timezone.utc)


async def _stock(db: AsyncSession, club_id: int, lock: bool = False) -> Optional[ManagerStock]:
    stmt = select(ManagerStock).where(ManagerStock.club_id == club_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalar_one_or_none()


async def season_open(db: AsyncSession, club: ManagerClub, key: str, config) -> None:
    """At the club's season start (club locked): a listed club's base is
    re-valued and the price starts from it."""
    stock = await _stock(db, club.id, lock=True)
    if stock is None or stock.floated <= 0:
        return
    stock.base = await base_price(db, club, config, stock.shares_total)
    stock.price = stock.base
    _mark(stock, key, 0)


async def after_round(db: AsyncSession, league: ManagerLeague, state: dict) -> None:
    """After a round (the league's clubs are locked): listed clubs' prices
    follow the form."""
    config = await get_config(db)
    ids = {t["club_id"]: t["index"] for t in state.get("teams", []) if t.get("club_id")}
    if not ids:
        return
    stocks = (await db.execute(
        select(ManagerStock).where(ManagerStock.club_id.in_(list(ids)), ManagerStock.floated > 0)
        .with_for_update().execution_options(populate_existing=True)
    )).scalars().all()
    for stock in stocks:
        ppg, form, played = form_of(state, ids[stock.club_id])
        stock.price = price_from(stock.base, ppg, form, config)
        _mark(stock, league.season_key, played)


# --- dividends and bonds at the season end -------------------------------------------------------

async def season_profit(db: AsyncSession, club_id: int, key: str) -> int:
    kinds = [k for k, (group, _label) in finance.KINDS.items() if group in ("income", "expense") and k != "dividend_out"]
    return int((await db.execute(
        select(func.coalesce(func.sum(ManagerLedger.amount), 0)).where(
            ManagerLedger.club_id == club_id, ManagerLedger.season_key == key, ManagerLedger.kind.in_(kinds),
        )
    )).scalar_one())


async def _club(db: AsyncSession, club_id: int) -> Optional[ManagerClub]:
    """A club of the settle (every club row is already locked there)."""
    return await db.get(ManagerClub, club_id)


async def season_end(db: AsyncSession, club: ManagerClub, key: str, config) -> list[str]:
    """Called from manager_finance.season_end for every club (all locked):
    dividends to the holders, coupons and principal of the club's bonds."""
    from app.services import manager_service as ms

    lines: list[str] = []
    stock = await _stock(db, club.id, lock=True)
    profit = await season_profit(db, club.id, key)
    if stock is not None and profit > 0:
        per_share = profit * _int(config, "dividend_pct") // 100 // max(1, stock.shares_total)
        holders = (await db.execute(
            select(ManagerShare).where(ManagerShare.club_id == club.id, ManagerShare.shares > 0)
            .with_for_update().execution_options(populate_existing=True)
        )).scalars().all()
        total = 0
        for h in holders:
            amount = min(per_share * h.shares, max(0, club.budget))
            holder = await _club(db, h.holder_club_id)
            if amount <= 0 or holder is None:
                continue
            if await finance.book(db, club, "dividend_out", -amount, key, ref=f"div_out:{h.id}:{key}", note=holder.name):
                await finance.book(db, holder, "dividend_in", amount, key, ref=f"div_in:{h.id}:{key}", note=club.name)
                h.dividends += amount
                total += amount
        if total:
            stock.dividends_paid += total
            lines.append(f"дивиденды акционерам {ms.money(total)}")
    for bond in (await db.execute(
        select(ManagerBond).where(ManagerBond.club_id == club.id, ManagerBond.status.in_(("active", "default")))
        .with_for_update().execution_options(populate_existing=True)
    )).scalars().all():
        if bond.last_season == key:
            continue
        lines += await _pay_bond(db, club, bond, key)
    return lines


async def _holdings(db: AsyncSession, bond_id: int) -> list[ManagerBondHolding]:
    return list((await db.execute(
        select(ManagerBondHolding).where(ManagerBondHolding.bond_id == bond_id, ManagerBondHolding.units > 0)
        .with_for_update().execution_options(populate_existing=True)
    )).scalars().all())


def _coupon(bond: ManagerBond, units: int) -> int:
    return units * bond.unit_eur * bond.rate_bp // 10_000


async def bond_due(bond: ManagerBond, final: Optional[bool] = None) -> int:
    """What the club owes now: the coupon (in default: the principal too)."""
    final = bond.status == "default" or bond.seasons_left <= 1 if final is None else final
    return _coupon(bond, bond.units_sold) + (bond.units_sold * bond.unit_eur if final else 0)


async def _pay_bond(db: AsyncSession, club: ManagerClub, bond: ManagerBond, key: str) -> list[str]:
    from app.services import manager_service as ms

    bond.last_season = key
    defaulted = bond.status == "default"
    final = defaulted or bond.seasons_left <= 1
    due = await bond_due(bond, final)
    if club.budget < due:
        if not defaulted:
            bond.status = "default"
            bond.seasons_left = 0
            await notify(
                db, club.owner_id, NotificationType.manager_event, f"«{club.name}»: дефолт по облигациям ⚠️",
                f"Не хватило {ms.money(due)} — трансферы закрыты, пока не погасишь облигации",
                related_object_type=ms.RELATED, related_object_id=club.id,
            )
        return ["дефолт по облигациям — трансферы закрыты"]
    await _settle_bond(db, club, bond, key, final)
    return ["облигации погашены" if final else f"купон по облигациям {ms.money(_coupon(bond, bond.units_sold))}"]


async def _settle_bond(db: AsyncSession, club: ManagerClub, bond: ManagerBond, key: str, final: bool) -> None:
    for h in await _holdings(db, bond.id):
        holder = await db.get(ManagerClub, h.holder_club_id)
        if holder is None:
            continue
        coupon = _coupon(bond, h.units) if bond.status != "default" or bond.seasons_left > 0 else 0
        principal = h.units * bond.unit_eur if final else 0
        if coupon and await finance.book(db, club, "coupon_out", -coupon, key, ref=f"coupon_out:{h.id}:{key}", note=holder.name):
            await finance.book(db, holder, "coupon_in", coupon, key, ref=f"coupon_in:{h.id}:{key}", note=club.name)
            h.received += coupon
        if principal and await finance.book(db, club, "bond_repay", -principal, key, ref=f"bond_repay:{h.id}", note=holder.name):
            await finance.book(db, holder, "bond_back", principal, key, ref=f"bond_back:{h.id}", note=club.name)
            h.received += principal
    if final:
        bond.status = "repaid"
        bond.seasons_left = 0
        bond.closed_at = datetime.now(timezone.utc)
    else:
        bond.seasons_left -= 1


async def bonds_start(db: AsyncSession, club: ManagerClub, key: str) -> None:
    """At the club's season start: its bonds sold for this season stop selling."""
    for bond in (await db.execute(
        select(ManagerBond).where(ManagerBond.club_id == club.id, ManagerBond.status == "selling", ManagerBond.season_key <= key)
        .with_for_update().execution_options(populate_existing=True)
    )).scalars().all():
        if bond.units_sold > 0:
            bond.status = "active"
            bond.units_total = bond.units_sold
        else:
            bond.status = "repaid"
            bond.closed_at = datetime.now(timezone.utc)


async def bond_debt(db: AsyncSession, club_id: int) -> int:
    rows = (await db.execute(
        select(ManagerBond).where(ManagerBond.club_id == club_id, ManagerBond.status.in_(("selling", "active", "default")))
    )).scalars().all()
    return sum(b.units_total * b.unit_eur if b.status == "selling" else b.units_sold * b.unit_eur for b in rows)


async def default_block(db: AsyncSession, club: ManagerClub) -> Optional[str]:
    from app.services import manager_service as ms

    bond = (await db.execute(
        select(ManagerBond).where(ManagerBond.club_id == club.id, ManagerBond.status == "default").limit(1)
    )).scalar_one_or_none()
    if bond is None:
        return None
    return f"Дефолт по облигациям — трансферы закрыты, пока не погасишь {ms.money(await bond_due(bond))}"


# --- actions -------------------------------------------------------------------------------------

async def _me(db: AsyncSession, user: User, config) -> ManagerClub:
    club = await finance._locked_club(db, user, config)
    if not _f(config)["exchange_enabled"]:
        raise ConflictError("Биржа сейчас закрыта")
    return club


async def _fresh(db: AsyncSession, club: ManagerClub, now: datetime) -> None:
    """A club's due round is played first: nobody trades on a result the
    price does not know yet."""
    from app.services import manager_service as ms

    if club.league_id and await ms.is_playing(db, club):
        await ms.resolve_league(db, club.league_id, now)


async def _lock_pair(db: AsyncSession, a: int, b: int) -> dict[int, ManagerClub]:
    from app.services import manager_service as ms

    return await ms._lock_clubs(db, [a, b])


async def _holding(db: AsyncSession, club_id: int, holder_id: int) -> ManagerShare:
    row = (await db.execute(
        select(ManagerShare).where(ManagerShare.club_id == club_id, ManagerShare.holder_club_id == holder_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if row is not None:
        return row
    try:
        async with db.begin_nested():
            row = ManagerShare(club_id=club_id, holder_club_id=holder_id, shares=0, cost=0, dividends=0)
            db.add(row)
    except IntegrityError:
        return await _holding(db, club_id, holder_id)
    return row


def _tape(db: AsyncSession, club_id: int, holder_id: Optional[int], side: str, shares: int, price: int, fee: int) -> None:
    db.add(ManagerTrade(club_id=club_id, holder_club_id=holder_id, side=side, shares=shares, price=price, fee=fee))


async def _free(db: AsyncSession, club: ManagerClub, config) -> int:
    from app.services import manager_service as ms

    return max(0, club.budget - await ms.start_bill(db, club, config))


async def ipo(db: AsyncSession, user: User, shares: int, now: Optional[datetime] = None) -> dict:
    """Float `shares` more (up to ipo_max_pct of all) — in the window."""
    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    club = await _me(db, user, config)
    await finance._window(db, club)
    stock = await _stock(db, club.id, lock=True)
    if stock is None:
        try:
            async with db.begin_nested():
                stock = ManagerStock(club_id=club.id, shares_total=_int(config, "shares_total") or 1000, history=[])
                db.add(stock)
        except IntegrityError:
            stock = await _stock(db, club.id, lock=True)
    cap = stock.shares_total * _int(config, "ipo_max_pct") // 100
    shares = int(shares)
    if shares <= 0 or stock.floated + shares > cap:
        raise ConflictError(f"На биржу можно вывести не больше {cap} акций из {stock.shares_total} — уже {stock.floated}")
    if stock.floated == 0:
        stock.base = await base_price(db, club, config, stock.shares_total)
        stock.price = stock.base
        _mark(stock, await finance.upcoming_key(db, now), 0)
    stock.floated += shares
    stock.unsold += shares
    _tape(db, club.id, None, "ipo", shares, stock.price, 0)
    await db.commit()
    return await view(db, user, now)


async def buy(db: AsyncSession, user: User, club_id: int, shares: int, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    me = await _me(db, user, config)
    if club_id == me.id:
        raise ConflictError("Свои акции покупаются только выкупом")
    await trade_guard_service.ensure_can_give(db, user, config, own=True)
    issuer = await db.get(ManagerClub, club_id)
    if issuer is None:
        raise NotFoundError("Клуб не найден")
    await _fresh(db, issuer, now)
    clubs = await _lock_pair(db, me.id, club_id)
    me, issuer = clubs[me.id], clubs[club_id]
    stock = await _stock(db, club_id, lock=True)
    shares = int(shares)
    if stock is None or stock.floated <= 0:
        raise NotFoundError("Этот клуб не на бирже")
    if shares <= 0 or shares > stock.unsold + stock.pool:
        raise ConflictError(f"На бирже {stock.unsold + stock.pool} акций «{issuer.name}»")
    holding = await _holding(db, club_id, me.id)
    cap = stock.shares_total * _int(config, "holder_max_pct") // 100
    if holding.shares + shares > cap:
        raise ConflictError(f"В одних руках — не больше {cap} акций клуба ({_int(config, 'holder_max_pct')}%), у тебя {holding.shares}")
    from_pool = min(shares, stock.pool)
    primary = shares - from_pool
    key_me, key_issuer = await finance.club_key(db, me, now), await finance.club_key(db, issuer, now)
    if primary:
        cap_eur = finance.grant_of(issuer.division, config) * _int(config, "ipo_season_cap_pct") // 100
        raised = stock.raised_eur if stock.raised_season == key_issuer else 0
        if raised + primary * stock.price > cap_eur:
            raise ConflictError(f"«{issuer.name}» уже привлёк максимум за сезон через IPO — попробуй в следующем сезоне")
    cost = shares * stock.price
    fee = _fee(cost, config)
    free = await _free(db, me, config)
    if cost + fee > free:
        from app.services import manager_service as ms

        raise ConflictError(f"Нужно {ms.money(cost + fee)} с комиссией, свободно {ms.money(free)}")
    await finance.book(db, me, "shares_buy", -(cost + fee), key_me, note=f"{shares} акц. «{issuer.name}»")
    if primary:
        await finance.book(db, issuer, "ipo", primary * stock.price, key_issuer, note=f"{primary} акц. → «{me.name}»")
        stock.raised_eur = (stock.raised_eur if stock.raised_season == key_issuer else 0) + primary * stock.price
        stock.raised_season = key_issuer
    stock.pool -= from_pool
    stock.unsold -= primary
    holding.shares += shares
    holding.cost += cost + fee
    _tape(db, club_id, me.id, "buy", shares, stock.price, fee)
    await db.commit()
    return await view(db, user, now)


async def sell(db: AsyncSession, user: User, club_id: int, shares: int, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    me = await _me(db, user, config)
    issuer = await db.get(ManagerClub, club_id)
    if issuer is None:
        raise NotFoundError("Клуб не найден")
    await _fresh(db, issuer, now)
    clubs = await _lock_pair(db, me.id, club_id)
    me = clubs[me.id]
    stock = await _stock(db, club_id, lock=True)
    holding = await _holding(db, club_id, me.id)
    shares = int(shares)
    if stock is None or shares <= 0 or shares > holding.shares:
        raise ConflictError(f"У тебя {holding.shares} акций этого клуба")
    gross = shares * stock.price
    fee = _fee(gross, config)
    await finance.book(db, me, "shares_sell", gross - fee, await finance.club_key(db, me, now), note=f"{shares} акц. «{issuer.name}»")
    holding.cost -= holding.cost * shares // holding.shares
    holding.shares -= shares
    stock.pool += shares
    _tape(db, club_id, me.id, "sell", shares, stock.price, fee)
    await db.commit()
    return await view(db, user, now)


async def buyback(db: AsyncSession, user: User, shares: int, now: Optional[datetime] = None) -> dict:
    """Take `shares` back: unsold ones free, the pool at the price, then
    holders pro rata at the price + premium. All back → the club leaves the
    exchange."""
    from app.services import manager_service as ms

    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    me = await _me(db, user, config)
    await finance._window(db, me)
    stock = await _stock(db, me.id, lock=True)
    shares = int(shares)
    if stock is None or stock.floated <= 0 or shares <= 0 or shares > stock.floated:
        raise ConflictError(f"На бирже {stock.floated if stock else 0} твоих акций")
    holders = (await db.execute(
        select(ManagerShare).where(ManagerShare.club_id == me.id, ManagerShare.shares > 0).order_by(ManagerShare.id)
    )).scalars().all()
    clubs = await ms._lock_clubs(db, [me.id, *(h.holder_club_id for h in holders)])
    me = clubs[me.id]
    stock = await _stock(db, me.id, lock=True)
    key = await finance.club_key(db, me, now)
    left = shares
    free_back = min(left, stock.unsold)
    stock.unsold -= free_back
    left -= free_back
    from_pool = min(left, stock.pool)
    left -= from_pool
    premium_price = stock.price * (100 + _int(config, "buyback_premium_pct")) // 100
    held = sum(h.shares for h in holders)
    plan: list[tuple[ManagerShare, int]] = []
    if left:
        if left > held:
            raise ConflictError("Столько акций нет на рынке")
        rest = left
        for i, h in enumerate(holders):
            take = rest if i == len(holders) - 1 else min(h.shares, -(-left * h.shares // held))
            take = min(take, h.shares, rest)
            if take:
                plan.append((h, take))
                rest -= take
        if rest:
            raise ConflictError("Столько акций нет на рынке")
    cost = from_pool * stock.price + sum(take * premium_price for _h, take in plan)
    if cost > await _free(db, me, config):
        raise ConflictError(f"На выкуп нужно {ms.money(cost)} — столько свободного бюджета нет")
    if from_pool:
        await finance.book(db, me, "buyback", -from_pool * stock.price, key, note=f"{from_pool} акц. с биржи")
        stock.pool -= from_pool
    for h, take in plan:
        holder = clubs[h.holder_club_id]
        h_row = await _holding(db, me.id, holder.id)
        amount = take * premium_price
        await finance.book(db, me, "buyback", -amount, key, note=f"{take} акц. у «{holder.name}»")
        await finance.book(db, holder, "shares_sell", amount, await finance.club_key(db, holder, now),
                           note=f"выкуп «{me.name}»: {take} акц.")
        h_row.cost -= h_row.cost * take // h_row.shares
        h_row.shares -= take
        await notify(db, holder.owner_id, NotificationType.manager_event, f"«{me.name}» выкупил акции 💼",
                     f"{take} акций по {ms.money(premium_price)} — {ms.money(amount)} в бюджет «{holder.name}»",
                     related_object_type=ms.RELATED, related_object_id=holder.id)
    stock.floated -= shares
    _tape(db, me.id, None, "buyback", shares, stock.price, 0)
    await db.commit()
    return await view(db, user, now)


def bond_limit(division: int, value: int, config) -> int:
    from app.services import manager_service as ms

    f = _f(config)
    by_grant = finance.grant_of(division, config) * finance._num(f["bond_grant_pct"]) / 100
    by_value = value * finance._num(f["bond_value_pct"]) / 100
    return ms._nice(max(0.0, min(by_grant, by_value)))


async def issue_bond(db: AsyncSession, user: User, units: int, rate_pct: float, seasons: int, now: Optional[datetime] = None) -> dict:
    from app.services import manager_service as ms

    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    me = await _me(db, user, config)
    await finance._window(db, me)
    await finance.ensure_can_transfer(db, me)
    f = _f(config)
    rate = finance._num(rate_pct, -1)
    low, high = finance._num(f["bond_rate_min_pct"]), finance._num(f["bond_rate_max_pct"])
    if not low <= rate <= high:
        raise ConflictError(f"Купон — от {low:g}% до {high:g}% за сезон")
    seasons = int(seasons)
    if not 1 <= seasons <= _int(config, "bond_seasons_max"):
        raise ConflictError(f"Срок — 1–{_int(config, 'bond_seasons_max')} сезона")
    unit = _int(config, "bond_unit_eur") or 100_000
    units = int(units)
    value = (await finance.club_value(db, me, config))["total"]
    room = bond_limit(me.division, value, config) - await bond_debt(db, me.id)
    if units <= 0 or units * unit > room:
        raise ConflictError(f"Можно занять ещё {ms.money(max(0, room))} ({max(0, room) // unit} обл. по {ms.money(unit)})")
    db.add(ManagerBond(club_id=me.id, season_key=await finance.upcoming_key(db, now), seasons_total=seasons, seasons_left=seasons,
                       rate_bp=round(rate * 100), unit_eur=unit, units_total=units, units_sold=0, status="selling"))
    await db.commit()
    return await view(db, user, now)


async def buy_bond(db: AsyncSession, user: User, bond_id: int, units: int, now: Optional[datetime] = None) -> dict:
    from app.services import manager_service as ms

    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    me = await _me(db, user, config)
    await trade_guard_service.ensure_can_give(db, user, config, own=True)
    found = await db.get(ManagerBond, bond_id)
    if found is None:
        raise NotFoundError("Облигация не найдена")
    if found.club_id == me.id:
        raise ConflictError("Свои облигации покупать нельзя")
    clubs = await _lock_pair(db, me.id, found.club_id)
    me, issuer = clubs[me.id], clubs[found.club_id]
    bond = (await db.execute(
        select(ManagerBond).where(ManagerBond.id == bond_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one()
    if bond.status != "selling" or await ms.is_playing(db, issuer):
        raise ConflictError("Продажа этих облигаций закончилась")
    units = int(units)
    if units <= 0 or bond.units_sold + units > bond.units_total:
        raise ConflictError(f"Осталось {bond.units_total - bond.units_sold} облигаций")
    holding = (await db.execute(
        select(ManagerBondHolding).where(ManagerBondHolding.bond_id == bond.id, ManagerBondHolding.holder_club_id == me.id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    cap = max(1, bond.units_total * _int(config, "bond_holder_max_pct") // 100)
    if (holding.units if holding else 0) + units > cap:
        raise ConflictError(f"В одних руках — не больше {cap} облигаций этого выпуска")
    cost = units * bond.unit_eur
    free = await _free(db, me, config)
    if cost > free:
        raise ConflictError(f"Нужно {ms.money(cost)}, свободно {ms.money(free)}")
    await finance.book(db, me, "bond_buy", -cost, await finance.club_key(db, me, now), note=f"«{issuer.name}»")
    await finance.book(db, issuer, "bond_in", cost, bond.season_key, note=f"«{me.name}»: {units} обл.")
    if holding is None:
        holding = ManagerBondHolding(bond_id=bond.id, holder_club_id=me.id, units=0, received=0)
        db.add(holding)
    holding.units += units
    bond.units_sold += units
    await db.commit()
    return await view(db, user, now)


async def repay_bond(db: AsyncSession, user: User, bond_id: int, now: Optional[datetime] = None) -> dict:
    """A defaulted bond paid in full: the principal to every holder."""
    from app.services import manager_service as ms

    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    me = await _me(db, user, config)
    bond = await db.get(ManagerBond, bond_id)
    if bond is None or bond.club_id != me.id or bond.status != "default":
        raise NotFoundError("Нет такой облигации в дефолте")
    holders = await _holdings(db, bond.id)
    clubs = await ms._lock_clubs(db, [me.id, *(h.holder_club_id for h in holders)])
    me = clubs[me.id]
    due = await bond_due(bond)
    if me.budget < due:
        raise ConflictError(f"Нужно {ms.money(due)}, в бюджете {ms.money(me.budget)}")
    await _settle_bond(db, me, bond, await finance.club_key(db, me, now), True)
    await db.commit()
    return await view(db, user, now)


# --- view ----------------------------------------------------------------------------------------

def _change(stock: ManagerStock) -> Optional[float]:
    history = stock.history or []
    if len(history) < 2 or not history[-2].get("p"):
        return None
    return round((history[-1]["p"] - history[-2]["p"]) * 100 / history[-2]["p"], 1)


async def view(db: AsyncSession, user: User, now: Optional[datetime] = None) -> dict:
    from app.services import manager_service as ms

    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    f = _f(config)
    me = await ms._owned_club(db, user.id)
    if me is None:
        raise NotFoundError("Сначала основай клуб")
    stocks = (await db.execute(select(ManagerStock).where(ManagerStock.floated > 0))).scalars().all()
    mine_stock = await _stock(db, me.id)
    clubs = {c.id: c for c in (await db.execute(
        select(ManagerClub).where(ManagerClub.id.in_({s.club_id for s in stocks} | {me.id}))
    )).scalars().all()}
    holdings = {h.club_id: h for h in (await db.execute(
        select(ManagerShare).where(ManagerShare.holder_club_id == me.id, ManagerShare.shares > 0)
    )).scalars().all()}
    cap = (mine_stock.shares_total if mine_stock else _int(config, "shares_total")) * _int(config, "holder_max_pct") // 100
    market = []
    for s in sorted(stocks, key=lambda s: -s.price * s.shares_total):
        c = clubs.get(s.club_id)
        if c is None:
            continue
        h = holdings.get(s.club_id)
        market.append({
            "club_id": c.id, "name": c.name, "division": c.division, "division_name": ms.division_name(c.division),
            "look": c.look or {}, "price": s.price, "change_pct": _change(s), "cap": s.price * s.shares_total,
            "available": s.unsold + s.pool, "floated": s.floated, "history": [h_["p"] for h_ in (s.history or [])][-20:],
            "mine": c.id == me.id, "held": h.shares if h else 0, "holder_cap": s.shares_total * _int(config, "holder_max_pct") // 100,
            "dividends_paid": s.dividends_paid,
        })
    portfolio = []
    for club_id, h in holdings.items():
        s = next((x for x in stocks if x.club_id == club_id), None)
        c = clubs.get(club_id)
        price = s.price if s else 0
        portfolio.append({"club_id": club_id, "name": c.name if c else "—", "shares": h.shares, "price": price,
                          "value": h.shares * price, "cost": h.cost, "dividends": h.dividends})
    holders = (await db.execute(
        select(ManagerShare, ManagerClub.name).join(ManagerClub, ManagerClub.id == ManagerShare.holder_club_id)
        .where(ManagerShare.club_id == me.id, ManagerShare.shares > 0).order_by(ManagerShare.shares.desc())
    )).all()
    value = (await finance.club_value(db, me, config))["total"]
    bonds = (await db.execute(
        select(ManagerBond).where(ManagerBond.status.in_(("selling", "active", "default"))).order_by(ManagerBond.id.desc()).limit(60)
    )).scalars().all()
    bond_clubs = {c.id: c for c in (await db.execute(
        select(ManagerClub).where(ManagerClub.id.in_({b.club_id for b in bonds} or {0}))
    )).scalars().all()}
    my_bond_units = {h.bond_id: h for h in (await db.execute(
        select(ManagerBondHolding).where(ManagerBondHolding.holder_club_id == me.id, ManagerBondHolding.units > 0)
    )).scalars().all()}

    def bond_out(b: ManagerBond) -> dict:
        c = bond_clubs.get(b.club_id)
        h = my_bond_units.get(b.id)
        return {"id": b.id, "club_id": b.club_id, "name": c.name if c else "—", "division": c.division if c else None,
                "rate_pct": b.rate_bp / 100, "unit_eur": b.unit_eur, "units_total": b.units_total, "units_sold": b.units_sold,
                "seasons_total": b.seasons_total, "seasons_left": b.seasons_left, "status": b.status, "season_key": b.season_key,
                "mine": b.club_id == me.id, "held": h.units if h else 0, "received": h.received if h else 0,
                "holder_cap": max(1, b.units_total * _int(config, "bond_holder_max_pct") // 100)}

    tape = (await db.execute(
        select(ManagerTrade, ManagerClub.name).join(ManagerClub, ManagerClub.id == ManagerTrade.club_id)
        .order_by(ManagerTrade.id.desc()).limit(TAPE_SHOWN)
    )).all()
    floated = mine_stock.floated if mine_stock else 0
    total = mine_stock.shares_total if mine_stock else _int(config, "shares_total")
    return {
        "enabled": bool(f["exchange_enabled"]),
        "club_id": me.id, "window_open": not await ms.is_playing(db, me),
        "budget": me.budget, "free_budget": await _free(db, me, config),
        "rules": {k: finance._num(f[k]) for k in (
            "shares_total", "ipo_max_pct", "holder_max_pct", "exchange_fee_pct", "buyback_premium_pct", "ipo_season_cap_pct",
            "dividend_pct", "bond_rate_min_pct", "bond_rate_max_pct", "bond_unit_eur", "bond_seasons_max", "bond_holder_max_pct",
        )},
        "my_stock": {
            "listed": floated > 0, "shares_total": total, "floated": floated,
            "unsold": mine_stock.unsold if mine_stock else 0, "pool": mine_stock.pool if mine_stock else 0,
            "held_by_others": sum(h.shares for h, _n in holders),
            "price": mine_stock.price if mine_stock and floated else await base_price(db, me, config, total),
            "history": [h["p"] for h in (mine_stock.history or [])][-20:] if mine_stock else [],
            "ipo_left": total * _int(config, "ipo_max_pct") // 100 - floated,
            "raised_this_season": mine_stock.raised_eur if mine_stock and mine_stock.raised_season == await finance.club_key(db, me, now) else 0,
            "raise_cap": finance.grant_of(me.division, config) * _int(config, "ipo_season_cap_pct") // 100,
            "dividends_paid": mine_stock.dividends_paid if mine_stock else 0,
            "buyback_price": (mine_stock.price if mine_stock else 0) * (100 + _int(config, "buyback_premium_pct")) // 100,
            "holders": [{"name": n, "shares": h.shares} for h, n in holders],
        },
        "market": market,
        "portfolio": portfolio,
        "bonds": {
            "limit": bond_limit(me.division, value, config), "owed": await bond_debt(db, me.id),
            "market": [bond_out(b) for b in bonds if b.status == "selling" and b.club_id != me.id],
            "mine": [bond_out(b) for b in bonds if b.club_id == me.id],
            "held": [bond_out(b) for b in bonds if b.id in my_bond_units],
        },
        "tape": [{"id": t.id, "club": n, "side": t.side, "shares": t.shares, "price": t.price,
                  "at": t.created_at.isoformat() if t.created_at else None} for t, n in tape],
    }
