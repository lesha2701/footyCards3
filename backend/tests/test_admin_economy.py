from app.models.enums import Position, Rarity, TransactionType
from app.models.transaction import CoinTransaction
from tests.factories import create_player
from tests.test_admin_packs import _admin_auth, _pack_payload
from tests.utils import telegram_headers

API = "/api/v1"


async def test_economy_report_splits_inflow_and_outflow_by_source(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    await client.post(f"{API}/auth/session", headers=telegram_headers(840001, bot_token))
    from tests.factories import get_user_by_telegram_id
    user = await get_user_by_telegram_id(db_session, 840001)
    for amount, kind in ((50, TransactionType.task_reward), (30, TransactionType.task_reward),
                         (-100, TransactionType.pack_purchase)):
        db_session.add(CoinTransaction(user_id=user.id, amount=amount, balance_before=0, balance_after=0, type=kind))
    await db_session.commit()

    body = (await client.get(f"{API}/admin/dashboard/economy?days=7", headers=auth)).json()
    rows = {r["type"]: r for r in body["by_type"]}
    assert rows["task_reward"]["inflow"] >= 80 and rows["task_reward"]["count"] >= 2
    assert rows["pack_purchase"]["outflow"] >= 100
    assert body["net"] == body["total_inflow"] - body["total_outflow"]
    assert body["daily"], "today's transactions show up as a day row"


async def test_pack_expected_value_uses_rarity_odds_and_pool_prices(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    await create_player(db_session, position=Position.ST, rarity=Rarity.common, quick_sell_price=10)
    await create_player(db_session, position=Position.CB, rarity=Rarity.common, quick_sell_price=30)
    pack_id = (await client.post(f"{API}/admin/packs", headers=auth, json=_pack_payload(
        slug="ev-pack", price=100, card_count=3,
    ))).json()["id"]

    body = (await client.get(f"{API}/admin/dashboard/packs/{pack_id}/expected-value", headers=auth)).json()
    common = next(r for r in body["rarities"] if r["rarity"] == "common")
    assert common["probability"] == 1.0
    assert body["expected_quick_sell_value"] == round(common["avg_quick_sell"] * 3, 1)
    assert body["value_to_price"] == round(body["expected_quick_sell_value"] / 100, 3)


async def test_economy_requires_admin(client, bot_token):
    resp = await client.get(f"{API}/admin/dashboard/economy", headers=telegram_headers(840002, bot_token))
    assert resp.status_code in (401, 403)
