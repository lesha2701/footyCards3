"""«Менеджер»: own clubs with club euros (a season grant from the division
and the «Клубная база»), the Transfermarkt-like value curve, the transfer
market of users' «Мои игроки» (sign / transfer / loan, both consents),
catalog footballers (buy / loan, one club at a time), the always-starting
own player and academy card, the weekly season (preseason → automatic
signings → 15 rounds with daily digests → promotion / relegation of the
×2 pyramid), the style shop, fans' merchandise, «Менеджер Pro» and the
share cards."""
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.club_base import UserClubBase
from app.models.enums import CardSource, NotificationType, Position, Rarity
from app.models.manager_club import (
    ManagerClub,
    ManagerContract,
    ManagerCosmetic,
    ManagerLeague,
    ManagerNpc,
    ManagerSeason,
    ManagerValueHistory,
)
from app.models.notification import Notification
from app.models.player import Player
from app.models.user import User
from app.services import manager_service, manager_shop, manager_tactics, share_service
from app.services.card_creation import create_user_card
from app.services.game_config_service import get_config
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1"
# Founding a club follows the trade give rules; the new-account ban is tested separately.
pytestmark = pytest.mark.usefixtures("trade_guards_off")
LOOK = {"skin": 1, "hair": 1, "hair_color": 1, "beard": 0, "eye_color": 0, "kit": 0, "kit_pattern": 0}
M = 1_000_000
START = 50_000  # coins of a test user (club, style and merch prices are high)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


def _next_season_start(config) -> datetime:
    """A moment just after next week's preseason closes."""
    now = datetime.now(timezone.utc)
    return manager_service.preseason_end(now + timedelta(days=7), config) + timedelta(minutes=5)


