"""«Филиал академии»: the region's nationalities, the release while a
contract is free, the career curve (1 season = 1 year), the market buy-back
once a season and the presidents' market without dumping."""
from datetime import datetime, timezone

import pytest

import app.core.rate_limit as rate_limit_module
from app.models.manager_filial import ManagerAlumnus, ManagerFilial
from app.models.user import User
from app.services import manager_filial, manager_finance, manager_service
from app.services.game_config_service import get_config
from tests.test_manager import API, _club, _no_season_at_the_real_clock, _player  # noqa: F401 (an autouse fixture)

pytestmark = pytest.mark.usefixtures("trade_guards_off")
FC = manager_finance.DEFAULTS


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _rich(db_session, user_id: int, coins: int = 200_000) -> None:
    user = await db_session.get(User, user_id)
    user.balance = coins
    await db_session.commit()


async def _filial_club(client, db_session, bot_token, tg_id: int, region: str = "europe", country: str = "Россия"):
    uid, headers = await _player(client, db_session, bot_token, tg_id)
    await _club(client, headers)
    await _rich(db_session, uid)
    resp = await client.post(f"{API}/manager/filial", headers=headers, json={"region": region, "country": country})
    assert resp.status_code == 200, resp.text
    return uid, headers, resp.json()


def _al(**kw) -> ManagerAlumnus:
    base = dict(name="Тест", country="Россия", position="CM", potential=3, peak=70, peak_age=26, decline_age=30,
                retire_age=35, start_age=17, joined_key="2026-W01", status="club")
    return ManagerAlumnus(**{**base, **kw})


def test_career_curve_one_season_one_year(db_session=None):
    class Cfg:
        manager_finance = {}
    al = _al()
    gap = FC["filial_grow_gap"]
    assert manager_filial.age_at(al, "2026-W01") == 17
    assert manager_filial.rating_at(al, "2026-W01", Cfg) == 70 - gap
    assert manager_filial.age_at(al, "2026-W10") == 26
    assert manager_filial.rating_at(al, "2026-W10", Cfg) == 70  # the peak at peak_age
    assert manager_filial.rating_at(al, "2026-W14", Cfg) == 70  # held until the decline age (30)
    after = manager_filial.rating_at(al, "2026-W17", Cfg)  # age 33
    assert after == round(70 - FC["filial_decline"] * 3)
    assert manager_filial.seasons_between("2025-W52", "2026-W02") == 2  # across the year


async def test_open_region_release_and_contract(client, db_session, bot_token):
    uid, headers, view = await _filial_club(client, db_session, bot_token, 897001, "south_america", "Бразилия")
    user = await db_session.get(User, uid)
    assert user.balance == 200_000 - FC["filial_open_coins"]
    filial = view["filial"]
    assert filial["contracts"] == FC["filial_contracts"] and filial["used"] == 0
    # The first release comes at once: candidates of the region's countries, the peak hidden.
    cands = filial["pending"]
    assert len(cands) == FC["filial_candidates"]
    south = set(manager_filial.REGIONS["south_america"]["countries"])
    assert all(c["country"] in south and c["peak"] is None and 1 <= c["stars"] <= 5 for c in cands)
    view = (await client.post(f"{API}/manager/filial/pick", headers=headers, json={"index": 0})).json()
    assert view["filial"]["used"] == 1 and view["filial"]["pending"] == []
    assert view["alumni"][0]["name"] == cands[0]["name"] and view["alumni"][0]["age"] == FC["filial_start_age"]
    # He plays for the club (an «alum» entry of the squad), the rating relative to the division.
    club = (await client.get(f"{API}/manager", headers=headers)).json()["club"]
    squad = club["squad"]["xi"] + club["squad"]["bench"]
    assert any(p["kind"] == "alum" and p["name"] == cands[0]["name"] for p in squad)
    # The one contract is taken: no release while he plays here.
    again = (await client.get(f"{API}/manager/filial", headers=headers)).json()
    assert again["filial"]["pending"] == []


async def test_peak_follows_the_division_and_buildings(db_session):
    config = await get_config(db_session)
    f = ManagerFilial(id=1, club_id=1, region="europe", country="Россия", levels={"fields": 2, "scout": 1})
    cands = manager_filial.candidates(f, 57, "2026-W40", config)
    assert len(cands) == FC["filial_candidates"] + 1  # «Скаут-офис»
    for c in cands:
        assert 57 + 2 <= c["peak"] <= 57 + 2 + FC["filial_potential_max"]
        assert c["retire_age"] > c["decline_age"] == FC["filial_decline_age"]
    # Seeded: the same filial and season give the same release.
    assert manager_filial.candidates(f, 57, "2026-W40", config) == cands
    europe = set(manager_filial.REGIONS["europe"]["countries"])
    assert {"Россия", "Украина", "Польша"} <= europe


