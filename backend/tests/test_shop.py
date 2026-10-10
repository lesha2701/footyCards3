"""Shop: daily discounted offer (server-priced, once a day), recent
purchases and the per-pack expected value shown on pack cards."""
import pytest

import app.core.rate_limit as rate_limit_module
from app.models.enums import Position, Rarity
from app.models.user import User
from app.services.game_config_service import get_config
from tests.factories import create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1"


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _setup(client, db_session, bot_token, tg_id, *, enabled=True):
    await client.post(f"{API}/auth/session", headers=telegram_headers(tg_id, bot_token))
    user = await get_user_by_telegram_id(db_session, tg_id)
    await create_player(db_session, position=Position.ST, rarity=Rarity.common, quick_sell_price=20)
    pack = await create_pack(db_session, f"offer-{tg_id}", price=200, card_count=1, probabilities={Rarity.common: 1.0})
    config = await get_config(db_session)
    config.shop_daily_offer_enabled = enabled
    config.shop_daily_offer_discount_pct = 25
    config.shop_daily_offer_pack_id = pack.id
    user.balance = 1000
    await db_session.commit()
    return user.id, pack.id, telegram_headers(tg_id, bot_token)


async def test_daily_offer_is_charged_at_the_server_discount_once_a_day(client, db_session, bot_token):
    user_id, pack_id, headers = await _setup(client, db_session, bot_token, 850001)
    offer = (await client.get(f"{API}/packs/daily-offer", headers=headers)).json()
    assert offer["pack"]["id"] == pack_id and offer["price"] == 150 and offer["claimed_today"] is False

    first = await client.post(f"{API}/packs/{pack_id}/open", headers=headers, json={"idempotency_key": "o1", "daily_offer": True})
    assert first.status_code == 200, first.text
    assert first.json()["new_balance"] == 1000 - 150

    again = await client.post(f"{API}/packs/{pack_id}/open", headers=headers, json={"idempotency_key": "o2", "daily_offer": True})
    assert again.status_code == 409
    # A retry of the SAME purchase is idempotent, not a second discount.
    retry = await client.post(f"{API}/packs/{pack_id}/open", headers=headers, json={"idempotency_key": "o1", "daily_offer": True})
    assert retry.status_code == 200 and retry.json()["opening_id"] == first.json()["opening_id"]
    assert (await client.get(f"{API}/packs/daily-offer", headers=headers)).json()["claimed_today"] is True
    db_session.expire_all()
    assert (await db_session.get(User, user_id)).balance == 850


async def test_daily_offer_rejects_other_packs_and_when_disabled(client, db_session, bot_token):
    _, pack_id, headers = await _setup(client, db_session, bot_token, 850002)
    other = await create_pack(db_session, "not-the-offer", price=100, card_count=1, probabilities={Rarity.common: 1.0})
    resp = await client.post(f"{API}/packs/{other.id}/open", headers=headers, json={"daily_offer": True})
    assert resp.status_code == 409

    config = await get_config(db_session)
    config.shop_daily_offer_enabled = False
    await db_session.commit()
    assert (await client.get(f"{API}/packs/daily-offer", headers=headers)).json() is None
    resp = await client.post(f"{API}/packs/{pack_id}/open", headers=headers, json={"daily_offer": True})
    assert resp.status_code == 409


async def test_recent_purchases_and_expected_value(client, db_session, bot_token):
    _, pack_id, headers = await _setup(client, db_session, bot_token, 850003, enabled=False)
    for key in ("h1", "h2"):
        assert (await client.post(f"{API}/packs/{pack_id}/open", headers=headers, json={"idempotency_key": key})).status_code == 200
    history = (await client.get(f"{API}/packs/history", headers=headers)).json()
    assert history[0]["pack"]["id"] == pack_id and history[0]["times_opened"] == 2

    listed = next(p for p in (await client.get(f"{API}/packs", headers=headers)).json() if p["id"] == pack_id)
    assert listed["expected_value"] is not None and listed["expected_value"] > 0
