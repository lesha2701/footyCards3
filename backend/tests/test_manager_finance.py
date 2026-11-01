"""«Менеджер» → «Кабинет президента» (manager_finance): the club money ledger
and the report by seasons, the club value, sponsors, the bank loan (interest,
collection, overdue → no transfers), and the season deals: shirt sponsor,
tours (fans, tired legs), TV rights, deposit, venture fund, farm club."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.exceptions import ConflictError
from app.models.club_base import UserClubBase
from app.models.enums import Position
from app.models.manager_club import ManagerClub, ManagerDeal, ManagerLeague, ManagerLedger, ManagerLoan
from app.models.user import User
from app.services import manager_finance as finance, manager_service
from app.services.game_config_service import get_config
from tests.factories import create_player
from tests.test_manager import API, M, _club, _next_season_start, _player, _no_season_at_the_real_clock, _reset_rate_limits  # noqa: F401

pytestmark = pytest.mark.usefixtures("trade_guards_off")


@pytest.fixture(autouse=True)
def _keep_loaded(db_session):
    """The services commit; tests keep reading config / users they hold
    (rows they check are re-read with populate_existing)."""
    db_session.sync_session.expire_on_commit = False
    yield


async def _setup(client, db_session, bot_token, tg_id, levels=None, name="Совы"):
    uid, headers = await _player(client, db_session, bot_token, tg_id)
    if levels:
        db_session.add(UserClubBase(user_id=uid, levels=levels, total_level=sum(levels.values()), appearance={}))
        await db_session.commit()
    await _club(client, headers, name)
    club = (await db_session.execute(select(ManagerClub).where(ManagerClub.owner_id == uid))).scalar_one()
    return uid, headers, club.id


async def _club_row(db_session, club_id) -> ManagerClub:
    return await db_session.get(ManagerClub, club_id, populate_existing=True)


async def _user(db_session, uid) -> User:
    return await db_session.get(User, uid, populate_existing=True)


async def _ledger_sum(db_session, club_id, kind=None) -> int:
    stmt = select(func.coalesce(func.sum(ManagerLedger.amount), 0)).where(ManagerLedger.club_id == club_id)
    if kind:
        stmt = stmt.where(ManagerLedger.kind == kind)
    return int((await db_session.execute(stmt)).scalar_one())


async def _squad(db_session, rating):
    for position in (Position.GK, Position.CB, Position.CB, Position.LB, Position.RB, Position.CM, Position.CDM, Position.CAM,
                     Position.LW, Position.RW, Position.ST):
        await create_player(db_session, rating=rating, position=position)


async def test_every_euro_is_in_the_ledger_and_the_report(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    uid, headers, club_id = await _setup(client, db_session, bot_token, 895001)
    start = _next_season_start(config)
    assert await manager_service.ensure_season(db_session, start)
    league_id = (await _club_row(db_session, club_id)).league_id
    await manager_service.resolve_league(db_session, league_id, now=start + timedelta(days=7))
    club = await _club_row(db_session, club_id)
    # The ledger explains the whole budget: grants, wages, loans of footballers, matches, tickets, prizes, moves.
    assert await _ledger_sum(db_session, club_id) == club.budget
    assert await _ledger_sum(db_session, club_id, "grant") > 0 and await _ledger_sum(db_session, club_id, "match") > 0
    view = await finance.view(db_session, await _user(db_session, uid), start + timedelta(days=7))
    season = next(s for s in view["report"] if s["key"] == manager_service.season_key(start))
    assert season["income"] > 0 and season["expense"] < 0
    assert season["profit"] == season["income"] + season["expense"]
    assert {line["kind"] for line in season["lines"]} >= {"grant", "match", "wages"}
    resp = await client.get(f"{API}/manager/office", headers=headers)
    assert resp.status_code == 200 and resp.json()["value"]["total"] > 0


async def test_club_value_counts_squad_budget_base_fans_titles_minus_debt(client, db_session, bot_token):
    config = await get_config(db_session)
    uid, _headers, club_id = await _setup(client, db_session, bot_token, 895002, {"hq": 4, "stadium": 2})
    club = await _club_row(db_session, club_id)
    club.titles, club.fans_bonus = 2, 100
    await db_session.commit()
    f = finance.cfg(config)
    value = await finance.club_value(db_session, club, config)
    parts = value["parts"]
    assert parts["budget"] == club.budget and parts["titles"] == 2 * f["value_per_title"]
    assert parts["fans"] == 100 * f["value_per_fan"] and parts["base"] == 6 * f["value_per_base_level"]
    assert value["total"] == sum(parts.values())


async def test_sponsors_safe_now_bonus_per_win_ambitious_for_the_title(client, db_session, bot_token):
    config = await get_config(db_session)
    pre = _next_season_start(config) - timedelta(hours=2)
    uid, _headers, club_id = await _setup(client, db_session, bot_token, 895003, {"hq": 5, "marketing": 5})
    user = await _user(db_session, uid)
    club = await _club_row(db_session, club_id)
    grant = finance.grant_of(club.division, config)
    before = club.budget
    view = await finance.sign(db_session, user, "sponsor", "safe", now=pre)
    safe = next(s for s in view["sponsors"]["offers"] if s["code"] == "safe")
    # «Отдел маркетинга» ур. 5: +10 % to every sponsor sum.
    assert safe["upfront"] == manager_service._nice(grant * 25 * 110 / 100 / 100)
    assert (await _club_row(db_session, club_id)).budget == before + safe["upfront"]
    with pytest.raises(ConflictError):  # one sponsor a season
        await finance.sign(db_session, user, "sponsor", "bonus", now=pre)

    # Season results are settled by the pyramid: the ambitious one pays for the title, nothing on relegation.
    deal = ManagerDeal(club_id=club_id, kind="sponsor", season_key="2030-W01", option="ambitious",
                       data={"places": [80 * M, 20 * M], "rest": 5 * M, "relegated": 0})
    db_session.add(deal)
    await db_session.commit()
    club = await _club_row(db_session, club_id)
    budget = club.budget
    await finance.season_end(db_session, club, "2030-W01", 1, False, config)
    await finance.season_end(db_session, club, "2030-W01", 1, False, config)  # once
    await db_session.commit()
    assert (await _club_row(db_session, club_id)).budget == budget + 80 * M
    relegated = ManagerDeal(club_id=club_id, kind="sponsor", season_key="2030-W02", option="ambitious",
                            data={"places": [80 * M], "rest": 5 * M, "relegated": 0})
    db_session.add(relegated)
    await db_session.commit()
    club = await _club_row(db_session, club_id)
    budget = club.budget
    await finance.season_end(db_session, club, "2030-W02", 14, True, config)
    await db_session.commit()
    assert (await _club_row(db_session, club_id)).budget == budget


async def test_bonus_sponsor_pays_for_each_win_of_the_season(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    start = _next_season_start(config)
    uid, _headers, club_id = await _setup(client, db_session, bot_token, 895004)
    await finance.sign(db_session, await _user(db_session, uid), "sponsor", "bonus", now=start - timedelta(hours=2))
    assert await manager_service.ensure_season(db_session, start)
    club = await _club_row(db_session, club_id)
    league = await db_session.get(ManagerLeague, club.league_id)
    team = next(t for t in league.state["teams"] if t["club_id"] == club_id)
    per_win = team["finance"]["sponsor_win"]
    assert per_win > 0
    await manager_service.resolve_league(db_session, league.id, now=start + timedelta(days=7))
    league = await db_session.get(ManagerLeague, league.id, populate_existing=True)
    row = next(r for r in manager_service.standings(league.state) if league.state["teams"][r["team_index"]]["club_id"] == club_id)
    wins = (await db_session.execute(
        select(func.count(ManagerLedger.id)).where(ManagerLedger.club_id == club_id, ManagerLedger.kind == "sponsor",
                                                   ManagerLedger.note == "бонус за победу")
    )).scalar_one()
    assert wins == row["won"]
    deal = (await db_session.execute(select(ManagerDeal).where(ManagerDeal.club_id == club_id))).scalar_one()
    assert deal.status == "done"


async def test_loan_interest_collection_overdue_blocks_transfers(client, db_session, bot_token):
    config = await get_config(db_session)
    start = _next_season_start(config)
    pre = start - timedelta(hours=2)
    uid, headers, club_id = await _setup(client, db_session, bot_token, 895005, {"hq": 10, "accounting": 10})
    user = await _user(db_session, uid)
    view = await finance.view(db_session, user, pre)
    limit, rate = view["loan"]["limit"], view["loan"]["rate_pct"]
    assert rate == 12 - 0.16 * 10  # «Бухгалтерия» cuts the rate
    with pytest.raises(ConflictError):
        await finance.take_loan(db_session, user, limit + 1, 1, now=pre)
    budget = (await _club_row(db_session, club_id)).budget
    await finance.take_loan(db_session, user, limit, 1, now=pre)
    assert (await _club_row(db_session, club_id)).budget == budget + limit
    with pytest.raises(ConflictError):  # one loan at a time
        await finance.take_loan(db_session, user, finance.cfg(config)["loan_min_eur"], 1, now=pre)
    with pytest.raises(ConflictError):  # no deposit on borrowed money
        await finance.sign(db_session, user, "deposit", amount=finance.cfg(config)["deposit_min_eur"], now=pre)

    club = await _club_row(db_session, club_id)
    key = manager_service.season_key(start)
    await finance.season_start(db_session, club, key, {}, config)
    await finance.season_start(db_session, club, key, {}, config)  # once a season
    await db_session.commit()
    loan = (await db_session.execute(select(ManagerLoan))).scalar_one()
    assert loan.debt == limit + limit * loan.rate_bp // 10_000 and loan.seasons_left == 0
    # The next season start: not enough money → overdue, a penalty, no transfers.
    club = await _club_row(db_session, club_id)
    club.budget = 0
    await db_session.commit()
    due = loan.debt
    await finance.season_start(db_session, club, finance.shift_key(key, 1), {}, config)
    await db_session.commit()
    loan = await db_session.get(ManagerLoan, loan.id, populate_existing=True)
    assert loan.status == "overdue" and loan.debt == due + due * finance.cfg(config)["loan_penalty_pct"] // 100
    player = await create_player(db_session, rating=60, position=Position.ST)
    resp = await client.post(f"{API}/manager/npc", headers=headers, json={"player_id": player.id, "kind": "loan"})
    assert resp.status_code == 409 and "Кредит просрочен" in resp.text
    club = await _club_row(db_session, club_id)
    club.budget = loan.debt + M
    await db_session.commit()
    resp = await client.post(f"{API}/manager/office/loan/repay", headers=headers, json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["loan"]["open"] is None and (await _club_row(db_session, club_id)).budget == M
    resp = await client.post(f"{API}/manager/npc", headers=headers, json={"player_id": player.id, "kind": "loan"})
    assert resp.status_code == 200, resp.text


async def test_loan_is_collected_when_the_budget_has_it(client, db_session, bot_token):
    config = await get_config(db_session)
    start = _next_season_start(config)
    uid, _headers, club_id = await _setup(client, db_session, bot_token, 895006)
    user = await _user(db_session, uid)
    await finance.take_loan(db_session, user, finance.cfg(config)["loan_min_eur"], 1, now=start - timedelta(hours=2))
    key = manager_service.season_key(start)
    club = await _club_row(db_session, club_id)
    await finance.season_start(db_session, club, key, {}, config)
    await db_session.commit()
    budget, debt = club.budget, (await db_session.execute(select(ManagerLoan))).scalar_one().debt
    # The next start collects it: the window sets the debt aside like the wages.
    club = await _club_row(db_session, club_id)
    assert await finance.loan_due(db_session, club) == debt
    assert await manager_service.start_bill(db_session, club, config) == await manager_service.wage_bill(db_session, club, config) + debt
    await finance.season_start(db_session, club, finance.shift_key(key, 1), {}, config)
    await db_session.commit()
    loan = (await db_session.execute(select(ManagerLoan))).scalar_one()
    assert loan.status == "repaid" and (await _club_row(db_session, club_id)).budget == budget - debt


async def test_shirt_sponsor_grows_with_the_shop_and_pays_each_season_once(client, db_session, bot_token):
    config = await get_config(db_session)
    start = _next_season_start(config)
    pre = start - timedelta(hours=2)
    uid, _headers, club_id = await _setup(client, db_session, bot_token, 895007, {"hq": 6, "shop": 5})
    user = await _user(db_session, uid)
    f = finance.cfg(config)
    brand = f["kit_brands"][0]
    with pytest.raises(Exception):
        await finance.sign(db_session, user, "kit", "Нет такого", seasons=2, now=pre)
    budget = (await _club_row(db_session, club_id)).budget
    view = await finance.sign(db_session, user, "kit", brand, seasons=2, now=pre)
    price = view["offers"]["kit"]["prices"][1]
    division = (await _club_row(db_session, club_id)).division
    base = (f["kit_base_eur"] + f["kit_eur_per_level"] * 5) * manager_service._pct(config.manager_division_income_pct, division) // 100
    assert price == manager_service._nice(base * 110 / 100)  # «Клубный магазин» ур. 5, +10 % for the second season
    club = await _club_row(db_session, club_id)
    assert club.budget == budget + price and view["offers"]["kit"]["taken"] and view["offers"]["kit"]["worn"] == brand
    with pytest.raises(ConflictError):  # one shirt sponsor a season
        await finance.sign(db_session, user, "kit", f["kit_brands"][1], now=pre)
    key = manager_service.season_key(start)
    for k in (key, key, finance.shift_key(key, 1), finance.shift_key(key, 2)):
        await finance.season_start(db_session, club, k, {}, config)
    await db_session.commit()
    assert await _ledger_sum(db_session, club_id, "kit") == 2 * price  # this season and the next, once each


async def test_tour_brings_money_fans_and_tired_legs(client, db_session, bot_token):
    config = await get_config(db_session)
    start = _next_season_start(config)
    uid, _headers, club_id = await _setup(client, db_session, bot_token, 895008, {"hq": 10, "hotel": 10, "media": 5})
    user = await _user(db_session, uid)
    budget = (await _club_row(db_session, club_id)).budget
    view = await finance.sign(db_session, user, "tour", "asia", now=start - timedelta(hours=2))
    asia = next(t for t in view["offers"]["tour"]["options"] if t["code"] == "asia")
    grant = finance.grant_of((await _club_row(db_session, club_id)).division, config)
    assert asia["cost"] == manager_service._nice(grant * 14 * 80 / 100 / 100)  # «Клубный отель» ур. 10: −20 %
    assert asia["fans"] == 900 * 120 // 100  # «Медиацентр» ур. 5: +20 % fans
    club = await _club_row(db_session, club_id)
    assert club.budget == budget + asia["revenue"] - asia["cost"] and club.fans_bonus == asia["fans"]
    money = await finance.season_start(db_session, club, manager_service.season_key(start), {}, config)
    assert money["fatigue_rounds"] == 4 and money["fans"] == asia["fans"]
    mods = finance.fatigue_mods({"MID": 2.0}, money, 0)
    assert mods["MID"] == 2.0 - 6 and mods["GK"] == -6
    assert finance.fatigue_mods({"MID": 2.0}, money, 4) == {"MID": 2.0}


async def test_tv_rights_sold_forward_take_the_match_income(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    start = _next_season_start(config)
    uid, _headers, club_id = await _setup(client, db_session, bot_token, 895009)
    view = await finance.sign(db_session, await _user(db_session, uid), "tv", now=start - timedelta(hours=2))
    tv = view["offers"]["tv"]
    assert tv["advance"] == manager_service._nice(tv["estimate"] * 70 / 100)
    assert await _ledger_sum(db_session, club_id, "tv") == tv["advance"]
    assert await manager_service.ensure_season(db_session, start)
    await manager_service.resolve_league(db_session, (await _club_row(db_session, club_id)).league_id, now=start + timedelta(days=7))
    assert await _ledger_sum(db_session, club_id, "match") == 0


async def test_deposit_returns_with_interest_and_the_venture_is_a_bet(client, db_session, bot_token):
    config = await get_config(db_session)
    start = _next_season_start(config)
    pre = start - timedelta(hours=2)
    uid, _headers, club_id = await _setup(client, db_session, bot_token, 895010, {"hq": 10, "accounting": 10})
    user = await _user(db_session, uid)
    club = await _club_row(db_session, club_id)
    stake, budget = club.budget // 2, club.budget
    with pytest.raises(ConflictError):  # the venture fund takes a share of the budget at most
        await finance.sign(db_session, user, "venture", amount=budget // 2, now=pre)
    await finance.sign(db_session, user, "deposit", amount=stake, now=pre)
    venture = budget * 20 // 100 // 2
    await finance.sign(db_session, user, "venture", amount=venture, now=pre)
    club = await _club_row(db_session, club_id)
    assert club.budget == budget - stake - venture
    value = await finance.club_value(db_session, club, config)
    assert value["parts"]["invested"] == stake + venture  # parked money still counts in the value
    key = manager_service.season_key(start)
    await finance.season_end(db_session, club, key, 5, False, config)
    await db_session.commit()
    deposit = (await db_session.execute(select(ManagerDeal).where(ManagerDeal.kind == "deposit"))).scalar_one()
    venture_deal = (await db_session.execute(select(ManagerDeal).where(ManagerDeal.kind == "venture"))).scalar_one()
    assert deposit.data["rate_bp"] == int(round((4 + 0.12 * 10) * 100))
    assert deposit.result == stake + stake * deposit.data["rate_bp"] // 10_000
    assert venture_deal.status in ("done", "lost")
    assert venture_deal.result == (venture * 3 if venture_deal.status == "done" else 0)
    assert (await _club_row(db_session, club_id)).budget == budget - stake - venture + deposit.result + venture_deal.result


async def test_farm_club_cheaper_loans_and_stronger_kids(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    start = _next_season_start(config)
    uid, headers, club_id = await _setup(client, db_session, bot_token, 895011, {"hq": 10, "training": 10})
    player = await create_player(db_session, rating=58, position=Position.ST)
    await finance.sign(db_session, await _user(db_session, uid), "farm")  # for the coming season
    farm = (await db_session.execute(select(ManagerDeal).where(ManagerDeal.kind == "farm"))).scalar_one()
    assert farm.data == {"keys": [farm.season_key], "loan_cut_pct": 30, "kid_bonus": 3 + 2}  # +0.2 per training level
    cheap = manager_service.npc_terms(58, config, loan_cut_pct=30)["loan_fee"]
    assert cheap < manager_service.npc_terms(58, config)["loan_fee"]
    resp = await client.get(f"{API}/manager/npc?q={player.display_name}", headers=headers)
    assert [p["loan_fee"] for p in resp.json()["players"] if p["player_id"] == player.id] == [cheap]
    # The season the farm club covers starts with stronger academy kids.
    farm.season_key, farm.data = manager_service.season_key(start), {**farm.data, "keys": [manager_service.season_key(start)]}
    await db_session.commit()
    assert await manager_service.ensure_season(db_session, start)
    club = await _club_row(db_session, club_id)
    league = await db_session.get(ManagerLeague, club.league_id)
    team = next(t for t in league.state["teams"] if t["club_id"] == club_id)
    assert team["filler"] == manager_service._division_rating(club.division, config) - (manager_service.FILLER_GAP - 5)


async def test_office_keeps_the_common_transfer_window(client, db_session, bot_token):
    """A club out of this season's leagues (founded too late) signs no deals
    and floats no shares while the others play — the office opens with the
    transfer window for everybody."""
    from datetime import datetime, timezone

    from app.models.manager_club import ManagerSeason
    from app.services import manager_exchange as exchange

    uid, headers, _ = await _setup(client, db_session, bot_token, 895021)
    season = ManagerSeason(key=manager_service.season_key(datetime.now(timezone.utc)), depth=1)
    db_session.add(season)
    await db_session.commit()

    office = (await client.get(f"{API}/manager/office", headers=headers)).json()
    assert office["window_open"] is False
    with pytest.raises(ConflictError):
        await finance.sign(db_session, await _user(db_session, uid), "tv")
    with pytest.raises(ConflictError):
        await exchange.ipo(db_session, await _user(db_session, uid), 100)

    season.settled_at = datetime.now(timezone.utc)
    await db_session.commit()
    assert (await client.get(f"{API}/manager/office", headers=headers)).json()["window_open"] is True
    await finance.sign(db_session, await _user(db_session, uid), "tv")


async def test_deals_only_in_the_window_and_admin_numbers(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    start = _next_season_start(config)
    uid, headers, club_id = await _setup(client, db_session, bot_token, 895012)
    assert await manager_service.ensure_season(db_session, start)
    with pytest.raises(ConflictError):  # the club plays its season
        await finance.sign(db_session, await _user(db_session, uid), "tv", now=start + timedelta(hours=1))
    assert finance.validate({"loan_rate_pct": 9, "venture_win_pct": 35.5}) == {"loan_rate_pct": 9, "venture_win_pct": 35.5}
    with pytest.raises(ValueError):
        finance.validate({"nope": 1})
    with pytest.raises(ValueError):
        finance.validate({"loan_rate_pct": -1})
    config.manager_finance = {"loan_rate_pct": 9}
    await db_session.commit()
    assert finance.cfg(config)["loan_rate_pct"] == 9 and finance.cfg(config)["deposit_rate_pct"] == 4
