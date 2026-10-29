"""Trades vs. multi-accounts and real-money deals (card_value_service,
trade_guard_service.ensure_value_rules): free-source valuable cards stay on
their account, valuable cards need a «Проверенный аккаунт», trades must be
of roughly equal value, and repeated trades with one partner don't farm
tasks / bingo."""
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.card import UserCard
from app.models.enums import CardSource, Rarity
from app.models.pack import StarsInvoice
from app.models.trade import TradeOffer
from app.models.user import User
from app.models.user_activity import UserDailyActivity
from app.services import card_value_service as cv
from app.services.card_creation import create_user_card
from app.services.game_config_service import get_config
from app.services.pack_service import pity_eligible
from tests.factories import create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1/trades"


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


@pytest.fixture(autouse=True)
async def _coins_and_one_way_off(db_session):
    """Only this file's rules: one-way offers allowed, the old young-account
    give rule out of the way (verified accounts are older anyway)."""
    config = await get_config(db_session)
    config.trade_cards_both_sides = False
    config.trade_send_min_account_age_days = 0
    config.trade_send_min_active_days = 0
    await db_session.commit()


async def _player(client, db_session, telegram_id, bot_token, *, verified=True) -> tuple[User, dict]:
    headers = telegram_headers(telegram_id, bot_token)
    assert (await client.post("/api/v1/auth/session", headers=headers)).status_code == 200
    user = await get_user_by_telegram_id(db_session, telegram_id)
    if verified:
        user.created_at = datetime.now(timezone.utc) - timedelta(days=40)
        for i in range(1, 9):
            db_session.add(UserDailyActivity(user_id=user.id, day=date.today() - timedelta(days=i)))
        db_session.add(StarsInvoice(
            user_id=user.id, payload_token=uuid.uuid4().hex, stars_amount=49, completed_at=datetime.now(timezone.utc),
        ))
    await db_session.commit()
    return user, headers


async def _card(db_session, owner: User, rarity=Rarity.common, source=CardSource.seed, **player_fields):
    player = await create_player(db_session, rarity=rarity, **player_fields)
    card = await create_user_card(db_session, owner.id, player.id, source)
    await db_session.commit()
    return card


async def _offer(client, headers, receiver, offered=(), requested=()):
    return await client.post(f"{API}/offers", headers=headers, json={
        "receiver_id": receiver.id, "offered_card_ids": [c.id for c in offered], "requested_card_ids": [c.id for c in requested],
    })


# --- values -----------------------------------------------------------------------------------


def _fake(rarity, rating=80, sell=100, path=None, stage=0, droppable=True, minted=100):
    player = SimpleNamespace(rarity=rarity, rating=rating, quick_sell_price=sell, path_talent_code=path,
                             is_pack_droppable=droppable, next_serial_number=minted + 1)
    return SimpleNamespace(player=player, path_stage=stage)


def test_card_values_follow_the_table():
    assert cv.card_value(_fake(Rarity.common, sell=30), None) == 60
    assert cv.card_value(_fake(Rarity.legendary, rating=91), None) == 6000
    assert cv.card_value(_fake(Rarity.legendary, rating=94), None) == 12000
    assert cv.card_value(_fake(Rarity.legendary, droppable=False, minted=40), None) == 30000
    assert cv.card_value(_fake(Rarity.legendary, droppable=False, minted=10), None) == 60000
    assert cv.card_value(_fake(Rarity.epic, droppable=False, minted=0), None) == 10000
    assert cv.card_value(_fake(Rarity.diamond), None) == 60000
    assert cv.card_value(_fake(Rarity.diamond, path="speed", stage=4), None) == 100000
    assert cv.is_valuable(_fake(Rarity.epic, droppable=False, minted=0), None)
    assert not cv.is_valuable(_fake(Rarity.epic), None)


# --- free sources ------------------------------------------------------------------------------


async def test_free_source_cards_are_marked_at_creation(client, db_session, bot_token):
    user, headers = await _player(client, db_session, 890001, bot_token)
    assert (await _card(db_session, user, source=CardSource.wheel)).from_free_source is True
    assert (await _card(db_session, user, source=CardSource.stars_purchase)).from_free_source is False

    await create_player(db_session, rarity=Rarity.common)
    paid = await create_pack(db_session, "paid", price=10, card_count=1, probabilities={Rarity.common: 1.0})
    free = await create_pack(db_session, "free", price=0, card_count=1, probabilities={Rarity.common: 1.0})
    await db_session.commit()
    user.balance = 1000
    await db_session.commit()
    for pack, bound in ((paid, False), (free, True)):
        body = (await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={})).json()
        card = await db_session.get(UserCard, body["cards"][0]["card"]["id"], populate_existing=True)
        assert card.from_free_source is bound


async def test_free_source_legendary_cannot_be_traded(client, db_session, bot_token):
    seller, headers = await _player(client, db_session, 890011, bot_token)
    buyer, _ = await _player(client, db_session, 890012, bot_token)
    free_legend = await _card(db_session, seller, Rarity.legendary, CardSource.free_pack, rating=91)
    their_legend = await _card(db_session, buyer, Rarity.legendary, rating=91)

    resp = await _offer(client, headers, buyer, [free_legend], [their_legend])
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["rule"] == "trade_bound_card"


