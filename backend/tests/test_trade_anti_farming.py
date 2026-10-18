"""Trade anti-farming rules (services/trade_guard_service.py): card-for-card
mode, new accounts can't give value, a daily cap on coins received through
trades, the coin tax, and the admin «suspicious trade flows» report."""
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.enums import CardSource, Rarity, TradeStatus, TransactionType
from app.models.game_config import GameConfig
from app.models.trade import TradeOffer
from app.models.transaction import CoinTransaction
from app.models.user import User
from app.models.user_activity import UserDailyActivity
from app.services.admin_analytics_service import analytics_report
from app.services.card_creation import create_user_card
from app.services.game_config_service import get_config
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1"


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


@pytest_asyncio.fixture(autouse=True)
async def _coins_and_gifts_allowed(db_session):
    """Most rules below are about coins and one-way gifts, which the default
    card-for-card mode forbids; the card-for-card tests switch it back on."""
    await _set_config(db_session, trade_coins_enabled=True, trade_cards_both_sides=False)


async def _register(client, db_session, telegram_id, bot_token):
    headers = telegram_headers(telegram_id, bot_token)
    assert (await client.post(f"{API}/auth/session", headers=headers)).status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id), headers


async def _make_veteran(db_session, user: User, active_days: int = 3) -> None:
    """Old enough and active on enough days to pass the default give rules."""
    user.created_at = datetime.now(timezone.utc) - timedelta(days=30)
    for i in range(1, active_days + 1):
        db_session.add(UserDailyActivity(user_id=user.id, day=date.today() - timedelta(days=i)))
    await db_session.commit()


async def _set_config(db_session, **values):
    config = await get_config(db_session)
    for key, value in values.items():
        setattr(config, key, value)
    await db_session.commit()


async def _card(db_session, owner_id):
    player = await create_player(db_session, rarity=Rarity.common)
    card = await create_user_card(db_session, owner_id, player.id, CardSource.seed)
    await db_session.commit()
    return card


async def _set_balance(db_session, user: User, balance: int):
    user.balance = balance
    await db_session.commit()


# --- giving needs an old, active account -------------------------------------------------


async def test_new_account_cannot_give_cards(client, db_session, bot_token):
    sender, headers = await _register(client, db_session, 760001, bot_token)
    receiver, _ = await _register(client, db_session, 760002, bot_token)
    card = await _card(db_session, sender.id)

    resp = await client.post(f"{API}/trades/offers", headers=headers, json={
        "receiver_id": receiver.id, "offered_card_ids": [card.id], "requested_card_ids": [],
    })
    assert resp.status_code == 403
    error = resp.json()["error"]
    assert error["details"]["rule"] == "trade_new_account"
    assert "после регистрации" in error["message"]
    await db_session.refresh(card)
    assert card.is_locked_in_trade is False


async def test_new_account_cannot_give_coins(client, db_session, bot_token):
    sender, headers = await _register(client, db_session, 760011, bot_token)
    receiver, _ = await _register(client, db_session, 760012, bot_token)

    resp = await client.post(f"{API}/trades/offers", headers=headers, json={
        "receiver_id": receiver.id, "sender_coins": 100,
    })
    assert resp.status_code == 403
    assert resp.json()["error"]["details"]["rule"] == "trade_new_account"


async def test_old_but_inactive_account_cannot_give(client, db_session, bot_token):
    sender, headers = await _register(client, db_session, 760021, bot_token)
    receiver, _ = await _register(client, db_session, 760022, bot_token)
    await _make_veteran(db_session, sender, active_days=0)  # only today's visit counts: 1 day < 2

    resp = await client.post(f"{API}/trades/offers", headers=headers, json={
        "receiver_id": receiver.id, "sender_coins": 50,
    })
    assert resp.status_code == 403
    assert "дн. игры" in resp.json()["error"]["message"]


async def test_veteran_can_give_and_new_account_can_receive(client, db_session, bot_token):
    sender, headers = await _register(client, db_session, 760031, bot_token)
    receiver, receiver_headers = await _register(client, db_session, 760032, bot_token)
    await _make_veteran(db_session, sender)
    card = await _card(db_session, sender.id)

    resp = await client.post(f"{API}/trades/offers", headers=headers, json={
        "receiver_id": receiver.id, "offered_card_ids": [card.id], "sender_coins": 100,
    })
    assert resp.status_code == 200
    accepted = await client.post(f"{API}/trades/offers/{resp.json()['id']}/accept", headers=receiver_headers)
    assert accepted.status_code == 200
    await db_session.refresh(card)
    assert card.owner_id == receiver.id


