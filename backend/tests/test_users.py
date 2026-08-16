from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def test_public_profile_exposes_tactics_and_penalty_rating(client, db_session, bot_token):
    viewer = await _register(client, db_session, 870001, bot_token)
    target = await _register(client, db_session, 870002, bot_token)
    target.tactics_rating = 42
    target.penalty_rating = 17
    db_session.add(target)
    await db_session.commit()

    resp = await client.get(f"/api/v1/users/{target.id}", headers=telegram_headers(870001, bot_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["tactics_rating"] == 42
    assert body["penalty_rating"] == 17
