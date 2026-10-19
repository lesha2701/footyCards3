"""Shop sales boosters (migration 0183): legendary pity on paid packs, the
×10 discount and the first coin purchase bonus — all GameConfig, 0 = off."""
from types import SimpleNamespace

import pytest

import app.core.rate_limit as rate_limit_module
from app.config import get_settings
from app.models.enums import Rarity
from app.services import stars_payment_service
from app.services.game_config_service import get_config
from app.services.pack_service import apply_pity, bulk_total_price
from tests.factories import create_coin_package, create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

INTERNAL_HEADERS = {"X-Internal-Secret": get_settings().internal_api_secret}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def _set_config(db_session, **values):
    config = await get_config(db_session)
    for key, value in values.items():
        setattr(config, key, value)
    await db_session.commit()


def _pack(legendary=0.05, stars_price=None):
    probs = [SimpleNamespace(rarity=Rarity.common, probability=1 - legendary)]
    if legendary:
        probs.append(SimpleNamespace(rarity=Rarity.legendary, probability=legendary))
    return SimpleNamespace(rarity_probabilities=probs, stars_price=stars_price)


# --- pity ------------------------------------------------------------------

def test_pity_forces_a_legendary_on_the_last_pack_and_resets():
    user = SimpleNamespace(pity_counter=2)
    rolled = apply_pity(user, _pack(), [Rarity.common, Rarity.rare, Rarity.common], pity_packs=3)
    assert Rarity.legendary in rolled
    assert rolled.count(Rarity.legendary) == 1
    assert Rarity.rare in rolled  # the lowest slot is upgraded, not the best one
    assert user.pity_counter == 0


def test_pity_counts_misses_and_resets_on_a_natural_legendary():
    user = SimpleNamespace(pity_counter=0)
    apply_pity(user, _pack(), [Rarity.common], pity_packs=10)
    assert user.pity_counter == 1
    apply_pity(user, _pack(), [Rarity.legendary], pity_packs=10)
    assert user.pity_counter == 0


def test_pity_ignores_packs_without_a_legendary_chance_stars_packs_and_when_off():
    user = SimpleNamespace(pity_counter=9)
    assert apply_pity(user, _pack(legendary=0), [Rarity.common], pity_packs=3) == [Rarity.common]
    assert apply_pity(user, _pack(stars_price=5), [Rarity.common], pity_packs=3) == [Rarity.common]
    assert apply_pity(user, _pack(), [Rarity.common], pity_packs=0) == [Rarity.common]
    assert user.pity_counter == 9


async def test_shop_listing_shows_packs_left_until_the_guaranteed_legendary(client, db_session, bot_token):
    await _set_config(db_session, pity_packs=30)
    with_legendary = await create_pack(db_session, "pity_on", price=100, card_count=1, probabilities={Rarity.common: 0.9, Rarity.legendary: 0.1})
    without = await create_pack(db_session, "pity_off", price=100, card_count=1, probabilities={Rarity.common: 1.0})
    user = await _register(client, db_session, 860001, bot_token)
    user.pity_counter = 12
    await db_session.commit()

    body = (await client.get("/api/v1/packs", headers=telegram_headers(860001, bot_token))).json()
    by_id = {p["id"]: p for p in body}
    assert by_id[with_legendary.id]["pity_left"] == 18
    assert by_id[without.id]["pity_left"] is None


# --- ×10 discount ----------------------------------------------------------

def test_bulk_price_discount_starts_at_ten_and_rounds_for_the_player():
    assert bulk_total_price(100, 5, 10) == (500, 0)
    assert bulk_total_price(100, 10, 10) == (900, 10)
    assert bulk_total_price(333, 10, 15) == (2831, 15)  # 3330 - 499
    assert bulk_total_price(100, 10, 0) == (1000, 0)


async def test_open_ten_charges_the_discounted_total(client, db_session, bot_token):
    for _ in range(3):
        await create_player(db_session, rarity=Rarity.common)
    await _set_config(db_session, bulk10_discount_pct=10)
    pack = await create_pack(db_session, "bulk10", price=40, card_count=1, probabilities={Rarity.common: 1.0})
    await _register(client, db_session, 860002, bot_token)

    resp = await client.post(
        f"/api/v1/packs/{pack.id}/open-bulk", headers=telegram_headers(860002, bot_token), json={"quantity": 10}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_price_paid"] == 360
    assert body["new_balance"] == 500 - 360


# --- first coin purchase bonus --------------------------------------------

async def _fake_invoice_link(payload_token, title, description, stars_amount):
    return f"https://t.me/$invoice-{payload_token}"


async def _buy(client, package_id, telegram_id, bot_token, charge):
    headers = telegram_headers(telegram_id, bot_token)
    invoice = (await client.post("/api/v1/wallet/stars-invoice", headers=headers, json={"coin_package_id": package_id})).json()
    resp = await client.post(
        "/api/v1/internal/stars-payments/deliver",
        json={
            "payload_token": invoice["payload_token"],
            "telegram_user_id": telegram_id,
            "telegram_payment_charge_id": charge + "c" * 100,
            "total_amount": invoice["stars_amount"],
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200
    return resp.json()["coin_result"]["coins_credited"]


async def test_first_coin_purchase_gets_the_bonus_once(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    await _set_config(db_session, first_coin_purchase_bonus_pct=100)
    package = await create_coin_package(db_session, stars_price=10, coins_amount=200)
    user = await _register(client, db_session, 860003, bot_token)
    headers = telegram_headers(860003, bot_token)

    listed = (await client.get("/api/v1/wallet/coin-packages", headers=headers)).json()
    assert listed[0]["first_purchase_bonus_coins"] == 200

    assert await _buy(client, package.id, 860003, bot_token, "first-") == 400
    assert await _buy(client, package.id, 860003, bot_token, "second-") == 200

    await db_session.refresh(user)
    assert user.balance == 500 + 400 + 200
    listed = (await client.get("/api/v1/wallet/coin-packages", headers=headers)).json()
    assert listed[0]["first_purchase_bonus_coins"] == 0


async def test_first_purchase_bonus_off_by_default(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    package = await create_coin_package(db_session, stars_price=10, coins_amount=200)
    await _register(client, db_session, 860004, bot_token)
    assert await _buy(client, package.id, 860004, bot_token, "plain-") == 200