async def test_cannot_request_value_from_a_new_account(client, db_session, bot_token):
    sender, headers = await _register(client, db_session, 760041, bot_token)
    receiver, _ = await _register(client, db_session, 760042, bot_token)
    await _make_veteran(db_session, sender)
    card = await _card(db_session, receiver.id)

    resp = await client.post(f"{API}/trades/offers", headers=headers, json={
        "receiver_id": receiver.id, "requested_card_ids": [card.id],
    })
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["rule"] == "trade_new_account_partner"


async def test_rules_are_rechecked_on_accept(client, db_session, bot_token):
    """An offer created while the rules were off can't be accepted once
    they're on if the accepting side would give value from a new account."""
    sender, headers = await _register(client, db_session, 760051, bot_token)
    receiver, receiver_headers = await _register(client, db_session, 760052, bot_token)
    card = await _card(db_session, receiver.id)
    await _set_config(db_session, trade_send_min_account_age_days=0, trade_send_min_active_days=0)
    offer = await client.post(f"{API}/trades/offers", headers=headers, json={
        "receiver_id": receiver.id, "requested_card_ids": [card.id],
    })
    assert offer.status_code == 200

    await _set_config(db_session, trade_send_min_account_age_days=3, trade_send_min_active_days=2)
    resp = await client.post(f"{API}/trades/offers/{offer.json()['id']}/accept", headers=receiver_headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["details"]["rule"] == "trade_new_account"
    await db_session.refresh(card)
    assert card.owner_id == receiver.id


async def test_zero_disables_the_give_rules(client, db_session, bot_token):
    sender, headers = await _register(client, db_session, 760061, bot_token)
    receiver, _ = await _register(client, db_session, 760062, bot_token)
    await _set_config(db_session, trade_send_min_account_age_days=0, trade_send_min_active_days=0)

    resp = await client.post(f"{API}/trades/offers", headers=headers, json={
        "receiver_id": receiver.id, "sender_coins": 10,
    })
    assert resp.status_code == 200


# --- daily cap on coins received through trades -----------------------------------------


async def test_daily_receive_cap_blocks_at_create_and_at_accept(client, db_session, bot_token):
    receiver, receiver_headers = await _register(client, db_session, 760071, bot_token)
    giver_a, headers_a = await _register(client, db_session, 760072, bot_token)
    giver_b, headers_b = await _register(client, db_session, 760073, bot_token)
    for giver in (giver_a, giver_b):
        await _make_veteran(db_session, giver)
        await _set_balance(db_session, giver, 5000)
    await _set_config(db_session, trade_daily_coins_receive_cap=1000)

    too_much = await client.post(f"{API}/trades/offers", headers=headers_a, json={
        "receiver_id": receiver.id, "sender_coins": 1001,
    })
    assert too_much.status_code == 409
    assert too_much.json()["error"]["details"] == {"rule": "trade_daily_coins_cap", "cap": 1000, "left": 1000}

    # Two offers that each fit, but not together: the second accept is refused.
    first = await client.post(f"{API}/trades/offers", headers=headers_a, json={"receiver_id": receiver.id, "sender_coins": 600})
    second = await client.post(f"{API}/trades/offers", headers=headers_b, json={"receiver_id": receiver.id, "sender_coins": 600})
    assert first.status_code == 200 and second.status_code == 200
    assert (await client.post(f"{API}/trades/offers/{first.json()['id']}/accept", headers=receiver_headers)).status_code == 200
    resp = await client.post(f"{API}/trades/offers/{second.json()['id']}/accept", headers=receiver_headers)
    assert resp.status_code == 409
    assert "можно ещё 400" in resp.json()["error"]["message"]
    await db_session.refresh(receiver)
    await db_session.refresh(giver_b)
    assert giver_b.balance == 5000


async def test_receive_cap_also_covers_coins_requested_from_the_partner(client, db_session, bot_token):
    sender, headers = await _register(client, db_session, 760081, bot_token)
    receiver, _ = await _register(client, db_session, 760082, bot_token)
    await _make_veteran(db_session, receiver)
    await _set_balance(db_session, receiver, 5000)
    await _set_config(db_session, trade_daily_coins_receive_cap=500)

    resp = await client.post(f"{API}/trades/offers", headers=headers, json={
        "receiver_id": receiver.id, "receiver_coins": 800,
    })
    assert resp.status_code == 409
    assert "Сегодня ты уже получил(а) 0" in resp.json()["error"]["message"]


# --- coin tax -------------------------------------------------------------------------------


async def test_coin_tax_is_burned_from_the_coin_receiver(client, db_session, bot_token):
    sender, headers = await _register(client, db_session, 760091, bot_token)
    receiver, receiver_headers = await _register(client, db_session, 760092, bot_token)
    await _make_veteran(db_session, sender)
    await _set_balance(db_session, sender, 1000)
    await _set_balance(db_session, receiver, 0)
    await _set_config(db_session, trade_coin_tax_pct=10)

    offer = await client.post(f"{API}/trades/offers", headers=headers, json={"receiver_id": receiver.id, "sender_coins": 105})
    resp = await client.post(f"{API}/trades/offers/{offer.json()['id']}/accept", headers=receiver_headers)
    assert resp.status_code == 200
    assert resp.json()["new_balance"] == 105 - 11  # 10% of 105, rounded up

    await db_session.refresh(sender)
    assert sender.balance == 1000 - 105
    tax = (await db_session.execute(
        select(CoinTransaction).where(CoinTransaction.type == TransactionType.trade_coin_tax)
    )).scalars().all()
    assert [(t.user_id, t.amount) for t in tax] == [(receiver.id, -11)]


async def test_no_tax_by_default(client, db_session, bot_token):
    sender, headers = await _register(client, db_session, 760101, bot_token)
    receiver, receiver_headers = await _register(client, db_session, 760102, bot_token)
    await _make_veteran(db_session, sender)
    await _set_balance(db_session, receiver, 0)

    offer = await client.post(f"{API}/trades/offers", headers=headers, json={"receiver_id": receiver.id, "sender_coins": 100})
    resp = await client.post(f"{API}/trades/offers/{offer.json()['id']}/accept", headers=receiver_headers)
    assert resp.json()["new_balance"] == 100


# --- card-for-card mode (the defaults) -----------------------------------------------------


async def _card_for_card_mode(db_session):
    await _set_config(db_session, trade_coins_enabled=False, trade_cards_both_sides=True)


async def test_card_for_card_mode_rejects_coins(client, db_session, bot_token):
    sender, headers = await _register(client, db_session, 760201, bot_token)
    receiver, _ = await _register(client, db_session, 760202, bot_token)
    await _make_veteran(db_session, sender)
    await _make_veteran(db_session, receiver)
    mine, theirs = await _card(db_session, sender.id), await _card(db_session, receiver.id)
    await _card_for_card_mode(db_session)

    for extra in ({"sender_coins": 100}, {"receiver_coins": 100}):
        resp = await client.post(f"{API}/trades/offers", headers=headers, json={
            "receiver_id": receiver.id, "offered_card_ids": [mine.id], "requested_card_ids": [theirs.id], **extra,
        })
        assert resp.status_code == 409
        assert resp.json()["error"]["details"]["rule"] == "trade_coins_disabled"
        assert "карточка на карточку" in resp.json()["error"]["message"]


async def test_card_for_card_mode_rejects_one_way_gifts(client, db_session, bot_token):
    sender, headers = await _register(client, db_session, 760211, bot_token)
    receiver, _ = await _register(client, db_session, 760212, bot_token)
    await _make_veteran(db_session, sender)
    await _make_veteran(db_session, receiver)
    mine, theirs = await _card(db_session, sender.id), await _card(db_session, receiver.id)
    await _card_for_card_mode(db_session)

    for body in ({"offered_card_ids": [mine.id]}, {"requested_card_ids": [theirs.id]}):
        resp = await client.post(f"{API}/trades/offers", headers=headers, json={"receiver_id": receiver.id, **body})
        assert resp.status_code == 409
        assert resp.json()["error"]["details"]["rule"] == "trade_cards_both_sides"


async def test_card_for_card_trade_goes_through(client, db_session, bot_token):
    sender, headers = await _register(client, db_session, 760221, bot_token)
    receiver, receiver_headers = await _register(client, db_session, 760222, bot_token)
    await _make_veteran(db_session, sender)
    await _make_veteran(db_session, receiver)
    mine, theirs = await _card(db_session, sender.id), await _card(db_session, receiver.id)
    await _card_for_card_mode(db_session)

    offer = await client.post(f"{API}/trades/offers", headers=headers, json={
        "receiver_id": receiver.id, "offered_card_ids": [mine.id], "requested_card_ids": [theirs.id],
    })
    assert offer.status_code == 200
    assert (await client.post(f"{API}/trades/offers/{offer.json()['id']}/accept", headers=receiver_headers)).status_code == 200
    await db_session.refresh(mine)
    await db_session.refresh(theirs)
    assert (mine.owner_id, theirs.owner_id) == (receiver.id, sender.id)


async def test_pending_coin_offer_is_refused_once_coins_are_switched_off(client, db_session, bot_token):
    sender, headers = await _register(client, db_session, 760231, bot_token)
    receiver, receiver_headers = await _register(client, db_session, 760232, bot_token)
    await _make_veteran(db_session, sender)
    offer = await client.post(f"{API}/trades/offers", headers=headers, json={"receiver_id": receiver.id, "sender_coins": 100})
    assert offer.status_code == 200

    await _card_for_card_mode(db_session)
    resp = await client.post(f"{API}/trades/offers/{offer.json()['id']}/accept", headers=receiver_headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["rule"] == "trade_coins_disabled"


def test_card_for_card_is_the_default():
    columns = GameConfig.__table__.c
    assert columns.trade_coins_enabled.default.arg is False
    assert columns.trade_cards_both_sides.default.arg is True


# --- player-facing rules ---------------------------------------------------------------------


async def test_rules_endpoint_explains_the_block(client, db_session, bot_token):
    _user, headers = await _register(client, db_session, 760111, bot_token)
    body = (await client.get(f"{API}/trades/rules", headers=headers)).json()
    assert body["can_give"] is False
    assert "после регистрации" in body["give_block_reason"]
    assert body["daily_coins_receive_cap"] == 3000
    assert body["coins_received_today"] == 0
    assert body["coin_tax_pct"] == 0


# --- admin report -------------------------------------------------------------------------------


async def _accepted_trade(db, giver: User, taker: User, coins: int = 0, coins_back: int = 0):
    now = datetime.now(timezone.utc)
    offer = TradeOffer(
        sender_id=giver.id, receiver_id=taker.id, sender_coins=coins, receiver_coins=coins_back,
        status=TradeStatus.accepted, expires_at=now, resolved_at=now,
    )
    db.add(offer)
    await db.commit()


async def _plain_user(db, tg_id: int, age_days: int) -> User:
    user = User(telegram_id=tg_id, username=f"tf_{tg_id}", balance=0,
                created_at=datetime.now(timezone.utc) - timedelta(days=age_days))
    db.add(user)
    await db.commit()
    return user


async def test_report_lists_a_main_fed_by_young_accounts(db_session):
    main = await _plain_user(db_session, 770001, age_days=100)
    fair = await _plain_user(db_session, 770002, age_days=100)
    alts = [await _plain_user(db_session, 770010 + i, age_days=1) for i in range(3)]
    for alt in alts:
        await _accepted_trade(db_session, alt, main, coins=400)
    # Young partners, but fair swaps (coins for coins) don't count.
    for alt in alts:
        await _accepted_trade(db_session, alt, fair, coins=100, coins_back=100)

    report = (await analytics_report(db_session, 7))["suspicious_trades"]
    assert report["min_donors"] == 3
    assert [r["user_id"] for r in report["rows"]] == [main.id]
    row = report["rows"][0]
    assert row["young_donors"] == 3
    assert row["coins_received"] == 1200
    assert row["trades"] == 3


async def test_report_ignores_old_donors_and_too_few_donors(db_session):
    main = await _plain_user(db_session, 770101, age_days=100)
    old_friends = [await _plain_user(db_session, 770110 + i, age_days=60) for i in range(3)]
    for friend in old_friends:
        await _accepted_trade(db_session, friend, main, coins=500)
    other = await _plain_user(db_session, 770120, age_days=100)
    for i in range(2):
        alt = await _plain_user(db_session, 770130 + i, age_days=1)
        await _accepted_trade(db_session, alt, other, coins=500)

    assert (await analytics_report(db_session, 7))["suspicious_trades"]["rows"] == []
