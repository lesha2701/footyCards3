"""Admin: all users' coin transactions, paginated and filtered."""
from app.models.enums import TransactionType
from app.models.transaction import CoinTransaction
from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers


async def _admin_headers(client, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(999000001, bot_token))
    return {"Authorization": f"Bearer {resp.json()['admin_token']}"}


async def test_all_transactions_paginate_and_filter(client, db_session, bot_token):
    admin_headers = await _admin_headers(client, bot_token)
    other_headers = telegram_headers(990002, bot_token)
    await client.post("/api/v1/auth/session", headers=other_headers)
    other = await get_user_by_telegram_id(db_session, 990002)
    for i in range(45):
        db_session.add(CoinTransaction(
            user_id=other.id, amount=10 if i % 3 else -5, balance_before=0, balance_after=0,
            type=TransactionType.match_reward if i % 3 else TransactionType.pack_purchase, description=f"tx {i}",
        ))
    await db_session.commit()

    page1 = await client.get("/api/v1/admin/transactions", headers=admin_headers, params={"user_id": other.id, "page_size": 20})
    assert page1.status_code == 200, page1.text
    body = page1.json()
    assert body["pages"] >= 3 and len(body["items"]) == 20 and body["items"][0]["user_id"] == other.id
    page3 = (await client.get("/api/v1/admin/transactions", headers=admin_headers,
                              params={"user_id": other.id, "page": 3, "page_size": 20})).json()
    assert len(page3["items"]) == body["total"] - 40
    spend = (await client.get("/api/v1/admin/transactions", headers=admin_headers,
                              params={"user_id": other.id, "direction": "spend"})).json()
    assert spend["total"] == 15 and spend["spent"] == 75 and spend["income"] == 0
    typed = (await client.get("/api/v1/admin/transactions", headers=admin_headers,
                              params={"search": "990002", "type": "match_reward"})).json()
    assert typed["total"] == 30