async def test_internat_gives_contracts_and_a_quicker_release(db_session):
    config = await get_config(db_session)
    f = ManagerFilial(id=1, club_id=1, region="europe", levels={})
    assert manager_filial.contracts_of(f, config) == 1 and manager_filial.every_of(f, config) == FC["filial_every"]
    f.levels = {"internat": len(FC["filial_internat_coins"])}
    assert manager_filial.contracts_of(f, config) == 1 + len(FC["filial_internat_coins"]) == 3
    assert manager_filial.every_of(f, config) == FC["filial_every_min"] == 3


async def test_build_costs_coins_and_caps(client, db_session, bot_token):
    uid, headers, _view = await _filial_club(client, db_session, bot_token, 897011)
    prices = FC["filial_gym_coins"]
    for lvl in range(len(prices)):
        resp = await client.post(f"{API}/manager/filial/build", headers=headers, json={"code": "gym"})
        assert resp.status_code == 200
    assert (await client.post(f"{API}/manager/filial/build", headers=headers, json={"code": "gym"})).status_code == 409
    user = await db_session.get(User, uid)
    assert user.balance == 200_000 - FC["filial_open_coins"] - sum(prices)


async def test_market_buys_back_once_a_season(client, db_session, bot_token):
    _uid, headers, view = await _filial_club(client, db_session, bot_token, 897021)
    await client.post(f"{API}/manager/filial/build", headers=headers, json={"code": "internat"})
    view = (await client.post(f"{API}/manager/filial/pick", headers=headers, json={"index": 0})).json()
    al = view["alumni"][0]
    budget = (await client.get(f"{API}/manager", headers=headers)).json()["club"]["budget"]
    view = (await client.post(f"{API}/manager/filial/alumni/{al['id']}/sell-market", headers=headers)).json()
    assert view["alumni"] == [] and view["filial"]["sold_this_season"]
    after = (await client.get(f"{API}/manager", headers=headers)).json()["club"]["budget"]
    assert after - budget == al["sell_back"]
    # A second one this season can't go to the market.
    row = (await db_session.execute(
        ManagerAlumnus.__table__.select().where(ManagerAlumnus.id == al["id"]))).first()
    assert row.status == "sold"


async def test_presidents_market_no_dumping_and_pair_cooldown(client, db_session, bot_token):
    _a, a_headers, view = await _filial_club(client, db_session, bot_token, 897031)
    view = (await client.post(f"{API}/manager/filial/pick", headers=a_headers, json={"index": 0})).json()
    al = view["alumni"][0]
    # Below the floor (dumping to a friend or one's second account) is refused.
    cheap = (await client.post(f"{API}/manager/filial/alumni/{al['id']}/price", headers=a_headers, json={"price": 1}))
    assert cheap.status_code == 409
    price = al["price_min"]
    ok = await client.post(f"{API}/manager/filial/alumni/{al['id']}/price", headers=a_headers, json={"price": price})
    assert ok.status_code == 200
    _b, b_headers = await _player(client, db_session, bot_token, 897032)
    await _club(client, b_headers)
    lots = (await client.get(f"{API}/manager/filial/market", headers=b_headers)).json()["lots"]
    assert [x["id"] for x in lots] == [al["id"]]
    seller_before = (await client.get(f"{API}/manager", headers=a_headers)).json()["club"]["budget"]
    resp = await client.post(f"{API}/manager/filial/market/{al['id']}/buy", headers=b_headers)
    assert resp.status_code == 200, resp.text
    seller_after = (await client.get(f"{API}/manager", headers=a_headers)).json()["club"]["budget"]
    assert seller_after - seller_before == price - price * FC["filial_fee_pct"] // 100  # the fee is burnt
    # The buyer can't flip him straight back to the same club.
    b_view = (await client.get(f"{API}/manager/filial", headers=b_headers))
    assert b_view.status_code == 200
    row = await db_session.get(ManagerAlumnus, al["id"])
    await db_session.refresh(row)
    lo = manager_filial._bounds(row, manager_service.season_key(datetime.now(timezone.utc)), await get_config(db_session))[0]
    await client.post(f"{API}/manager/filial/alumni/{al['id']}/price", headers=b_headers, json={"price": lo})
    back = await client.post(f"{API}/manager/filial/market/{al['id']}/buy", headers=a_headers)
    assert back.status_code == 409 and "через" in back.json()["error"]["message"]
