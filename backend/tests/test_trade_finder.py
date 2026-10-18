"""«Поиск обменов» (services/trade_finder_service.py): «Ищу» / «Отдаю» lists
and partner matching."""
from datetime import date, datetime, timedelta, timezone

import pytest

import app.core.rate_limit as rate_limit_module
from app.models.enums import CardSource, Rarity
from app.models.player import Player
from app.models.user import User
from app.models.user_activity import UserDailyActivity
from app.services.card_creation import create_user_card
from app.services.game_config_service import get_config
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1/trades/finder"


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _register(client, db_session, telegram_id, bot_token, veteran=True):
    headers = telegram_headers(telegram_id, bot_token)
    assert (await client.post("/api/v1/auth/session", headers=headers)).status_code == 200
    user = await get_user_by_telegram_id(db_session, telegram_id)
    if veteran:
        user.created_at = datetime.now(timezone.utc) - timedelta(days=30)
        for i in range(1, 4):
            db_session.add(UserDailyActivity(user_id=user.id, day=date.today() - timedelta(days=i)))
    user.last_seen_at = datetime.now(timezone.utc)
    await db_session.commit()
    return user, headers


async def _card(db_session, owner: User, player=None, **fields):
    player = player or await create_player(db_session, rarity=Rarity.common)
    card = await create_user_card(db_session, owner.id, player.id, CardSource.seed)
    for key, value in fields.items():
        setattr(card, key, value)
    await db_session.commit()
    return card


async def _wish(client, headers, kind, player_id):
    return await client.put(f"{API}/wishes", headers=headers, json={"kind": kind, "player_id": player_id})


# --- lists ------------------------------------------------------------------------------------


async def test_add_and_remove_wishes(client, db_session, bot_token):
    user, headers = await _register(client, db_session, 780001, bot_token)
    wanted = await create_player(db_session, rarity=Rarity.rare)
    mine = await _card(db_session, user)

    assert (await _wish(client, headers, "want", wanted.id)).status_code == 200
    body = (await _wish(client, headers, "give", mine.player_id)).json()
    assert [p["id"] for p in body["wants"]] == [wanted.id]
    assert [p["id"] for p in body["gives"]] == [mine.player_id]
    # Adding twice is a no-op.
    assert len((await _wish(client, headers, "want", wanted.id)).json()["wants"]) == 1

    body = (await client.delete(f"{API}/wishes/want/{wanted.id}", headers=headers)).json()
    assert body["wants"] == []


async def test_give_list_needs_an_owned_card(client, db_session, bot_token):
    _user, headers = await _register(client, db_session, 780011, bot_token)
    other = await create_player(db_session)
    resp = await _wish(client, headers, "give", other.id)
    assert resp.status_code == 409
    assert "которая у тебя есть" in resp.json()["error"]["message"]


async def test_list_limits_and_rules(client, db_session, bot_token):
    user, headers = await _register(client, db_session, 780021, bot_token)
    config = await get_config(db_session)
    config.trade_finder_max_wants = 2
    await db_session.commit()

    players = [await create_player(db_session) for _ in range(3)]
    assert (await _wish(client, headers, "want", players[0].id)).status_code == 200
    assert (await _wish(client, headers, "want", players[1].id)).status_code == 200
    over = await _wish(client, headers, "want", players[2].id)
    assert over.status_code == 409 and "не больше 2" in over.json()["error"]["message"]

    diamond = await create_player(db_session, rarity=Rarity.diamond, rating=60)
    assert (await _wish(client, headers, "want", diamond.id)).status_code == 409

    card = await _card(db_session, user, player=players[0])
    both = await _wish(client, headers, "give", card.player_id)  # already in «Ищу»
    assert both.status_code == 409


# --- matching ---------------------------------------------------------------------------------


async def test_mutual_match_is_found_from_both_sides(client, db_session, bot_token):
    alice, alice_headers = await _register(client, db_session, 780101, bot_token)
    bob, bob_headers = await _register(client, db_session, 780102, bot_token)
    x = await _card(db_session, bob)    # Alice wants X, Bob has it
    y = await _card(db_session, alice)  # Bob wants Y, Alice gives it
    await _wish(client, alice_headers, "want", x.player_id)
    await _wish(client, alice_headers, "give", y.player_id)
    await _wish(client, bob_headers, "want", y.player_id)

    matches = (await client.get(f"{API}/matches", headers=alice_headers)).json()
    assert len(matches) == 1
    m = matches[0]
    assert m["user"]["id"] == bob.id and m["mutual"] is True
    assert [(c["card_id"], c["player"]["id"]) for c in m["they_have"]] == [(x.id, x.player_id)]
    assert [c["card_id"] for c in m["they_want"]] == [y.id]

    # Bob sees Alice: she has Y (in her «Отдаю») — one-sided for him, since he lists nothing to give.
    bob_matches = (await client.get(f"{API}/matches", headers=bob_headers)).json()
    assert [(b["user"]["id"], b["they_have"][0]["card_id"], b["they_have"][0]["marked_to_give"]) for b in bob_matches] == [
        (alice.id, y.id, True)
    ]


async def test_spare_copy_counts_as_giveable(client, db_session, bot_token):
    alice, alice_headers = await _register(client, db_session, 780111, bot_token)
    bob, bob_headers = await _register(client, db_session, 780112, bot_token)
    y = await _card(db_session, alice)
    await _card(db_session, alice, player=await db_session.get(Player, y.player_id))  # second copy
    await _wish(client, bob_headers, "want", y.player_id)

    matches = (await client.get(f"{API}/matches", headers=alice_headers)).json()
    assert [m["user"]["id"] for m in matches] == [bob.id]
    assert matches[0]["they_want"][0]["player"]["id"] == y.player_id


async def test_partner_filters(client, db_session, bot_token):
    alice, alice_headers = await _register(client, db_session, 780121, bot_token)
    hidden_owner, _ = await _register(client, db_session, 780122, bot_token)
    sleeper, _ = await _register(client, db_session, 780123, bot_token)
    newbie, _ = await _register(client, db_session, 780124, bot_token, veteran=False)
    locked_owner, _ = await _register(client, db_session, 780125, bot_token)
    good, _ = await _register(client, db_session, 780126, bot_token)

    wanted = await create_player(db_session, rarity=Rarity.rare)
    await _card(db_session, hidden_owner, player=wanted, hidden_from_trade=True)
    await _card(db_session, sleeper, player=wanted)
    sleeper.last_seen_at = datetime.now(timezone.utc) - timedelta(days=30)
    await _card(db_session, newbie, player=wanted)               # too new to give
    await _card(db_session, locked_owner, player=wanted, is_in_lineup=True)
    await _card(db_session, good, player=wanted)
    await db_session.commit()
    await _wish(client, alice_headers, "want", wanted.id)

    matches = (await client.get(f"{API}/matches", headers=alice_headers)).json()
    assert [m["user"]["id"] for m in matches] == [good.id]


async def test_no_wishes_no_matches(client, db_session, bot_token):
    _user, headers = await _register(client, db_session, 780131, bot_token)
    assert (await client.get(f"{API}/matches", headers=headers)).json() == []
