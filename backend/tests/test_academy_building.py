"""«Академия» building (services/academy_service.py): timed wing upgrades for
coins, one construction at a time, Stars speed-up, wing effects on the path
(experience, attempts, task targets), the pack (scout) and the showcase
(hall), the scouting report and the leaderboard."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.card_path import UserAcademy
from app.models.enums import CardSource, Position, Rarity
from app.models.game_config import GameConfig
from app.services import academy_service, path_service
from app.services.card_creation import create_user_card
from app.services.pack_service import scout_adjusted
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _config(db_session, **overrides) -> GameConfig:
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
    for key, value in overrides.items():
        setattr(config, key, value)
    await db_session.commit()
    return config


async def _login(client, db_session, bot_token, telegram_id, balance=100_000):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, telegram_id)
    user.balance = balance
    await db_session.commit()
    return headers, user


async def _academy(db_session, user_id) -> UserAcademy:
    return (await db_session.execute(
        select(UserAcademy).where(UserAcademy.user_id == user_id).execution_options(populate_existing=True)
    )).scalar_one()


async def _finish_now(db_session, user_id):
    academy = await _academy(db_session, user_id)
    academy.build_ends_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()


async def test_upgrade_charges_coins_runs_a_timer_and_completes_lazily(client, db_session, bot_token):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 990101, balance=10_000)
    resp = await client.post("/api/v1/academy/wings/training/upgrade", headers=headers, json={"idempotency_key": "u1"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["construction"]["building_code"] == "training" and body["construction"]["to_level"] == 1
    assert body["construction"]["speedup_stars"] == 2 and body["new_balance"] == 8_000
    replay = await client.post("/api/v1/academy/wings/training/upgrade", headers=headers, json={"idempotency_key": "u1"})
    assert replay.status_code == 200 and replay.json()["new_balance"] == 8_000
    busy = await client.post("/api/v1/academy/wings/dorm/upgrade", headers=headers, json={})
    assert busy.status_code == 409  # one construction at a time

    await _finish_now(db_session, user.id)
    state = (await client.get("/api/v1/academy", headers=headers)).json()
    wing = next(w for w in state["wings"] if w["code"] == "training")
    assert wing["level"] == 1 and state["construction"] is None and state["level"] == 1
    assert state["effects"]["training"] == 4
    nxt = await client.post("/api/v1/academy/wings/dorm/upgrade", headers=headers, json={})
    assert nxt.status_code == 200
    assert (await _academy(db_session, user.id)).levels == {"training": 1}


async def test_not_enough_coins_and_max_level(client, db_session, bot_token):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 990102, balance=100)
    assert (await client.post("/api/v1/academy/wings/scout/upgrade", headers=headers, json={})).status_code in (400, 402, 409)
    user.balance = 10**7
    await db_session.commit()
    for _ in range(5):
        assert (await client.post("/api/v1/academy/wings/hall/upgrade", headers=headers, json={})).status_code == 200
        await _finish_now(db_session, user.id)
    assert (await client.post("/api/v1/academy/wings/hall/upgrade", headers=headers, json={})).status_code == 409
    state = (await client.get("/api/v1/academy", headers=headers)).json()
    assert state["showcase_slots"] == 3 + 5


async def test_stars_speedup_finishes_the_construction(client, db_session, bot_token, monkeypatch):
    from app.services import stars_payment_service

    async def fake_link(*args, **kwargs):
        return "https://t.me/invoice/x"

    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", fake_link)
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 990103)
    await client.post("/api/v1/academy/wings/scout/upgrade", headers=headers, json={})
    inv = await client.post("/api/v1/academy/speedup-invoice", headers=headers)
    assert inv.status_code == 200, inv.text
    token, stars = inv.json()["payload_token"], inv.json()["stars_amount"]
    assert stars == 2
    ok, _ = await stars_payment_service.validate_pre_checkout(db_session, token, stars)
    assert ok
    await stars_payment_service.deliver_payment(db_session, token, user.telegram_id, "ch-academy-1", stars)
    academy = await _academy(db_session, user.id)
    assert academy.levels == {"scout": 1} and academy.building_code is None


async def test_wings_shape_the_path(client, db_session, bot_token):
    config = await _config(db_session, path_daily_free_arena=1)
    _headers, user = await _login(client, db_session, bot_token, 990104)
    db_session.add(UserAcademy(user_id=user.id, levels={"training": 5, "dorm": 5, "staff": 5}, total_level=15))
    await db_session.commit()
    player = await create_player(db_session, rarity=Rarity.diamond, rating=60, path_talent_code="fighter")
    card = await create_user_card(db_session, user.id, player.id, CardSource.seed)
    await db_session.commit()
    statuses = []
    for i in range(5):
        res = await path_service.award_match(
            db_session, user_id=user.id, source_type="arena", source_id=str(i),
            entries=[path_service.MatchEntry(card.id, "win")], config=config,
        )
        await db_session.commit()
        statuses.append(res[0])
    # 1 free + 3 from the dorm (level 5 → +3); +20% experience.
    assert [r.status for r in statuses] == ["awarded"] * 4 + ["no_attempts"]
    assert statuses[0].xp == 24
    catalog = await path_service.load_catalog(db_session)
    assert path_service.task_target(30, 25) == 23 and path_service.task_target(1, 25) == 1
    tasks = path_service.tasks_status(catalog, 0, {}, Position.ST, 25)
    assert {t["metric"]: t["target"] for t in tasks} == {"matches": 23, "wins": 9}


def test_scout_raises_the_academy_share_of_a_pack():
    rows = [NS(rarity=Rarity.common, probability=0.6), NS(rarity=Rarity.epic, probability=0.35),
            NS(rarity=Rarity.diamond, probability=0.05)]
    adjusted = {r.rarity: round(r.probability, 4) for r in scout_adjusted(rows, 0.05)}
    assert adjusted[Rarity.diamond] == 0.10
    assert round(sum(adjusted.values()), 6) == 1.0
    assert adjusted[Rarity.common] == round(0.6 * 0.9 / 0.95, 4)
    assert scout_adjusted(rows, 0) == rows


async def test_scouting_report_card_or_coins_and_cooldown(client, db_session, bot_token, monkeypatch):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 990105, balance=0)
    db_session.add(UserAcademy(user_id=user.id, levels={"scout": 1}, total_level=1))
    await db_session.commit()
    await create_player(db_session, rarity=Rarity.diamond, path_talent_code="captain", position=Position.CM)

    monkeypatch.setattr(academy_service.random, "random", lambda: 0.99)  # miss → coins
    first = await client.post("/api/v1/academy/scout-report", headers=headers, json={"idempotency_key": "r1"})
    assert first.status_code == 200, first.text
    assert first.json()["report"] == {"coins": 200} and first.json()["new_balance"] == 200
    again = await client.post("/api/v1/academy/scout-report", headers=headers, json={})
    assert again.status_code == 409  # cooldown

    academy = await _academy(db_session, user.id)
    academy.scout_report_at = datetime.now(timezone.utc) - timedelta(days=8)
    await db_session.commit()
    monkeypatch.setattr(academy_service.random, "random", lambda: 0.0)  # hit → card
    hit = await client.post("/api/v1/academy/scout-report", headers=headers, json={})
    assert hit.status_code == 200 and "card_id" in hit.json()["report"]


async def test_academy_level_leaderboard(client, db_session, bot_token):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 990106)
    db_session.add(UserAcademy(user_id=user.id, levels={"scout": 2, "hall": 1}, total_level=3))
    await db_session.commit()
    resp = await client.get("/api/v1/leaderboard/ranking", headers=headers, params={"metric": "academy_level"})
    assert resp.status_code == 200 and resp.json()["top"][0]["value"] == 3
