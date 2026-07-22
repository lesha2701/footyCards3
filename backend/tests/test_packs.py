import pytest
from sqlalchemy import select

from app.models.card import UserCard
from app.models.enums import Rarity
from tests.factories import create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def test_open_pack_success(client, db_session, bot_token):
    for _ in range(5):
        await create_player(db_session, rarity=Rarity.common)
    pack = await create_pack(db_session, "basic", price=100, card_count=3, probabilities={Rarity.common: 1.0})

    user = await _register(client, db_session, 700001, bot_token)
    headers = telegram_headers(700001, bot_token)

    resp = await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["cards"]) == 3
    assert body["new_balance"] == 500 - 100


async def test_open_pack_insufficient_balance(client, db_session, bot_token):
    await create_player(db_session, rarity=Rarity.common)
    pack = await create_pack(db_session, "expensive", price=999999, card_count=3, probabilities={Rarity.common: 1.0})

    await _register(client, db_session, 700002, bot_token)
    headers = telegram_headers(700002, bot_token)

    resp = await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "insufficient_balance"


async def test_open_pack_guaranteed_min_rarity(client, db_session, bot_token):
    await create_player(db_session, rarity=Rarity.common)
    await create_player(db_session, rarity=Rarity.epic, rating=85)
    pack = await create_pack(
        db_session, "elite_test", price=100, card_count=5,
        probabilities={Rarity.common: 1.0}, guaranteed_min_rarity=Rarity.epic,
    )

    await _register(client, db_session, 700003, bot_token)
    headers = telegram_headers(700003, bot_token)

    resp = await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={})
    assert resp.status_code == 200
    rarities = [c["card"]["player"]["rarity"] for c in resp.json()["cards"]]
    assert "epic" in rarities


async def test_open_pack_atomicity_on_failure(client, db_session, bot_token):
    """A failed open (insufficient balance) must not create any cards or change the balance."""
    await create_player(db_session, rarity=Rarity.common)
    pack = await create_pack(db_session, "atomtest", price=999999, card_count=3, probabilities={Rarity.common: 1.0})

    await _register(client, db_session, 700004, bot_token)
    headers = telegram_headers(700004, bot_token)

    resp = await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={})
    assert resp.status_code == 400

    user = await get_user_by_telegram_id(db_session, 700004)
    assert user.balance == 500
    cards = (await db_session.execute(select(UserCard).where(UserCard.owner_id == user.id))).scalars().all()
    assert len(cards) == 0


async def test_open_pack_idempotency_key_prevents_double_charge(client, db_session, bot_token):
    for _ in range(5):
        await create_player(db_session, rarity=Rarity.common)
    pack = await create_pack(db_session, "idem_test", price=100, card_count=2, probabilities={Rarity.common: 1.0})

    await _register(client, db_session, 700005, bot_token)
    headers = telegram_headers(700005, bot_token)

    first = await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={"idempotency_key": "abc-123"})
    second = await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={"idempotency_key": "abc-123"})

    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["opening_id"] == second.json()["opening_id"]
    assert first.json()["new_balance"] == second.json()["new_balance"] == 400

    user = await get_user_by_telegram_id(db_session, 700005)
    assert user.balance == 400
