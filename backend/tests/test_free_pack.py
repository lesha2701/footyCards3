from app.models.enums import Rarity
from tests.factories import create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def test_free_pack_available_for_new_user(client, db_session, bot_token):
    await _register(client, db_session, 850001, bot_token)
    headers = telegram_headers(850001, bot_token)

    resp = await client.get("/api/v1/free-pack/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["available"] is True
    assert resp.json()["available_at"] is None


async def test_free_pack_claim_grants_card_and_sets_next_available_at(client, db_session, bot_token):
    for _ in range(3):
        await create_player(db_session, rarity=Rarity.common)
    await create_pack(db_session, "basic", price=100, card_count=3, probabilities={Rarity.common: 1.0})

    await _register(client, db_session, 850002, bot_token)
    headers = telegram_headers(850002, bot_token)

    resp = await client.post("/api/v1/free-pack/claim", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["pack"]["name"] == "Basic"
    assert len(body["cards"]) == 3

    status_resp = await client.get("/api/v1/free-pack/status", headers=headers)
    assert status_resp.json()["available"] is False
    assert status_resp.json()["available_at"] is not None


async def test_free_pack_claim_twice_immediately_is_rejected(client, db_session, bot_token):
    await create_player(db_session, rarity=Rarity.common)
    await create_pack(db_session, "basic", price=100, card_count=1, probabilities={Rarity.common: 1.0})

    await _register(client, db_session, 850003, bot_token)
    headers = telegram_headers(850003, bot_token)

    first = await client.post("/api/v1/free-pack/claim", headers=headers)
    assert first.status_code == 200
    second = await client.post("/api/v1/free-pack/claim", headers=headers)
    assert second.status_code == 409


async def test_free_pack_available_again_after_interval_elapses(client, db_session, bot_token):
    await create_player(db_session, rarity=Rarity.common)
    await create_pack(db_session, "basic", price=100, card_count=1, probabilities={Rarity.common: 1.0})

    user = await _register(client, db_session, 850004, bot_token)
    headers = telegram_headers(850004, bot_token)

    await client.post("/api/v1/free-pack/claim", headers=headers)

    from datetime import timedelta

    await db_session.refresh(user)
    user.free_pack_available_at = user.free_pack_available_at - timedelta(hours=9)
    db_session.add(user)
    await db_session.commit()

    resp = await client.post("/api/v1/free-pack/claim", headers=headers)
    assert resp.status_code == 200
