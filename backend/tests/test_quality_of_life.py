"""One-tap helpers: auto-filled squads and "sell spare duplicates"."""
import pytest
from sqlalchemy import select
from sqlalchemy.orm import joinedload

import app.core.rate_limit as rate_limit_module
from app.models.card import UserCard
from app.models.enums import CardSource, Position, Rarity
from app.models.user import User
from app.services.club_formation_service import get_formation_slots
from app.services.lineup_service import FORMATION_SLOTS
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1"
_serial = {"n": 5000}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post(f"{API}/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def _card(db_session, owner_id, player, **kw) -> UserCard:
    _serial["n"] += 1
    card = UserCard(owner_id=owner_id, player_id=player.id, source=CardSource.seed, serial_number=_serial["n"], **kw)
    db_session.add(card)
    await db_session.commit()
    await db_session.refresh(card)
    return card


async def test_auto_arena_lineup_picks_best_fitting_cards(client, db_session, bot_token):
    user = await _register(client, db_session, 830001, bot_token)
    best_ids = {}
    for slot in FORMATION_SLOTS:
        weak = await create_player(db_session, rating=60, position=slot.ideal_position)
        strong = await create_player(db_session, rating=85, position=slot.ideal_position)
        await _card(db_session, user.id, weak)
        best_ids[slot.code] = (await _card(db_session, user.id, strong)).id
    # A stronger card locked in a trade must be skipped.
    locked_star = await create_player(db_session, rating=99, position=Position.GK)
    await _card(db_session, user.id, locked_star, is_locked_in_trade=True)

    resp = await client.post(f"{API}/lineups/templates/1/auto", headers=telegram_headers(830001, bot_token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_complete"] is True
    assert {s["slot_code"]: s["card"]["id"] for s in body["slots"]} == best_ids


async def test_auto_arena_lineup_respects_diamond_limit(client, db_session, bot_token):
    user = await _register(client, db_session, 830002, bot_token)
    for slot in FORMATION_SLOTS:
        diamond = await create_player(db_session, rating=95, position=slot.ideal_position, rarity=Rarity.diamond)
        plain = await create_player(db_session, rating=70, position=slot.ideal_position)
        await _card(db_session, user.id, diamond)
        await _card(db_session, user.id, plain)
    resp = await client.post(f"{API}/lineups/templates/1/auto", headers=telegram_headers(830002, bot_token))
    assert resp.status_code == 200, resp.text
    rarities = [s["card"]["player"]["rarity"] for s in resp.json()["slots"]]
    assert rarities.count("diamond") == 1  # default match_max_diamond_cards


async def test_auto_tournament_squad_and_copy_from_arena(client, db_session, bot_token):
    user = await _register(client, db_session, 830003, bot_token)
    headers = telegram_headers(830003, bot_token)
    for slot in get_formation_slots("4-3-3"):
        for rating in (65, 80):
            player = await create_player(db_session, rating=rating, position=slot.ideal_position)
            await _card(db_session, user.id, player)

    resp = await client.post(f"{API}/player-tournaments/squads/1/auto", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_complete"] is True

    # Arena lineup built from the WEAKER copies; copying it must keep them.
    weak_slots = []
    cards = (await db_session.execute(
        select(UserCard).where(UserCard.owner_id == user.id).options(joinedload(UserCard.player))
    )).unique().scalars().all()
    for slot in FORMATION_SLOTS:
        weak = next(c for c in cards if c.player.position == slot.ideal_position and c.player.rating == 65
                    and c.id not in {w["user_card_id"] for w in weak_slots})
        weak_slots.append({"slot_code": slot.code, "user_card_id": weak.id})
    assert (await client.put(f"{API}/lineups/active", headers=headers, json={"slots": weak_slots})).status_code == 200

    resp = await client.post(f"{API}/player-tournaments/squads/1/auto?copy_from_arena=true", headers=headers)
    assert resp.status_code == 200, resp.text
    squad_ids = {s["user_card_id"] for s in resp.json()["slots"]}
    assert {w["user_card_id"] for w in weak_slots} <= squad_ids


async def test_auto_squad_with_no_cards_is_a_clear_error(client, db_session, bot_token):
    await _register(client, db_session, 830004, bot_token)
    resp = await client.post(f"{API}/lineups/templates/1/auto", headers=telegram_headers(830004, bot_token))
    assert resp.status_code == 409


async def test_sell_duplicates_keeps_one_and_protects_skilled_locked_and_diamond(client, db_session, bot_token):
    user = await _register(client, db_session, 830005, bot_token)
    user_id = user.id
    headers = telegram_headers(830005, bot_token)
    a = await create_player(db_session, position=Position.ST, quick_sell_price=10)
    b = await create_player(db_session, position=Position.CB, quick_sell_price=20)
    c = await create_player(db_session, position=Position.CM, quick_sell_price=30)
    d = await create_player(db_session, position=Position.GK, rarity=Rarity.diamond, quick_sell_price=500)
    a_skilled = await _card(db_session, user_id, a, skill_code="sniper", skill_level=1)
    a1, a2 = await _card(db_session, user_id, a), await _card(db_session, user_id, a)
    b_lineup = await _card(db_session, user_id, b, is_in_lineup=True)
    b1 = await _card(db_session, user_id, b)
    c_only = await _card(db_session, user_id, c)
    await _card(db_session, user_id, d)
    await _card(db_session, user_id, d)

    preview = (await client.post(f"{API}/collection/cards/sell-duplicates", headers=headers, json={"preview": True})).json()
    assert preview["preview"] is True and preview["sold_count"] == 3 and preview["coins_earned"] == 10 + 10 + 20

    kept_ids = {a_skilled.id, b_lineup.id, c_only.id}
    sold_ids = {a1.id, a2.id, b1.id}
    balance_before = (await db_session.get(User, user_id)).balance
    done = (await client.post(f"{API}/collection/cards/sell-duplicates", headers=headers, json={"preview": False})).json()
    assert done["preview"] is False and done["sold_count"] == 3
    assert done["new_balance"] == balance_before + 40

    remaining = set((await db_session.execute(select(UserCard.id).where(UserCard.owner_id == user_id))).scalars().all())
    assert kept_ids <= remaining
    assert not (sold_ids & remaining)
    assert len(remaining) == 5  # 3 kept + 2 diamonds untouched


async def test_game_limits_report_when_an_exhausted_game_frees_up(client, db_session, bot_token):
    from datetime import datetime, timedelta, timezone

    user = await _register(client, db_session, 830006, bot_token)
    headers = telegram_headers(830006, bot_token)
    limit = (await client.get(f"{API}/games/limits", headers=headers)).json()["hourly_limit"]
    started = datetime.now(timezone.utc) - timedelta(minutes=20)
    user.match_hourly_attempts = limit
    user.match_hour_started_at = started
    await db_session.commit()

    body = (await client.get(f"{API}/games/limits", headers=headers)).json()
    assert body["arena"] == 0
    assert set(body["resets_at"]) == {"arena"}
    resets = datetime.fromisoformat(body["resets_at"]["arena"].replace("Z", "+00:00"))
    assert abs((resets - (started + timedelta(hours=1))).total_seconds()) < 2


async def test_bench_upgrades_suggest_single_swaps(client, db_session, bot_token):
    user = await _register(client, db_session, 830007, bot_token)
    headers = telegram_headers(830007, bot_token)
    slot = FORMATION_SLOTS[0]
    weak = await _card(db_session, user.id, await create_player(db_session, rating=60, position=slot.ideal_position))
    strong = await _card(db_session, user.id, await create_player(db_session, rating=84, position=slot.ideal_position))
    resp = await client.put(f"{API}/lineups/active", headers=headers,
                            json={"slots": [{"slot_code": slot.code, "user_card_id": weak.id}]})
    assert resp.status_code == 200, resp.text

    hints = (await client.get(f"{API}/lineups/templates/1/bench-upgrades", headers=headers)).json()
    hint = next(h for h in hints if h["slot_code"] == slot.code)
    assert hint["current_card_id"] == weak.id and hint["suggested_card_id"] == strong.id
    assert hint["gain"] == 24
    # The strong card is now suggested for its slot only — never twice.
    assert sum(h["suggested_card_id"] == strong.id for h in hints) == 1


async def test_attention_counts_incoming_trades(client, db_session, bot_token):
    from datetime import datetime, timedelta, timezone

    from app.models.enums import TradeStatus
    from app.models.trade import TradeOffer

    receiver = await _register(client, db_session, 830008, bot_token)
    sender = await _register(client, db_session, 830009, bot_token)
    db_session.add(TradeOffer(sender_id=sender.id, receiver_id=receiver.id, status=TradeStatus.pending,
                              expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
    db_session.add(TradeOffer(sender_id=sender.id, receiver_id=receiver.id, status=TradeStatus.pending,
                              expires_at=datetime.now(timezone.utc) - timedelta(days=1)))
    await db_session.commit()
    body = (await client.get(f"{API}/profile/me/attention", headers=telegram_headers(830008, bot_token))).json()
    assert body["incoming_trades"] == 1
    assert body["match_challenges"] == 0 and body["active_friend_matches"] == 0