# --- «Проверенный аккаунт» ---------------------------------------------------------------------


async def test_unverified_account_cannot_give_a_legendary(client, db_session, bot_token):
    alt, headers = await _player(client, db_session, 890021, bot_token, verified=False)
    main, _ = await _player(client, db_session, 890022, bot_token)
    legend = await _card(db_session, alt, Rarity.legendary, rating=91)
    other = await _card(db_session, main, Rarity.legendary, rating=91)

    resp = await _offer(client, headers, main, [legend], [other])
    assert resp.status_code == 403
    assert resp.json()["error"]["details"]["rule"] == "trade_not_verified"
    assert "покупка за ⭐" in resp.json()["error"]["message"]

    rules = (await client.get(f"{API}/rules", headers=headers)).json()
    assert rules["verified"] is False and "Проверенный" in rules["verified_block_reason"]


async def test_cannot_ask_a_legendary_from_an_unverified_partner(client, db_session, bot_token):
    main, headers = await _player(client, db_session, 890031, bot_token)
    alt, _ = await _player(client, db_session, 890032, bot_token, verified=False)
    mine = await _card(db_session, main, Rarity.legendary, rating=91)
    theirs = await _card(db_session, alt, Rarity.legendary, rating=91)

    resp = await _offer(client, headers, alt, [mine], [theirs])
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["rule"] == "trade_not_verified_partner"


async def test_verified_legendary_swap_goes_through(client, db_session, bot_token):
    a, headers_a = await _player(client, db_session, 890041, bot_token)
    b, headers_b = await _player(client, db_session, 890042, bot_token)
    mine = await _card(db_session, a, Rarity.legendary, rating=91)
    theirs = await _card(db_session, b, Rarity.legendary, rating=92)

    offer = await _offer(client, headers_a, b, [mine], [theirs])
    assert offer.status_code == 200
    assert (await client.post(f"{API}/offers/{offer.json()['id']}/accept", headers=headers_b)).status_code == 200


# --- equal value -------------------------------------------------------------------------------


async def test_legendary_for_a_common_is_refused(client, db_session, bot_token):
    seller, headers = await _player(client, db_session, 890051, bot_token)
    buyer, _ = await _player(client, db_session, 890052, bot_token)
    legend = await _card(db_session, seller, Rarity.legendary, rating=91)
    common = await _card(db_session, buyer, Rarity.common, quick_sell_price=10)

    resp = await _offer(client, headers, buyer, [legend], [common])
    assert resp.status_code == 409
    error = resp.json()["error"]
    assert error["details"]["rule"] == "trade_unequal_value"
    assert error["details"]["give"] == 6000 and error["details"]["get"] == 20

    preview = (await client.post(f"{API}/preview", headers=headers, json={
        "receiver_id": buyer.id, "offered_card_ids": [legend.id], "requested_card_ids": [common.id],
    })).json()
    assert preview == {"give_value": 6000, "get_value": 20, "ok": False, "problem": error["message"]}


async def test_cheap_swaps_are_not_checked(client, db_session, bot_token):
    a, headers = await _player(client, db_session, 890061, bot_token, verified=False)
    b, _ = await _player(client, db_session, 890062, bot_token, verified=False)
    rare = await _card(db_session, a, Rarity.rare, quick_sell_price=100)
    common = await _card(db_session, b, Rarity.common, quick_sell_price=10)
    assert (await _offer(client, headers, b, [rare], [common])).status_code == 200


# --- tasks / bingo -----------------------------------------------------------------------------


async def test_only_one_trade_a_day_per_pair_counts_for_progress(client, db_session, bot_token):
    a, headers_a = await _player(client, db_session, 890071, bot_token)
    b, headers_b = await _player(client, db_session, 890072, bot_token)
    card = await _card(db_session, a, Rarity.common)

    # The same card there and back again.
    for giver_headers, taker_headers, taker in ((headers_a, headers_b, b), (headers_b, headers_a, a)):
        offer = await _offer(client, giver_headers, taker, [card], [])
        assert offer.status_code == 200, offer.text
        assert (await client.post(f"{API}/offers/{offer.json()['id']}/accept", headers=taker_headers)).status_code == 200
    rows = (await db_session.execute(select(TradeOffer.counts_for_progress).order_by(TradeOffer.id))).scalars().all()
    assert rows == [True, False]


# --- packs -------------------------------------------------------------------------------------


def test_pity_can_be_switched_off_per_pack():
    probabilities = [SimpleNamespace(rarity=Rarity.legendary, probability=0.02)]
    on = SimpleNamespace(stars_price=None, rarity_probabilities=probabilities, pity_enabled=True)
    off = SimpleNamespace(stars_price=None, rarity_probabilities=probabilities, pity_enabled=False)
    assert pity_eligible(on) and not pity_eligible(off)
