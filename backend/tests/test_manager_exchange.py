"""«Кабинет президента», phase 2 (manager_exchange): IPO up to 49 %, buying
and selling through the exchange (fee burnt, 25 % in one hands, the price
set by the form only), dividends, the buyback, bonds (coupons, principal,
default → no transfers), the anti-farming rules."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.exceptions import ConflictError, ForbiddenError
from app.models.manager_club import ManagerBond, ManagerClub, ManagerLedger, ManagerShare, ManagerStock
from app.services import manager_exchange as exchange, manager_finance as finance, manager_service
from app.services.game_config_service import get_config
from tests.test_manager import API, M, _next_season_start, _reset_rate_limits  # noqa: F401
from tests.test_manager_finance import _club_row, _keep_loaded, _setup, _squad, _user  # noqa: F401

pytestmark = pytest.mark.usefixtures("trade_guards_off")


async def _stock(db_session, club_id) -> ManagerStock:
    return await db_session.get(ManagerStock, club_id, populate_existing=True)


async def _rich(db_session, club_id, budget=200 * M):
    club = await _club_row(db_session, club_id)
    club.budget = budget
    await db_session.commit()


async def _ledger(db_session, club_id, kind) -> int:
    return int((await db_session.execute(
        select(func.coalesce(func.sum(ManagerLedger.amount), 0)).where(ManagerLedger.club_id == club_id, ManagerLedger.kind == kind)
    )).scalar_one())


async def test_ipo_buy_sell_pool_fee_and_one_hands_cap(client, db_session, bot_token):
    config = await get_config(db_session)
    a_uid, a_headers, a_id = await _setup(client, db_session, bot_token, 896001, name="Совы")
    b_uid, b_headers, b_id = await _setup(client, db_session, bot_token, 896002, name="Ястребы")
    c_uid, _c_headers, c_id = await _setup(client, db_session, bot_token, 896003, name="Грачи")
    for club_id in (a_id, b_id, c_id):
        await _rich(db_session, club_id)
    with pytest.raises(ConflictError):  # 49 % at most
        await exchange.ipo(db_session, await _user(db_session, a_uid), 491)
    view = (await client.post(f"{API}/manager/exchange/ipo", headers=a_headers, json={"shares": 300})).json()
    stock = await _stock(db_session, a_id)
    price = stock.price
    assert stock.floated == stock.unsold == 300 and price == stock.base > 0
    assert view["my_stock"]["listed"] and view["my_stock"]["ipo_left"] == 190
    assert (await client.post(f"{API}/manager/exchange/{a_id}/buy", headers=a_headers, json={"shares": 1})).status_code == 409

    # B buys 200 IPO shares: the club gets the price, the fee is burnt.
    a_before, b_before = (await _club_row(db_session, a_id)).budget, (await _club_row(db_session, b_id)).budget
    resp = await client.post(f"{API}/manager/exchange/{a_id}/buy", headers=b_headers, json={"shares": 200})
    assert resp.status_code == 200, resp.text
    fee = 200 * price * finance.cfg(config)["exchange_fee_pct"] // 100
    assert (await _club_row(db_session, a_id)).budget == a_before + 200 * price
    assert (await _club_row(db_session, b_id)).budget == b_before - 200 * price - fee
    # 25 % in one hands: 250 of 1000.
    resp = await client.post(f"{API}/manager/exchange/{a_id}/buy", headers=b_headers, json={"shares": 51})
    assert resp.status_code == 409 and "одних руках" in resp.text

    # B sells 50 back to the exchange; C buys them from the pool — the club gets nothing.
    resp = await client.post(f"{API}/manager/exchange/{a_id}/sell", headers=b_headers, json={"shares": 50})
    assert resp.status_code == 200
    stock = await _stock(db_session, a_id)
    assert stock.pool == 50 and stock.unsold == 100
    a_mid = (await _club_row(db_session, a_id)).budget
    await exchange.buy(db_session, await _user(db_session, c_uid), a_id, 60)
    stock = await _stock(db_session, a_id)
    assert stock.pool == 0 and stock.unsold == 90
    assert (await _club_row(db_session, a_id)).budget == a_mid + 10 * price  # only the 10 IPO shares pay the club
    market = (await client.get(f"{API}/manager/exchange", headers=b_headers)).json()
    row = next(r for r in market["market"] if r["club_id"] == a_id)
    assert row["held"] == 150 and row["available"] == 90
    assert [p["shares"] for p in market["portfolio"]] == [150]


async def test_ipo_money_per_season_is_capped(client, db_session, bot_token):
    config = await get_config(db_session)
    a_uid, _a, a_id = await _setup(client, db_session, bot_token, 896011, name="Совы")
    b_uid, _b, b_id = await _setup(client, db_session, bot_token, 896012, name="Ястребы")
    await _rich(db_session, b_id)
    await exchange.ipo(db_session, await _user(db_session, a_uid), 200)
    stock = await _stock(db_session, a_id)
    club = await _club_row(db_session, a_id)
    cap = finance.grant_of(club.division, config) * finance.cfg(config)["ipo_season_cap_pct"] // 100
    stock.price = cap // 100 + 1  # 100 shares are already over the season's cap
    await db_session.commit()
    with pytest.raises(ConflictError):
        await exchange.buy(db_session, await _user(db_session, b_uid), a_id, 100)


async def test_price_follows_the_form_dividends_and_bonds_over_a_season(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    a_uid, a_headers, a_id = await _setup(client, db_session, bot_token, 896021, name="Совы")
    b_uid, b_headers, b_id = await _setup(client, db_session, bot_token, 896022, name="Ястребы")
    await _rich(db_session, b_id)
    await exchange.ipo(db_session, await _user(db_session, a_uid), 400)
    await exchange.buy(db_session, await _user(db_session, b_uid), a_id, 250)
    # A borrows 4 units for one season at 10 %; one club holds 25 % of a bond at most.
    resp = await client.post(f"{API}/manager/bonds", headers=a_headers, json={"units": 4, "rate_pct": 10, "seasons": 1})
    assert resp.status_code == 200, resp.text
    bond = (await db_session.execute(select(ManagerBond))).scalar_one()
    resp = await client.post(f"{API}/manager/bonds/{bond.id}/buy", headers=b_headers, json={"units": 2})
    assert resp.status_code == 409  # 25 % of 4 = 1
    a_before = (await _club_row(db_session, a_id)).budget
    resp = await client.post(f"{API}/manager/bonds/{bond.id}/buy", headers=b_headers, json={"units": 1})
    assert resp.status_code == 200, resp.text
    unit = finance.cfg(config)["bond_unit_eur"]
    assert (await _club_row(db_session, a_id)).budget == a_before + unit

    start = _next_season_start(config)
    assert await manager_service.ensure_season(db_session, start)
    bond = await db_session.get(ManagerBond, bond.id, populate_existing=True)
    assert bond.status == "active" and bond.units_total == 1  # unsold units dropped at the start
    league_id = (await _club_row(db_session, a_id)).league_id
    await manager_service.resolve_league(db_session, league_id, now=start + timedelta(hours=30))
    stock = await _stock(db_session, a_id)
    played = [h for h in stock.history if h["k"] == manager_service.season_key(start) and h["r"] > 0]
    assert played  # a price point after every round
    # The price is the base × the form, nothing else.
    league = await db_session.get(manager_service.ManagerLeague, league_id, populate_existing=True)
    index = next(t["index"] for t in league.state["teams"] if t["club_id"] == a_id)
    ppg, form, _n = exchange.form_of(league.state, index)
    assert stock.price == exchange.price_from(stock.base, ppg, form, config)

    # The season ends: dividends to B (if A made a profit), the coupon and the principal of the bond.
    a_club = await _club_row(db_session, a_id)
    a_club.budget += 50 * M  # enough to pay
    await db_session.commit()
    await manager_service.resolve_league(db_session, league_id, now=start + timedelta(days=7))
    # (the dividends are counted before the bond coupon of the same season end)
    profit = await exchange.season_profit(db_session, a_id, manager_service.season_key(start)) - await _ledger(db_session, a_id, "coupon_out")
    holding = (await db_session.execute(select(ManagerShare).where(ManagerShare.holder_club_id == b_id))).scalar_one()
    holding = await db_session.get(ManagerShare, holding.id, populate_existing=True)
    if profit > 0:
        per_share = profit * finance.cfg(config)["dividend_pct"] // 100 // 1000
        assert holding.dividends == per_share * 250 == await _ledger(db_session, b_id, "dividend_in")
    bond = await db_session.get(ManagerBond, bond.id, populate_existing=True)
    assert bond.status == "repaid"
    assert await _ledger(db_session, b_id, "coupon_in") == unit * 10 // 100
    assert await _ledger(db_session, b_id, "bond_back") == unit
    # Settling twice pays nothing more.
    await exchange.season_end(db_session, await _club_row(db_session, a_id), manager_service.season_key(start), config)
    assert await _ledger(db_session, b_id, "bond_back") == unit


def test_price_formula_is_bounded():
    config = type("C", (), {"manager_finance": {}})()
    assert exchange.price_from(1000, 1.4, 1.4, config) == 1000
    assert exchange.price_from(1000, 3, 3, config) == 1000 * (100 + 1.6 * 20 + 1.6 * 10) // 100
    assert exchange.price_from(1000, 0, 0, config) == 1000 * (100 - 1.4 * 30) // 100
    assert exchange.price_from(1000, 99, 99, config) == 2000  # price_max_pct


async def test_buyback_unsold_free_pool_at_price_holders_at_premium(client, db_session, bot_token):
    config = await get_config(db_session)
    a_uid, a_headers, a_id = await _setup(client, db_session, bot_token, 896031, name="Совы")
    b_uid, _b, b_id = await _setup(client, db_session, bot_token, 896032, name="Ястребы")
    await _rich(db_session, a_id)
    await _rich(db_session, b_id)
    await exchange.ipo(db_session, await _user(db_session, a_uid), 300)
    await exchange.buy(db_session, await _user(db_session, b_uid), a_id, 200)
    await exchange.sell(db_session, await _user(db_session, b_uid), a_id, 50)
    stock = await _stock(db_session, a_id)
    price = stock.price
    assert (stock.unsold, stock.pool) == (100, 50)
    a_before, b_before = (await _club_row(db_session, a_id)).budget, (await _club_row(db_session, b_id)).budget
    resp = await client.post(f"{API}/manager/exchange/buyback", headers=a_headers, json={"shares": 300})
    assert resp.status_code == 200, resp.text
    premium = price * (100 + finance.cfg(config)["buyback_premium_pct"]) // 100
    assert (await _club_row(db_session, a_id)).budget == a_before - 50 * price - 150 * premium
    assert (await _club_row(db_session, b_id)).budget == b_before + 150 * premium
    stock = await _stock(db_session, a_id)
    assert stock.floated == stock.unsold == stock.pool == 0
    assert not resp.json()["my_stock"]["listed"]
    holding = (await db_session.execute(select(ManagerShare).where(ManagerShare.holder_club_id == b_id))).scalar_one()
    assert (await db_session.get(ManagerShare, holding.id, populate_existing=True)).shares == 0


async def test_bond_default_closes_transfers_until_repaid(client, db_session, bot_token):
    config = await get_config(db_session)
    a_uid, a_headers, a_id = await _setup(client, db_session, bot_token, 896041, name="Совы")
    b_uid, b_headers, b_id = await _setup(client, db_session, bot_token, 896042, name="Ястребы")
    await _rich(db_session, b_id)
    club = await _club_row(db_session, a_id)
    value = (await finance.club_value(db_session, club, config))["total"]
    limit = exchange.bond_limit(club.division, value, config)
    unit = finance.cfg(config)["bond_unit_eur"]
    with pytest.raises(ConflictError):
        await exchange.issue_bond(db_session, await _user(db_session, a_uid), limit // unit + 1, 10, 1)
    with pytest.raises(ConflictError):  # the coupon range
        await exchange.issue_bond(db_session, await _user(db_session, a_uid), 1, 99, 1)
    await exchange.issue_bond(db_session, await _user(db_session, a_uid), 4, 10, 1)
    bond = (await db_session.execute(select(ManagerBond))).scalar_one()
    await exchange.buy_bond(db_session, await _user(db_session, b_uid), bond.id, 1)
    key = manager_service.season_key(_next_season_start(config))
    club = await _club_row(db_session, a_id)
    await exchange.bonds_start(db_session, club, key)
    club.budget = 0
    await db_session.commit()
    club = await _club_row(db_session, a_id)
    assert await exchange.season_end(db_session, club, key, config) == ["дефолт по облигациям — трансферы закрыты"]
    await db_session.commit()
    assert "Дефолт" in (await finance.transfer_block(db_session, await _club_row(db_session, a_id)))
    club = await _club_row(db_session, a_id)
    club.budget = 10 * M
    await db_session.commit()
    resp = await client.post(f"{API}/manager/bonds/{bond.id}/repay", headers=a_headers)
    assert resp.status_code == 200, resp.text
    assert await _ledger(db_session, b_id, "bond_back") == unit
    assert await finance.transfer_block(db_session, await _club_row(db_session, a_id)) is None


async def test_new_accounts_cant_buy_shares(client, db_session, bot_token):
    config = await get_config(db_session)
    a_uid, _a, a_id = await _setup(client, db_session, bot_token, 896051, name="Совы")
    b_uid, _b, b_id = await _setup(client, db_session, bot_token, 896052, name="Ястребы")
    await _rich(db_session, b_id)
    await exchange.ipo(db_session, await _user(db_session, a_uid), 100)
    config.trade_send_min_account_age_days = 30
    await db_session.commit()
    with pytest.raises(ForbiddenError):
        await exchange.buy(db_session, await _user(db_session, b_uid), a_id, 10)
    assert (await db_session.execute(select(func.count(ManagerShare.id)))).scalar_one() == 0
    assert (await _club_row(db_session, a_id)).budget == (await db_session.get(ManagerClub, a_id)).budget
