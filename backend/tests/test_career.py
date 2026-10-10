"""Карьера тренера: league setup, schedule, lazy round resolution, fatigue,
rewards, friend seasons — plus the friends feature it builds on."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.core.timeutil import app_timezone
from app.models.card import UserCard
from app.models.career import CareerParticipant, CareerSeason
from app.models.enums import CardSource, Position
from app.models.trophy import TrophyDefinition, UserTrophy
from app.models.user import User
from app.services import career_service
from app.services.club_formation_service import get_formation_slots
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1"
_serial = {"n": 90000}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _player_with_cards(client, db_session, bot_token, tg_id, rating=75):
    await client.post(f"{API}/auth/session", headers=telegram_headers(tg_id, bot_token))
    user = await get_user_by_telegram_id(db_session, tg_id)
    positions = [s.ideal_position for s in get_formation_slots("4-3-3")]
    positions += [Position.GK, Position.CB, Position.CM, Position.ST, Position.RW]
    for pos in positions:
        player = await create_player(db_session, rating=rating, position=pos)
        _serial["n"] += 1
        db_session.add(UserCard(owner_id=user.id, player_id=player.id, source=CardSource.seed, serial_number=_serial["n"]))
    await db_session.commit()
    return user.id, telegram_headers(tg_id, bot_token)


def test_double_round_robin_meets_everyone_twice():
    rounds = career_service.double_round_robin()
    assert len(rounds) == 14
    meetings: dict[tuple[int, int], int] = {}
    for pairs in rounds:
        teams = [t for pair in pairs for t in pair]
        assert sorted(teams) == list(range(8))  # everyone plays exactly once a round
        for home, away in pairs:
            meetings[(home, away)] = meetings.get((home, away), 0) + 1
    # each ordered pair (home, away) exactly once = two meetings, one at each ground
    assert len(meetings) == 56 and set(meetings.values()) == {1}


def test_schedule_two_rounds_a_day_for_a_week():
    tz = app_timezone()
    now = datetime(2026, 10, 12, 11, 30, tzinfo=tz)  # 11:30 -> 12:00 is too soon (< 1h)
    schedule = [datetime.fromisoformat(s).astimezone(tz) for s in career_service.build_schedule(now)]
    assert len(schedule) == 14
    assert schedule[0] == datetime(2026, 10, 12, 19, 0, tzinfo=tz)
    assert {(t.hour, t.minute) for t in schedule} == {(12, 0), (19, 0)}
    assert (schedule[-1] - schedule[0]) == timedelta(days=6, hours=17)


async def test_solo_season_plays_out_with_rewards(client, db_session, bot_token):
    user_id, headers = await _player_with_cards(client, db_session, bot_token, 860001)
    db_session.add(TrophyDefinition(code="career_champion", name="Чемпион карьеры", is_active=True))
    await db_session.commit()

    resp = await client.post(f"{API}/career/seasons", headers=headers, json={"difficulty": "amateur"})
    assert resp.status_code == 200, resp.text
    season = resp.json()["season"]
    assert season["status"] == "active" and len(season["teams"]) == 8
    assert sum(t["is_bot"] for t in season["teams"]) == 7
    assert len(season["squad"]) == 16 and len(season["lineup"]) == 11
    assert len(season["schedule"]) == 14 and season["rounds_played"] == 0

    # A second season while one is running is refused.
    assert (await client.post(f"{API}/career/seasons", headers=headers, json={})).status_code == 409

    balance_before = (await db_session.get(User, user_id)).balance
    season_id = season["id"]
    later = datetime.now(timezone.utc) + timedelta(days=8)
    assert await career_service.resolve_due(db_session, season_id, now=later) == 14
    # Re-running is a no-op: rounds are never played twice.
    assert await career_service.resolve_due(db_session, season_id, now=later) == 0

    db_session.expire_all()
    row = await db_session.get(CareerSeason, season_id)
    assert row.status == "finished" and row.rounds_played == 14
    table = career_service.standings(row.state)
    assert sum(r["played"] for r in table) == 14 * 8
    part = (await db_session.execute(select(CareerParticipant).where(CareerParticipant.season_id == season_id))).scalar_one()
    assert part.final_place is not None and part.coins_earned > 0
    assert (await db_session.get(User, user_id)).balance == balance_before + part.coins_earned
    trophies = (await db_session.execute(select(UserTrophy).where(UserTrophy.user_id == user_id))).scalars().all()
    assert len(trophies) == (1 if part.final_place == 1 else 0)
    # Fatigue/injury state was tracked for squad cards.
    assert set(part.condition) <= {str(c) for c in part.squad_card_ids}


async def test_lineup_only_accepts_squad_cards_in_legal_slots(client, db_session, bot_token):
    user_id, headers = await _player_with_cards(client, db_session, bot_token, 860002)
    season = (await client.post(f"{API}/career/seasons", headers=headers, json={"difficulty": "pro"})).json()["season"]
    lineup = season["lineup"]
    gk_slot = next(s["code"] for s in season["slots"] if s["category"] == "GK")
    st_slot = next(s["code"] for s in season["slots"] if s["category"] == "FWD")

    swapped = {**lineup, gk_slot: lineup[st_slot]}
    resp = await client.put(f"{API}/career/lineup", headers=headers, json={"slots": swapped, "mentality": "ATTACKING"})
    assert resp.status_code == 409

    resp = await client.put(f"{API}/career/lineup", headers=headers, json={"slots": lineup, "mentality": "ATTACKING"})
    assert resp.status_code == 200 and resp.json()["season"]["mentality"] == "ATTACKING"


async def test_friend_season_invite_accept_and_expiry(client, db_session, bot_token):
    a_id, a_headers = await _player_with_cards(client, db_session, bot_token, 860003)
    b_id, b_headers = await _player_with_cards(client, db_session, bot_token, 860004)
    c_id, c_headers = await _player_with_cards(client, db_session, bot_token, 860005)

    # Only friends can be invited.
    resp = await client.post(f"{API}/career/seasons", headers=a_headers, json={"friend_id": b_id})
    assert resp.status_code == 403

    assert (await client.post(f"{API}/friends/requests", headers=a_headers, json={"user_id": b_id})).json()["status"] == "pending"
    incoming = (await client.get(f"{API}/friends", headers=b_headers)).json()["incoming"]
    assert (await client.post(f"{API}/friends/requests/{incoming[0]['request_id']}/accept", headers=b_headers)).status_code == 204

    season = (await client.post(f"{API}/career/seasons", headers=a_headers, json={"friend_id": b_id})).json()["season"]
    assert season["status"] == "pending"
    invite = (await client.get(f"{API}/career", headers=b_headers)).json()["invite"]
    assert invite["season_id"] == season["id"]

    resp = await client.post(f"{API}/career/seasons/{season['id']}/invite", headers=b_headers, json={"accept": True})
    assert resp.status_code == 200, resp.text
    active = resp.json()["season"]
    assert active["status"] == "active"
    assert sum(not t["is_bot"] for t in active["teams"]) == 2
    # The two friends meet twice: once at each ground.
    meetings = [m for r in active["rounds"] for m in r["matches"] if {m["home"], m["away"]} == {0, 1}]
    assert len(meetings) == 2

    # A second pair: the invite is never answered and expires -> bot takes the slot.
    assert (await client.post(f"{API}/friends/requests", headers=c_headers, json={"user_id": b_id})).status_code == 200
    # b is busy in a season, so c invites nobody; instead test expiry with a fresh friend pair.
    d_id, d_headers = await _player_with_cards(client, db_session, bot_token, 860006)
    await client.post(f"{API}/friends/requests", headers=c_headers, json={"user_id": d_id})
    req = (await client.get(f"{API}/friends", headers=d_headers)).json()["incoming"][0]["request_id"]
    await client.post(f"{API}/friends/requests/{req}/accept", headers=d_headers)
    pending = (await client.post(f"{API}/career/seasons", headers=c_headers, json={"friend_id": d_id})).json()["season"]
    later = datetime.now(timezone.utc) + timedelta(hours=25)
    await career_service.resolve_due(db_session, pending["id"], now=later)
    db_session.expire_all()
    row = await db_session.get(CareerSeason, pending["id"])
    assert row.status == "active"
    assert sum(t.get("user_id") is None for t in row.state["teams"]) == 7


async def test_leaving_turns_remaining_matches_into_defeats(client, db_session, bot_token):
    user_id, headers = await _player_with_cards(client, db_session, bot_token, 860007)
    season_id = (await client.post(f"{API}/career/seasons", headers=headers, json={})).json()["season"]["id"]
    assert (await client.post(f"{API}/career/leave", headers=headers)).status_code == 204
    await career_service.resolve_due(db_session, season_id, now=datetime.now(timezone.utc) + timedelta(days=8))
    db_session.expire_all()
    row = await db_session.get(CareerSeason, season_id)
    mine = [m for r in row.state["results"] for m in r if 0 in (m["home"], m["away"])]
    assert len(mine) == 14
    assert all((m["hs"], m["as"]) == ((0, 3) if m["home"] == 0 else (3, 0)) for m in mine)
    part = (await db_session.execute(select(CareerParticipant).where(CareerParticipant.season_id == season_id))).scalar_one()
    assert part.final_place is None and part.coins_earned == 0


async def test_friends_requests_relation_and_feed(client, db_session, bot_token):
    a_id, a_headers = await _player_with_cards(client, db_session, bot_token, 860010)
    b_id, b_headers = await _player_with_cards(client, db_session, bot_token, 860011)
    assert (await client.get(f"{API}/friends/relation/{b_id}", headers=a_headers)).json()["relation"] == "none"
    await client.post(f"{API}/friends/requests", headers=a_headers, json={"user_id": b_id})
    assert (await client.get(f"{API}/friends/relation/{b_id}", headers=a_headers)).json()["relation"] == "outgoing"
    assert (await client.get(f"{API}/profile/me/attention", headers=b_headers)).json()["friend_requests"] == 1

    # b asking back turns the pending request into a friendship.
    assert (await client.post(f"{API}/friends/requests", headers=b_headers, json={"user_id": a_id})).json()["status"] == "accepted"
    assert (await client.get(f"{API}/friends/relation/{a_id}", headers=b_headers)).json()["relation"] == "friends"
    assert [f["user"]["id"] for f in (await client.get(f"{API}/friends", headers=a_headers)).json()["friends"]] == [b_id]
    assert (await client.post(f"{API}/friends/requests", headers=a_headers, json={"user_id": a_id})).status_code == 409

    trophy = TrophyDefinition(code="feed_test", name="Тестовый трофей", is_active=True)
    db_session.add(trophy)
    await db_session.flush()
    db_session.add(UserTrophy(user_id=b_id, trophy_definition_id=trophy.id))
    await db_session.commit()
    feed = (await client.get(f"{API}/friends/feed", headers=a_headers)).json()
    assert feed and feed[0]["user"]["id"] == b_id and "Тестовый трофей" in feed[0]["text"]

    assert (await client.delete(f"{API}/friends/{b_id}", headers=a_headers)).status_code == 204
    assert (await client.get(f"{API}/friends", headers=b_headers)).json()["friends"] == []
