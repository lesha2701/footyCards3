from datetime import date

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module

from app.models.user import User
from app.models.user_activity import SectionTimeDaily
from app.services import section_time_service
from app.services.admin_analytics_service import analytics_report
from tests.utils import telegram_headers

API = "/api/v1"
URL = f"{API}/activity/time"


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _rows(db, user_id: int) -> dict[str, int]:
    rows = (await db.execute(select(SectionTimeDaily).where(SectionTimeDaily.user_id == user_id))).scalars().all()
    return {r.section: r.seconds for r in rows}


async def _login(client, tg_id: int, bot_token: str) -> dict:
    headers = telegram_headers(tg_id, bot_token)
    assert (await client.post(f"{API}/auth/session", headers=headers)).status_code == 200
    return headers


async def test_batches_add_up_per_section_and_day(client, db_session, bot_token):
    headers = await _login(client, 870001, bot_token)
    first = await client.post(URL, headers=headers, json={"sections": {"home": 20, "play/penalty": 30}})
    assert first.status_code == 200
    assert first.json()["stored"] == {"home": 20, "play/penalty": 30}
    await client.post(URL, headers=headers, json={"sections": {"play/penalty": 40}})
    user_id = (await db_session.execute(select(User.id).where(User.telegram_id == 870001))).scalar_one()
    db_session.expire_all()
    assert await _rows(db_session, user_id) == {"home": 20, "play/penalty": 70}


async def test_a_batch_is_capped_and_odd_keys_are_dropped():
    batch = section_time_service.clean({
        "play/penalty": 500, "home": 30, "../etc": 10, "Bad Key": 5, "packs": -3, "a/b/c": 4,
    })
    # The biggest section takes the whole cap, nothing is left for the rest.
    assert batch == {"play/penalty": section_time_service.MAX_BATCH_SECONDS}
    many = section_time_service.clean({f"s{i}": 1 for i in range(40)})
    assert len(many) == section_time_service.MAX_SECTIONS


async def test_rate_limited_after_a_few_batches_a_minute(client, bot_token):
    headers = await _login(client, 870002, bot_token)
    codes = [(await client.post(URL, headers=headers, json={"sections": {"home": 5}})).status_code for _ in range(4)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429


async def test_needs_auth(client):
    assert (await client.post(URL, json={"sections": {"home": 5}})).status_code == 401


async def test_report_sums_sections_in_the_window(db_session):
    a = User(telegram_id=870101, username="st_a", balance=0)
    b = User(telegram_id=870102, username="st_b", balance=0)
    db_session.add_all([a, b])
    await db_session.flush()
    today = date(2026, 10, 10)
    await section_time_service.record(db_session, a.id, {"play/penalty": 60}, day=today)
    await section_time_service.record(db_session, a.id, {"play/penalty": 60}, day=date(2026, 10, 9))
    await section_time_service.record(db_session, b.id, {"play/penalty": 60, "home": 30}, day=today)
    # Outside a 7-day window.
    await section_time_service.record(db_session, b.id, {"town": 70}, day=date(2026, 9, 1))

    report = await analytics_report(db_session, 7, today=today)
    rows = {r["section"]: r for r in report["section_time"]}
    assert list(rows) == ["play/penalty", "home"]
    assert rows["play/penalty"] == {
        "section": "play/penalty", "players": 2, "seconds": 180, "minutes_per_player_day": 1.0,
    }
    # b's batch hit the 75 s cap: 60 + 15.
    assert rows["home"]["seconds"] == 15
