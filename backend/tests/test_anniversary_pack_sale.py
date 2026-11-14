"""«Юбилейный пак» on sale: a themed pack (player_pool "collection:<id>")
shows and sells only inside its window and once its collection has cards;
the coins one has a daily limit, the Stars one is checked at the invoice and
at pre-checkout."""
from datetime import datetime, timedelta, timezone

import pytest

import app.core.rate_limit as rate_limit_module
from app.config import get_settings
from app.models.card_collection import CardCollection
from app.models.enums import Rarity
from app.services import stars_payment_service
from tests.factories import create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

INTERNAL_HEADERS = {"X-Internal-Secret": get_settings().internal_api_secret}
ODDS = {Rarity.rare: 0.55, Rarity.epic: 0.35, Rarity.legendary: 0.10}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _fake_link(payload_token, title, description, stars_amount, subscription_period=None):
    return f"https://t.me/invoice/{payload_token}"


async def _setup(db_session, client, bot_token, tg, *, filled=True, **window):
    collection = CardCollection(name=f"Клуб {tg}", is_active=False)
    db_session.add(collection)
    await db_session.commit()
    if filled:
        for rarity in (Rarity.rare, Rarity.epic, Rarity.legendary):
            await create_player(db_session, rarity=rarity, collection_id=collection.id, is_pack_droppable=False)
    now = datetime.now(timezone.utc)
    window = {"available_from": now - timedelta(days=1), "available_until": now + timedelta(days=5), **window}
    pool = f"collection:{collection.id}"
    coins = await create_pack(db_session, f"anni-{tg}", price=2500, card_count=3, probabilities=ODDS,
                              player_pool=pool, daily_limit_per_user=2, **window)
    stars = await create_pack(db_session, f"anni-stars-{tg}", price=2500, card_count=3, probabilities=ODDS,
                              player_pool=pool, stars_price=20, **window)
    headers = telegram_headers(tg, bot_token)
    assert (await client.post("/api/v1/auth/session", headers=headers)).status_code == 200
    user = await get_user_by_telegram_id(db_session, tg)
    user.balance = 100_000
    await db_session.commit()
    return coins, stars, headers


async def _shop_ids(client, headers):
    return {p["id"] for p in (await client.get("/api/v1/packs", headers=headers)).json()}


async def test_sold_for_coins_with_a_daily_limit(client, db_session, bot_token):
    coins, stars, headers = await _setup(db_session, client, bot_token, 873001)
    assert {coins.id, stars.id} <= await _shop_ids(client, headers)
    for _ in range(2):
        opened = await client.post(f"/api/v1/packs/{coins.id}/open", headers=headers, json={})
        assert opened.status_code == 200, opened.text
        assert len(opened.json()["cards"]) == 3
    third = await client.post(f"/api/v1/packs/{coins.id}/open", headers=headers, json={})
    assert third.status_code == 409 and third.json()["error"]["details"]["reason"] == "daily_limit"
    # The Stars one is not for coins.
    assert (await client.post(f"/api/v1/packs/{stars.id}/open", headers=headers, json={})).status_code == 409


async def test_hidden_and_not_sold_while_the_collection_is_empty(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_link)
    coins, stars, headers = await _setup(db_session, client, bot_token, 873002, filled=False)
    assert not {coins.id, stars.id} & await _shop_ids(client, headers)
    opened = await client.post(f"/api/v1/packs/{coins.id}/open", headers=headers, json={})
    assert opened.status_code == 409 and opened.json()["error"]["details"]["reason"] == "collection_pool_empty"
    assert (await client.post(f"/api/v1/packs/{stars.id}/stars-invoice", headers=headers)).status_code == 409


async def test_hidden_and_not_sold_outside_the_window(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_link)
    past = datetime.now(timezone.utc) - timedelta(days=1)
    coins, stars, headers = await _setup(db_session, client, bot_token, 873003,
                                         available_from=past - timedelta(days=9), available_until=past)
    assert not {coins.id, stars.id} & await _shop_ids(client, headers)
    assert (await client.post(f"/api/v1/packs/{coins.id}/open", headers=headers, json={})).status_code == 409
    assert (await client.post(f"/api/v1/packs/{stars.id}/stars-invoice", headers=headers)).status_code == 409


async def test_stars_pack_window_checked_at_pre_checkout(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_link)
    _, stars, headers = await _setup(db_session, client, bot_token, 873004)
    invoice = await client.post(f"/api/v1/packs/{stars.id}/stars-invoice", headers=headers)
    assert invoice.status_code == 200, invoice.text
    token = invoice.json()["payload_token"]
    assert invoice.json()["stars_amount"] == 20

    # The event ended between the invoice and the payment.
    stars.available_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()
    pre = await client.post("/api/v1/internal/stars-payments/pre-checkout",
                            json={"payload_token": token, "total_amount": 20}, headers=INTERNAL_HEADERS)
    assert pre.json()["ok"] is False


async def test_collection_only_in_the_album_while_the_event_runs(client, db_session, bot_token):
    from app.services import anniversary_service
    from app.services.game_config_service import get_config

    _, _, headers = await _setup(db_session, client, bot_token, 873005)
    collection = (await db_session.execute(
        CardCollection.__table__.select().where(CardCollection.name == "Клуб 873005")
    )).first()
    config = await get_config(db_session)
    now = datetime.now(timezone.utc)
    config.anniversary_enabled = True
    config.anniversary_starts_at = now + timedelta(days=7)
    config.anniversary_ends_at = now + timedelta(days=17)
    config.anniversary_settings = {"collection_id": collection.id}
    await db_session.commit()
    anniversary_service.reset_cache()

    async def album_names():
        body = (await client.get("/api/v1/collection/album", headers=headers)).json()
        return {c["name"] for c in body["collections"]}

    assert "Клуб 873005" not in await album_names()  # before the start
    config.anniversary_starts_at = now - timedelta(hours=1)
    await db_session.commit()
    assert "Клуб 873005" in await album_names()  # the event runs
    config.anniversary_ends_at = now - timedelta(minutes=1)
    await db_session.commit()
    assert "Клуб 873005" not in await album_names()  # it's over
