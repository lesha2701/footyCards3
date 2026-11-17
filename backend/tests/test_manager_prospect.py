"""«Воспитанник Академии» in «Менеджер»: plays for his owner's club once old
enough (optionally always in the XI), goes on the free-agent market with
«Ищу клуб», signs for another club with the owner's consent and earns XP
from club matches."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.academy_prospect import AcademyProspect
from app.models.manager_club import ManagerContract
from app.services import manager_service, prospect_service
from app.services.game_config_service import get_config
from tests.test_manager import _accept_latest, _club, _player

API = "/api/v1"
pytestmark = pytest.mark.usefixtures("trade_guards_off")
LOOK = {"skin": 1, "hair": 1, "hair_color": 1, "beard": 0, "eye_color": 0, "kit": 0, "kit_pattern": 0}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


@pytest.fixture(autouse=True)
def _no_season_at_the_real_clock(monkeypatch):
    real = manager_service.ensure_season

    async def ensure(db, now=None):
        if now is None or abs(now - datetime.now(timezone.utc)) < timedelta(hours=1):
            return False
        return await real(db, now)

    monkeypatch.setattr(manager_service, "ensure_season", ensure)


async def _prospect(client, db_session, headers, user_id, days=30, position="ST"):
    resp = await client.post(f"{API}/prospect", headers=headers,
                             json={"name": "Лёва Мяч", "number": 7, "position": position, "foot": "left", "appearance": LOOK})
    assert resp.status_code == 200, resp.text
    p = (await db_session.execute(select(AcademyProspect).where(AcademyProspect.user_id == user_id))).scalar_one()
    p.created_at = datetime.now(timezone.utc) - timedelta(days=days)
    p.xp = 20_000
    await db_session.commit()
    return p


def _all(view):
    squad = view["club"]["squad"]
    return [*squad["xi"], *squad["bench"]]


async def test_too_young_prospect_is_not_in_the_club_nor_on_the_market(client, db_session, bot_token):
    a_id, a_headers = await _player(client, db_session, bot_token, 897001)
    await _club(client, a_headers, "Совы")
    await _prospect(client, db_session, a_headers, a_id, days=0)
    view = (await client.get(f"{API}/manager", headers=a_headers)).json()
    assert view["prospect"]["eligible"] is False and view["prospect"]["age"] == 6
    assert not any(p["kind"] == "prospect" for p in _all(view))
    resp = await client.post(f"{API}/manager/market", headers=a_headers, json={"open": True, "subject": "prospect"})
    assert resp.status_code == 409


async def test_own_prospect_plays_for_the_owner_and_may_always_start(client, db_session, bot_token):
    a_id, a_headers = await _player(client, db_session, bot_token, 897011)
    await _club(client, a_headers, "Совы")
    await _prospect(client, db_session, a_headers, a_id)
    view = (await client.get(f"{API}/manager", headers=a_headers)).json()
    assert view["prospect"]["eligible"] is True and view["prospect"]["age"] >= 9
    entry = next(p for p in _all(view) if p["kind"] == "prospect")
    assert entry["user_id"] == a_id and entry["subject"] == "prospect" and entry["starts"] is False
    resp = await client.patch(f"{API}/manager/club", headers=a_headers, json={"prospect_starts": True})
    assert resp.status_code == 200, resp.text
    xi = resp.json()["club"]["squad"]["xi"]
    assert any(p["kind"] == "prospect" and p["starts"] for p in xi)
    assert resp.json()["club"]["prospect_starts"] is True
    # Nobody offers your own prospect to your own club.
    resp = await client.post(f"{API}/manager/offers", headers=a_headers,
                             json={"user_id": a_id, "subject": "prospect", "wage": 100, "seasons": 1})
    assert resp.status_code == 409


async def test_prospect_signs_for_another_club_with_consent(client, db_session, bot_token):
    a_id, a_headers = await _player(client, db_session, bot_token, 897021)
    p_id, p_headers = await _player(client, db_session, bot_token, 897022)
    await _club(client, a_headers, "Совы")
    await _prospect(client, db_session, p_headers, p_id)
    offer = {"user_id": p_id, "subject": "prospect", "wage": 200, "seasons": 2}
    assert (await client.post(f"{API}/manager/offers", headers=a_headers, json=offer)).status_code == 409  # not on the market
    resp = await client.post(f"{API}/manager/market", headers=p_headers, json={"open": True, "subject": "prospect"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["prospect"]["market_open"] is True and not resp.json()["market_open"]  # «Мой игрок» stays off
    market = (await client.get(f"{API}/manager/market", headers=a_headers)).json()["players"]
    listed = [p for p in market if p["user_id"] == p_id]
    assert [p["subject"] for p in listed] == ["prospect"] and listed[0]["player_name"] == "Лёва Мяч"
    assert (await client.post(f"{API}/manager/offers", headers=a_headers, json=offer)).status_code == 200
    mine = (await client.get(f"{API}/manager", headers=p_headers)).json()
    assert mine["offers"][0]["subject"] == "prospect"
    view = await _accept_latest(client, p_headers)
    assert view["prospect"]["contract"]["club_name"] == "Совы" and not view["prospect"]["market_open"]
    assert view["contract"] is None  # his «Мой игрок» is still free
    a_view = (await client.get(f"{API}/manager", headers=a_headers)).json()
    entry = next(p for p in _all(a_view) if p.get("user_id") == p_id)
    assert entry["kind"] == "live" and entry["subject"] == "prospect"
    rows = (await db_session.execute(select(ManagerContract).where(ManagerContract.user_id == p_id))).scalars().all()
    assert [(r.subject, r.status) for r in rows] == [("prospect", "active")]
    # His «Мой игрок» may sign for the same club on a separate contract.
    await client.post(f"{API}/manager/market", headers=p_headers, json={"open": True})
    resp = await client.post(f"{API}/manager/offers", headers=a_headers, json={"user_id": p_id, "wage": 200, "seasons": 1})
    assert resp.status_code == 200, resp.text


async def test_owner_club_loses_the_prospect_while_he_plays_elsewhere(client, db_session, bot_token):
    a_id, a_headers = await _player(client, db_session, bot_token, 897031)
    p_id, p_headers = await _player(client, db_session, bot_token, 897032)
    await _club(client, a_headers, "Совы")
    await _club(client, p_headers, "Ястребы")
    await _prospect(client, db_session, p_headers, p_id)
    own = (await client.get(f"{API}/manager", headers=p_headers)).json()
    assert any(p["kind"] == "prospect" for p in _all(own))
    await client.post(f"{API}/manager/market", headers=p_headers, json={"open": True, "subject": "prospect"})
    await client.post(f"{API}/manager/offers", headers=a_headers, json={"user_id": p_id, "subject": "prospect", "wage": 100, "seasons": 1})
    await _accept_latest(client, p_headers)
    own = (await client.get(f"{API}/manager", headers=p_headers)).json()
    assert not any(p.get("user_id") == p_id and p.get("subject") == "prospect" for p in _all(own))


async def test_club_match_xp_is_capped_and_counted(client, db_session, bot_token):
    a_id, a_headers = await _player(client, db_session, bot_token, 897041)
    p = await _prospect(client, db_session, a_headers, a_id)
    c = prospect_service.cfg(await get_config(db_session))
    before = p.xp
    gained = await prospect_service.award_manager(db_session, a_id, 2)
    await db_session.commit()
    assert gained > 0
    p = (await db_session.execute(
        select(AcademyProspect).where(AcademyProspect.user_id == a_id).execution_options(populate_existing=True))).scalar_one()
    assert p.xp == before + gained and p.stats["club_matches"] == 1 and p.stats["club_goals"] == 2
    assert any(m["code"] == "club_debut" for m in p.memories)
    # The daily cap holds for club matches too.
    for _ in range(20):
        await prospect_service.award_manager(db_session, a_id, 3)
    await db_session.commit()
    p = (await db_session.execute(
        select(AcademyProspect).where(AcademyProspect.user_id == a_id).execution_options(populate_existing=True))).scalar_one()
    assert p.xp_today <= int(c["daily_xp_cap"])