async def _player(client, db_session, bot_token, tg_id, position="ST", xp=5000, balance=START):
    headers = telegram_headers(tg_id, bot_token)
    await client.post(f"{API}/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, tg_id)
    resp = await client.post(f"{API}/my-player", headers=headers,
                             json={"name": "Игрок " + "АБВГДЕЖЗИК"[tg_id % 10], "number": 9, "position": position, "appearance": LOOK})
    assert resp.status_code == 200, resp.text
    user = await db_session.get(User, user.id)
    user.my_player_xp = xp
    user.balance = balance
    await db_session.commit()
    return user.id, headers


async def _club(client, headers, name="Ночные Совы"):
    resp = await client.post(f"{API}/manager/club", headers=headers, json={"name": name})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _accept_latest(client, headers) -> dict:
    offer_id = (await client.get(f"{API}/manager", headers=headers)).json()["offers"][0]["id"]
    resp = await client.post(f"{API}/manager/offers/{offer_id}/respond", headers=headers, json={"accept": True})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_value_curve_is_in_millions(db_session):
    config = await get_config(db_session)
    assert manager_service.value_of(70, config) == 3_500_000
    assert manager_service.value_of(90, config) == 160 * M
    assert manager_service.value_of(30, config) == 50_000 and manager_service.value_of(99, config) == 220 * M
    between = manager_service.value_of(72, config)
    assert 3_500_000 < between < 12 * M and len(str(between).rstrip("0")) <= 2  # two significant digits
    assert manager_service.money(3_500_000) == "€3,5 млн" and manager_service.money(150_000) == "€150 тыс"


async def test_found_club_at_the_bottom_with_a_base_budget(client, db_session, bot_token):
    config = await get_config(db_session)
    bottom, grant = config.manager_divisions, config.manager_division_budget[config.manager_divisions - 1]
    per_level, sponsor, cap_pct, cost = (config.manager_budget_per_base_level, config.manager_sponsor_eur_per_level,
                                         config.manager_base_bonus_cap_pct, config.manager_found_cost)
    league_size = config.manager_league_size
    a_id, a_headers = await _player(client, db_session, bot_token, 894001)
    db_session.add(UserClubBase(user_id=a_id, levels={"hq": 3, "marketing": 2}, total_level=5, appearance={}))
    await db_session.commit()
    view = await _club(client, a_headers)
    club = view["club"]
    assert club["division"] == bottom and club["base"]["marketing"] == 2
    bonus = min(per_level * 5 + sponsor * 2, grant * cap_pct // 100)
    assert club["budget"] == grant + bonus == club["next_grant"]["total"]
    assert (await db_session.get(User, a_id)).balance == START - cost
    xi = club["squad"]["xi"]
    assert len(xi) == 11 and [p["kind"] for p in xi].count("own") == 1 and club["squad"]["kids"] == 10
    assert len(view["pyramid"]) == bottom and view["pyramid"][0]["capacity"] == league_size
    assert (await client.post(f"{API}/manager/club", headers=a_headers, json={"name": "Второй"})).status_code == 409


async def test_young_accounts_cant_found_a_club(client, db_session, bot_token):
    config = await get_config(db_session)
    config.trade_send_min_account_age_days = 3
    await db_session.commit()
    _, headers = await _player(client, db_session, bot_token, 894002)
    resp = await client.post(f"{API}/manager/club", headers=headers, json={"name": "Фарм"})
    assert resp.status_code == 409 and "обмен" in resp.json()["error"]["message"]


async def test_catalog_buy_loan_release_one_club_at_a_time(client, db_session, bot_token):
    config = await get_config(db_session)
    star = await create_player(db_session, rating=62, position=Position.ST, display_name="Звезда Каталога")
    keeper = await create_player(db_session, rating=60, position=Position.GK, display_name="Надёжный Вратарь")
    a_id, a_headers = await _player(client, db_session, bot_token, 894011)
    b_id, b_headers = await _player(client, db_session, bot_token, 894012)
    await _club(client, a_headers, "Совы")
    await _club(client, b_headers, "Ястребы")
    terms = manager_service.npc_terms(62, config)
    before = (await client.get(f"{API}/manager", headers=a_headers)).json()["club"]["budget"]

    catalog = (await client.get(f"{API}/manager/npc", headers=a_headers, params={"line": "FWD"})).json()["players"]
    row = next(p for p in catalog if p["player_id"] == star.id)
    assert row["value"] == terms["value"] and row["taken_by"] is None
    view = (await client.post(f"{API}/manager/npc", headers=a_headers, json={"player_id": star.id, "kind": "buy", "seasons": 2})).json()
    assert view["club"]["budget"] == before - terms["value"]
    assert any(p.get("player_id") == star.id for p in view["club"]["squad"]["xi"])
    resp = await client.post(f"{API}/manager/npc", headers=b_headers, json={"player_id": star.id, "kind": "loan"})
    assert resp.status_code == 409  # one club at a time
    catalog = (await client.get(f"{API}/manager/npc", headers=b_headers, params={"q": "Звезда"})).json()["players"]
    assert catalog[0]["taken_by"] == "Совы"
    view = (await client.post(f"{API}/manager/npc", headers=b_headers, json={"player_id": keeper.id, "kind": "loan"})).json()
    assert view["club"]["npcs"][0]["kind"] == "loan"
    npc_id = (await client.get(f"{API}/manager", headers=a_headers)).json()["club"]["npcs"][0]["id"]
    view = (await client.post(f"{API}/manager/npc/{npc_id}/release", headers=a_headers)).json()
    assert view["club"]["budget"] == before - terms["value"] + terms["sell_back"] and view["club"]["npcs"] == []
    assert (await client.post(f"{API}/manager/npc", headers=b_headers, json={"player_id": star.id, "kind": "loan"})).status_code == 200


async def test_own_player_and_academy_always_start(client, db_session, bot_token):
    a_id, a_headers = await _player(client, db_session, bot_token, 894021, "CB")
    kid = await create_player(db_session, rarity=Rarity.diamond, rating=55, position=Position.CB, path_talent_code="fighter",
                              display_name="Свой Воспитанник")
    card = await create_user_card(db_session, a_id, kid.id, CardSource.seed)
    plain = await create_user_card(db_session, a_id, (await create_player(db_session, rating=80)).id, CardSource.seed)
    await db_session.commit()
    view = await _club(client, a_headers)
    assert [o["card_id"] for o in view["club"]["academy_options"]] == [card.id]
    assert (await client.patch(f"{API}/manager/club", headers=a_headers, json={"academy_card_id": plain.id})).status_code == 409
    await client.patch(f"{API}/manager/club", headers=a_headers, json={"academy_card_id": card.id})
    # Three stronger defenders from the catalog for the 4 defence slots: the
    # own player and the academy kid still start, one of the three sits.
    for name in ("Сильный Защитник 1", "Сильный Защитник 2", "Сильный Защитник 3"):
        p = await create_player(db_session, rating=65, position=Position.CB, display_name=name)
        assert (await client.post(f"{API}/manager/npc", headers=a_headers, json={"player_id": p.id, "kind": "loan"})).status_code == 200
    club = (await client.get(f"{API}/manager", headers=a_headers)).json()["club"]
    xi_kinds = {p["kind"] for p in club["squad"]["xi"]}
    assert {"own", "academy"} <= xi_kinds
    assert len(club["squad"]["bench"]) == 1 and club["squad"]["bench"][0]["name"].startswith("Сильный Защитник")


async def test_sign_transfer_and_loan_need_both_consents(client, db_session, bot_token):
    config = await get_config(db_session)
    wage_max = config.manager_live_wage_max
    a_id, a_headers = await _player(client, db_session, bot_token, 894031)
    b_id, b_headers = await _player(client, db_session, bot_token, 894032)
    p_id, p_headers = await _player(client, db_session, bot_token, 894033, "CB")
    q_id, q_headers = await _player(client, db_session, bot_token, 894034, "CM")
    await _club(client, a_headers, "Совы")
    await _club(client, b_headers, "Ястребы")
    assert (await client.post(f"{API}/manager/offers", headers=a_headers, json={"user_id": p_id, "wage": 500, "seasons": 2})).status_code == 409
    await client.post(f"{API}/manager/market", headers=p_headers, json={"open": True})
    too_much = {"user_id": p_id, "wage": wage_max + 1, "seasons": 2}
    assert (await client.post(f"{API}/manager/offers", headers=a_headers, json=too_much)).status_code == 409
    assert (await client.post(f"{API}/manager/offers", headers=a_headers, json={"user_id": p_id, "wage": 500, "seasons": 2})).status_code == 200
    view = await _accept_latest(client, p_headers)
    assert view["contract"]["club_name"] == "Совы" and not view["market_open"]
    assert view["my_value"] == manager_service.value_of(view["my_rating"], await get_config(db_session))
    a_view = (await client.get(f"{API}/manager", headers=a_headers)).json()
    assert any(p["kind"] == "live" and p["user_id"] == p_id for p in a_view["club"]["squad"]["xi"])

    market = (await client.get(f"{API}/manager/market", headers=b_headers)).json()["players"]
    value = next(p for p in market if p["user_id"] == p_id)["value"]
    assert (await client.post(f"{API}/manager/offers", headers=b_headers,
                              json={"user_id": p_id, "wage": 600, "seasons": 1, "fee": value // 3, "kind": "transfer"})).status_code == 409
    resp = await client.post(f"{API}/manager/offers", headers=b_headers,
                             json={"user_id": p_id, "wage": 600, "seasons": 1, "fee": value, "kind": "transfer"})
    assert resp.status_code == 200, resp.text
    b_budget, a_budget = resp.json()["club"]["budget"], a_view["club"]["budget"]
    incoming = (await client.get(f"{API}/manager", headers=a_headers)).json()["club"]["incoming"]
    assert incoming[0]["fee"] == value
    view = (await client.post(f"{API}/manager/offers/{incoming[0]['id']}/respond", headers=a_headers, json={"accept": True})).json()
    assert view["club"]["budget"] == a_budget  # nothing moves before the player agrees
    await _accept_latest(client, p_headers)
    a_after = (await client.get(f"{API}/manager", headers=a_headers)).json()["club"]
    b_after = (await client.get(f"{API}/manager", headers=b_headers)).json()["club"]
    assert a_after["budget"] == a_budget + value and b_after["budget"] == b_budget - value
    assert [c["user_id"] for c in b_after["contracts"]] == [p_id] and a_after["contracts"] == []
    # «Here we go!» for the deal: the player and both owners may share it, nobody else.
    deal = b_after["contracts"][0]["id"]
    shared = await client.post(f"{API}/share/prepare", headers=p_headers, json={"kind": "manager_transfer", "id": deal})
    assert shared.status_code == 200 and "Here we go" in shared.json()["caption"]
    data = Path(share_service.SHARE_DIR / shared.json()["image_url"].removeprefix("/static/share/")).read_bytes()
    assert Image.open(io.BytesIO(data)).size == (800, 800)
    assert (await client.post(f"{API}/share/prepare", headers=q_headers, json={"kind": "manager_transfer", "id": deal})).status_code == 404

    await client.post(f"{API}/manager/market", headers=q_headers, json={"open": True})
    await client.post(f"{API}/manager/offers", headers=a_headers, json={"user_id": q_id, "wage": 300, "seasons": 3})
    await _accept_latest(client, q_headers)
    resp = await client.post(f"{API}/manager/offers", headers=b_headers, json={"user_id": q_id, "wage": 400, "fee": 1000, "kind": "loan"})
    assert resp.status_code == 200, resp.text
    incoming = (await client.get(f"{API}/manager", headers=a_headers)).json()["club"]["incoming"]
    await _accept_latest(client, q_headers)
    await client.post(f"{API}/manager/offers/{incoming[0]['id']}/respond", headers=a_headers, json={"accept": True})
    rows = {c.kind: c for c in (await db_session.execute(select(ManagerContract).where(ManagerContract.user_id == q_id))).scalars().all()}
    assert rows["sign"].status == "on_loan" and rows["loan"].status == "active" and rows["loan"].seasons_left == 1


async def test_live_limit_and_trade_ban(client, db_session, bot_token):
    config = await get_config(db_session)
    config.manager_max_live = 1
    await db_session.commit()
    a_id, a_headers = await _player(client, db_session, bot_token, 894041)
    p_id, p_headers = await _player(client, db_session, bot_token, 894042)
    q_id, q_headers = await _player(client, db_session, bot_token, 894043)
    await _club(client, a_headers)
    for headers in (p_headers, q_headers):
        await client.post(f"{API}/manager/market", headers=headers, json={"open": True})
    q = await db_session.get(User, q_id)
    q.is_trade_banned = True
    await db_session.commit()
    assert (await client.post(f"{API}/manager/offers", headers=a_headers, json={"user_id": q_id, "wage": 100, "seasons": 1})).status_code == 409
    assert (await client.post(f"{API}/manager/offers", headers=a_headers, json={"user_id": p_id, "wage": 100, "seasons": 1})).status_code == 200
    resp = await client.post(f"{API}/manager/offers", headers=a_headers, json={"user_id": q_id, "wage": 0, "seasons": 1})
    assert resp.status_code == 409 and "не больше 1" in resp.json()["error"]["message"]


async def test_season_wages_auto_signings_digests_and_promotion(client, db_session, bot_token):
    config = await get_config(db_session)
    bottom = config.manager_divisions
    target = config.manager_division_rating[bottom - 1]
    rounds, size = manager_service.rounds_of(config), manager_service.league_size(config)
    eur_per_coin, per_day = config.manager_wage_eur_per_coin, len(manager_service.slots_of(config))
    grant = config.manager_division_budget[bottom - 1]
    for position in (Position.GK, Position.CB, Position.CB, Position.LB, Position.RB, Position.CM, Position.CDM, Position.CAM,
                     Position.LW, Position.RW, Position.ST) * 2:
        await create_player(db_session, rating=target, position=position)
    a_id, a_headers = await _player(client, db_session, bot_token, 894051)
    b_id, b_headers = await _player(client, db_session, bot_token, 894052)
    p_id, p_headers = await _player(client, db_session, bot_token, 894053, "CB")
    await _club(client, a_headers, "Совы")
    await _club(client, b_headers, "Ястребы")
    await client.post(f"{API}/manager/market", headers=p_headers, json={"open": True})
    await client.post(f"{API}/manager/offers", headers=a_headers, json={"user_id": p_id, "wage": 700, "seasons": 1})
    await _accept_latest(client, p_headers)
    p_before = (await db_session.get(User, p_id)).balance
    a_budget = (await client.get(f"{API}/manager", headers=a_headers)).json()["club"]["budget"]

    start = _next_season_start(config)
    assert await manager_service.ensure_season(db_session, start - timedelta(minutes=10)) is False  # still preseason
    assert await manager_service.ensure_season(db_session, start) is True
    assert await manager_service.ensure_season(db_session, start) is False  # once per season
    db_session.expire_all()
    assert (await db_session.get(User, p_id)).balance == p_before + 700  # coins to the player
    clubs = (await db_session.execute(select(ManagerClub).order_by(ManagerClub.id))).scalars().all()
    # … and their euros out of the budget (plus this season's grant, minus the automatic loans).
    assert clubs[0].budget <= a_budget + grant - 700 * eur_per_coin
    league_id, club_ids = clubs[0].league_id, [c.id for c in clubs]
    assert league_id and clubs[1].league_id == league_id
    league = await db_session.get(ManagerLeague, league_id)
    assert len(league.state["teams"]) == size and len(league.state["fixtures"]) == rounds
    assert datetime.fromisoformat(league.state["schedule"][0]) > start
    auto = (await db_session.execute(select(ManagerNpc).where(ManagerNpc.auto.is_(True)))).scalars().all()
    assert auto
    for n in auto:
        assert abs((await db_session.get(Player, n.player_id)).rating - target) <= manager_service.AUTO_RANGE and n.kind == "loan"
    team = next(t for t in league.state["teams"] if t["club_id"] == club_ids[0])
    kinds = [p["kind"] for p in team["xi"]]
    assert kinds.count("own") == 1 and kinds.count("live") == 1 and kinds.count("npc") >= 1
    # (a season of the real current week may have started too, from the views above)
    assert (await db_session.execute(select(ManagerValueHistory).where(ManagerValueHistory.user_id == p_id))).scalars().all()
    resp = await client.post(f"{API}/manager/npc", headers=a_headers, json={"player_id": auto[0].player_id, "kind": "loan"})
    assert resp.status_code == 409  # no trading during the season

    assert await manager_service.resolve_league(db_session, league_id, now=start + timedelta(days=7)) == rounds
    db_session.expire_all()
    league = await db_session.get(ManagerLeague, league_id)
    assert league.status == "finished"
    digests = (await db_session.execute(
        select(Notification).where(Notification.user_id == a_id, Notification.type == NotificationType.manager_event,
                                   Notification.title.like("%итоги дня%"))
    )).scalars().all()
    days = {datetime.fromisoformat(at).astimezone(manager_service.app_timezone()).date() for at in league.state["schedule"]}
    assert len(digests) == len(days) - 1  # one a day (the last day ends with the season), not one per match
    assert len(days) == rounds // per_day  # 3 rounds a day
    season = await db_session.get(ManagerSeason, league.season_key)
    assert season.settled_at is not None
    for place, row in enumerate(manager_service.standings(league.state), start=1):
        team = league.state["teams"][row["team_index"]]
        if team["club_id"]:
            club = await db_session.get(ManagerClub, team["club_id"])
            # The divisions above are empty: the top half of the league goes up — one division only.
            assert club.division == (bottom - 1 if place <= size // 2 else bottom) and club.seasons_played == 1
    contract = (await db_session.execute(select(ManagerContract).where(ManagerContract.user_id == p_id))).scalar_one()
    assert contract.status == "ended" and contract.matches_played == rounds


async def test_full_division_relegates_twice_as_many_as_each_league_promotes(client, db_session, bot_token):
    """Division 1 full (one league of 4): its bottom 2 go down, the top 1 of
    each of the 2 leagues below comes up — the ×2 pyramid holds."""
    config = await get_config(db_session)
    config.manager_league_size, config.manager_divisions, config.manager_promote = 4, 2, 1
    await db_session.commit()
    owners = []
    for i in range(12):
        uid, _ = await _player(client, db_session, bot_token, 894100 + i)
        owners.append(uid)
    clubs = []
    for i, uid in enumerate(owners):
        club = ManagerClub(owner_id=uid, name=f"Клуб {i}", division=1 if i < 4 else 2, budget=0, look={})
        db_session.add(club)
        clubs.append(club)
    db_session.add(ManagerSeason(key="2030-W01", depth=2))
    await db_session.flush()

    def league_of(division, members):
        teams = [{"index": n, "club_id": c.id, "name": c.name, "owner_name": "x"} for n, c in enumerate(members)]
        # Index 0 beats everyone, 1 beats 2-3, 2 beats 3.
        results = [[{"home": a, "away": b, "hs": 1, "as": 0}] for a in range(4) for b in range(a + 1, 4)]
        return ManagerLeague(season_key="2030-W01", division=division, status="finished",
                             state={"teams": teams, "fixtures": [], "schedule": [], "results": results})

    db_session.add(league_of(1, clubs[:4]))
    db_session.add(league_of(2, clubs[4:8]))
    db_session.add(league_of(2, clubs[8:12]))
    await db_session.commit()
    ids = [c.id for c in clubs]
    await manager_service._settle(db_session, "2030-W01", await get_config(db_session))
    await db_session.commit()
    db_session.expire_all()
    division = {cid: (await db_session.get(ManagerClub, cid)).division for cid in ids}
    assert [division[c] for c in ids[:4]] == [1, 1, 2, 2]
    assert division[ids[4]] == 1 and division[ids[8]] == 1
    assert all(division[c] == 2 for c in ids[5:8] + ids[9:12])


async def test_style_shop_merch_and_pro(client, db_session, bot_token):
    config = await get_config(db_session)
    lion = next(i for i in manager_shop.catalog(config) if i["code"] == "symbol_lion")
    scarf = next(i for i in manager_shop.merch_items(config) if i["code"] == "scarf")
    found_cost, pro_stars = config.manager_found_cost, config.manager_pro_stars
    a_id, a_headers = await _player(client, db_session, bot_token, 894201)
    fan_id, fan_headers = await _player(client, db_session, bot_token, 894202)
    view = await _club(client, a_headers)
    club_id, budget = view["club"]["id"], view["club"]["budget"]
    assert (await client.patch(f"{API}/manager/look", headers=a_headers, json={"symbol": "🦁"})).status_code == 409  # not bought
    assert (await client.post(f"{API}/manager/shop/symbol_lion", headers=a_headers)).status_code == 200
    view = (await client.patch(f"{API}/manager/look", headers=a_headers, json={"symbol": "🦁", "color": "#c62828"})).json()
    assert view["club"]["look"]["symbol"] == "🦁" and view["club"]["look"]["color"] == "#c62828"
    assert (await client.patch(f"{API}/manager/look", headers=a_headers, json={"color": "#123456"})).status_code == 409
    db_session.expire_all()
    assert (await db_session.get(User, a_id)).balance == START - found_cost - lion["coins"]

    # A fan buys a scarf: his coins burn, the club gets euros; once per item; not one's own.
    card = (await client.post(f"{API}/manager/clubs/{club_id}/merch/scarf", headers=fan_headers)).json()
    assert card["fans"] == 1 and next(m for m in card["merch"] if m["code"] == "scarf")["bought"]
    assert (await client.post(f"{API}/manager/clubs/{club_id}/merch/scarf", headers=fan_headers)).status_code == 409
    assert (await client.post(f"{API}/manager/clubs/{club_id}/merch/scarf", headers=a_headers)).status_code == 409
    db_session.expire_all()
    assert (await db_session.get(User, fan_id)).balance == START - scarf["coins"]
    assert (await db_session.get(ManagerClub, club_id)).budget == budget + scarf["eur"]
    assert (await client.get(f"{API}/manager/popular", headers=fan_headers)).json()["clubs"][0]["id"] == club_id

    # «Менеджер Pro» through Stars: the scout opens, the gold frame becomes usable.
    assert (await client.get(f"{API}/manager/scout", headers=a_headers)).status_code == 403
    config = await get_config(db_session)
    a = await db_session.get(User, a_id)
    invoice = SimpleNamespace(user_id=a_id, my_player_purchase="manager:pro", stars_amount=pro_stars)
    assert (await manager_shop.validate_stars(db_session, invoice, config))[0]
    await manager_shop.deliver_stars(db_session, a, invoice, config)
    gold = SimpleNamespace(user_id=a_id, my_player_purchase="manager:frame_gold", stars_amount=999)
    assert not (await manager_shop.validate_stars(db_session, gold, config))[0]  # wrong price
    await db_session.commit()
    assert (await client.get(f"{API}/manager/scout", headers=a_headers)).status_code == 200
    view = (await client.patch(f"{API}/manager/look", headers=a_headers, json={"frame": "gold"})).json()
    assert view["club"]["pro"] and view["club"]["look"]["frame"] == "gold"
    assert not (await db_session.execute(select(ManagerCosmetic).where(ManagerCosmetic.code == "frame_gold"))).scalars().all()

    # The value share card.
    shared = await client.post(f"{API}/share/prepare", headers=a_headers, json={"kind": "manager_player", "id": 0})
    assert shared.status_code == 200 and "€" in shared.json()["caption"]


async def test_tactics_formation_style_and_the_style_circle(client, db_session, bot_token):
    config = await get_config(db_session)
    edge_pct = config.manager_style_edge_pct
    # Атака beats Оборона: its lines plus the edge; Оборона gets only its own lines.
    attack = manager_tactics.modifiers("attacking", "4-3-3", "defensive", config)
    assert attack == {"GK": -4 + edge_pct, "DEF": -4 + edge_pct, "MID": 2 + edge_pct, "FWD": 6 + edge_pct}
    assert manager_tactics.modifiers("defensive", "4-3-3", "attacking", config)["DEF"] == 6
    assert manager_tactics.edge("counter", "attacking") == "win" and manager_tactics.edge("attacking", "counter") == "lose"
    assert manager_tactics.edge("attacking", "possession") == "even"
    # A formation tilts attack vs defense (3-4-3 more attack, 5-3-2 more defense).
    assert manager_tactics.modifiers("possession", "3-4-3", "possession", config)["FWD"] > 0
    assert manager_tactics.modifiers("possession", "5-3-2", "possession", config)["DEF"] > 0

    a_id, a_headers = await _player(client, db_session, bot_token, 894301, "CM")
    await _club(client, a_headers)
    assert (await client.patch(f"{API}/manager/club", headers=a_headers, json={"style": "chaos"})).status_code == 409
    view = (await client.patch(f"{API}/manager/club", headers=a_headers, json={"formation": "3-5-2", "style": "counter"})).json()
    club = view["club"]
    assert club["formation"] == "3-5-2" and club["style"] == "counter" and club["squad"]["formation"] == "3-5-2"
    assert sum(1 for p in club["squad"]["xi"] if p["slot"].startswith("MID")) == 5  # the formation's slots
    assert [s["value"] for s in view["rules"]["tactics"]["styles"]] == list(manager_tactics.STYLES)
    # The own player's picture data for the pitch.
    own = next(p for p in club["squad"]["xi"] if p["kind"] == "own")
    assert own["appearance"] and own["number"] == 9
