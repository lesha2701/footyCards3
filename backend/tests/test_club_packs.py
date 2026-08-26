import pytest_asyncio

from app.models.enums import Position
from tests.factories import create_player
from tests.utils import telegram_headers


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """club_service.create_club seeds a starting squad on every club
    creation (Task 4) — give every test in this file enough active players
    per formation category (GK/DEF/MID/FWD) to draw from. autouse fixtures
    are file-scoped in this codebase's test setup (see test_clubs.py and
    test_club_squad.py precedent), so it must be repeated here rather than
    relying on the per-test inline `create_player` calls below, which only
    seed generic ST/common players for the pack's own rarity rolls and are
    not enough to cover every formation slot's required positions (fresh
    SQLite schema per test, see conftest.py's `_fresh_schema`)."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _admin_auth(client, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    return {"Authorization": f"Bearer {session_resp.json()['admin_token']}"}


async def _register_only(client, bot_token, telegram_id):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200


async def _create_club(client, bot_token, telegram_id, name):
    await _register_only(client, bot_token, telegram_id)
    headers = telegram_headers(telegram_id, bot_token)
    resp = await client.post(
        "/api/v1/clubs", headers=headers,
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    return resp.json(), headers


async def test_open_club_pack_debits_budget_and_mints_cards(client, db_session, bot_token):
    admin_auth = await _admin_auth(client, bot_token)
    for _ in range(5):
        await create_player(db_session)
    pack_resp = await client.post(
        "/api/v1/admin/club-packs", headers=admin_auth,
        json={
            "slug": "club-test-pack", "name": "Тестовый клубный пак", "price": 100, "card_count": 2,
            "rarity_probabilities": [{"rarity": "common", "probability": 1.0}],
        },
    )
    pack_id = pack_resp.json()["id"]

    club, headers = await _create_club(client, bot_token, 820400, "Клуб с паками")
    # Give the club enough budget via the daily claim (200 coins by default) — not enough
    # for a 100-coin pack twice, but enough to open once and verify the debit.
    await client.post("/api/v1/clubs/me/daily-claim", headers=headers)

    open_resp = await client.post(f"/api/v1/clubs/me/packs/{pack_id}/open", headers=headers, json={"idempotency_key": "test-key-1"})
    assert open_resp.status_code == 200
    body = open_resp.json()
    assert body["new_budget"] == 100  # 200 - 100
    assert len(body["cards"]) == 2

    cards_resp = await client.get("/api/v1/clubs/me/cards", headers=headers)
    assert len(cards_resp.json()) == 17  # 15 starting + 2 from the pack


async def test_open_club_pack_idempotency_key_prevents_double_charge(client, db_session, bot_token):
    admin_auth = await _admin_auth(client, bot_token)
    for _ in range(5):
        await create_player(db_session)
    pack_resp = await client.post(
        "/api/v1/admin/club-packs", headers=admin_auth,
        json={
            "slug": "club-idem-pack", "name": "Идемпотентный пак", "price": 50, "card_count": 1,
            "rarity_probabilities": [{"rarity": "common", "probability": 1.0}],
        },
    )
    pack_id = pack_resp.json()["id"]
    club, headers = await _create_club(client, bot_token, 820401, "Клуб с идемпотентностью")
    await client.post("/api/v1/clubs/me/daily-claim", headers=headers)

    first = await client.post(f"/api/v1/clubs/me/packs/{pack_id}/open", headers=headers, json={"idempotency_key": "same-key"})
    second = await client.post(f"/api/v1/clubs/me/packs/{pack_id}/open", headers=headers, json={"idempotency_key": "same-key"})
    assert first.json()["opening_id"] == second.json()["opening_id"]
    assert first.json()["new_budget"] == second.json()["new_budget"]


async def test_open_club_pack_fails_on_insufficient_budget(client, db_session, bot_token):
    admin_auth = await _admin_auth(client, bot_token)
    for _ in range(5):
        await create_player(db_session)
    pack_resp = await client.post(
        "/api/v1/admin/club-packs", headers=admin_auth,
        json={
            "slug": "club-expensive-pack", "name": "Дорогой пак", "price": 999999, "card_count": 1,
            "rarity_probabilities": [{"rarity": "common", "probability": 1.0}],
        },
    )
    pack_id = pack_resp.json()["id"]
    club, headers = await _create_club(client, bot_token, 820402, "Бедный клуб")

    resp = await client.post(f"/api/v1/clubs/me/packs/{pack_id}/open", headers=headers, json={})
    assert resp.status_code == 400
