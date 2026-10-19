"""Stake anti-farming rules for open chat challenges
(services/stake_guard_service.py), exercised through Пенальти — Тактико and
Стратего call the same two checks."""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

import app.core.rate_limit as rate_limit_module
from app.models.card import UserCard
from app.models.enums import CardSource, Rarity, TransactionType
from app.models.transaction import CoinTransaction
from app.models.user_activity import UserDailyActivity
from app.services.game_config_service import get_config
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1/games/penalty/challenges"


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _player(client, db_session, telegram_id, bot_token, veteran=True, balance=5000):
    assert (await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))).status_code == 200
    user = await get_user_by_telegram_id(db_session, telegram_id)
    if veteran:
        user.created_at = datetime.now(timezone.utc) - timedelta(days=30)
        for i in range(1, 4):
            db_session.add(UserDailyActivity(user_id=user.id, day=date.today() - timedelta(days=i)))
    user.balance = balance
    player = await create_player(db_session, rarity=Rarity.rare, rating=80)
    card = UserCard(owner_id=user.id, player_id=player.id, source=CardSource.seed)
    db_session.add(card)
    await db_session.flush()
    card.serial_number = card.id
    await db_session.commit()
    return user, card, telegram_headers(telegram_id, bot_token)


async def _open(client, headers, card, stake):
    return await client.post(f"{API}/open", headers=headers, json={"user_card_id": card.id, "stake_coins": stake})


async def _accept(client, headers, card, match_id):
    return await client.post(f"{API}/open/{match_id}/accept", headers=headers, json={"user_card_id": card.id})


async def _config(db_session, **values):
    config = await get_config(db_session)
    for key, value in values.items():
        setattr(config, key, value)
    await db_session.commit()


async def test_stake_above_max_is_refused(client, db_session, bot_token):
    _user, card, headers = await _player(client, db_session, 870001, bot_token)
    resp = await _open(client, headers, card, 501)
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["rule"] == "stake_max"
    assert (await _open(client, headers, card, 500)).status_code == 200


async def test_zero_max_turns_stakes_off_but_free_challenges_work(client, db_session, bot_token):
    _user, card, headers = await _player(client, db_session, 870011, bot_token)
    await _config(db_session, stake_max_coins=0)
    resp = await _open(client, headers, card, 10)
    assert resp.status_code == 409 and resp.json()["error"]["details"]["rule"] == "stakes_disabled"
    assert (await _open(client, headers, card, 0)).status_code == 200


async def test_new_account_cannot_stake(client, db_session, bot_token):
    _user, card, headers = await _player(client, db_session, 870021, bot_token, veteran=False)
    resp = await _open(client, headers, card, 100)
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["rule"] == "stake_new_account"
    assert "без ставки" in resp.json()["error"]["message"]


async def test_new_account_cannot_accept_a_staked_challenge(client, db_session, bot_token):
    _creator, card_a, headers_a = await _player(client, db_session, 870031, bot_token)
    alt, card_b, headers_b = await _player(client, db_session, 870032, bot_token, veteran=False)
    match_id = (await _open(client, headers_a, card_a, 300)).json()["id"]

    resp = await _accept(client, headers_b, card_b, match_id)
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["rule"] == "stake_new_account"
    await db_session.refresh(alt)
    assert alt.balance == 5000  # nothing debited


async def test_pair_daily_limit(client, db_session, bot_token):
    await _config(db_session, stake_pair_daily_limit=1)
    _a, card_a, headers_a = await _player(client, db_session, 870041, bot_token)
    _b, card_b, headers_b = await _player(client, db_session, 870042, bot_token)

    first = (await _open(client, headers_a, card_a, 100)).json()["id"]
    assert (await _accept(client, headers_b, card_b, first)).status_code == 200
    # The limit counts staked matches started today, whatever their state.
    await db_session.execute(text("UPDATE penalty_matches SET status = 'finished' WHERE id = :id"), {"id": first})
    await db_session.commit()

    second = (await _open(client, headers_a, card_a, 100)).json()["id"]
    resp = await _accept(client, headers_b, card_b, second)
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["rule"] == "stake_pair_daily_limit"


async def test_daily_profit_cap(client, db_session, bot_token):
    await _config(db_session, stake_daily_profit_cap=1000)
    winner, card_a, headers_a = await _player(client, db_session, 870051, bot_token)
    _b, card_b, headers_b = await _player(client, db_session, 870052, bot_token)
    # Already won 900 net on stakes today.
    db_session.add(CoinTransaction(
        user_id=winner.id, amount=900, balance_before=5000, balance_after=5900,
        type=TransactionType.tactico_stake_win, description="test",
    ))
    await db_session.commit()

    resp = await _open(client, headers_a, card_a, 200)
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["rule"] == "stake_daily_profit_cap"
    assert (await _open(client, headers_a, card_a, 100)).status_code == 200

    # The opponent side is checked at accept too.
    match_id = (await _open(client, headers_b, card_b, 200)).json()["id"]
    resp = await _accept(client, headers_a, card_a, match_id)
    assert resp.status_code == 409 and resp.json()["error"]["details"]["rule"] == "stake_daily_profit_cap"


async def test_feature_flags_expose_the_max_stake(client, db_session, bot_token):
    _u, _c, headers = await _player(client, db_session, 870061, bot_token)
    body = (await client.get("/api/v1/feature-flags", headers=headers)).json()
    assert body["stake_max_coins"] == 500
