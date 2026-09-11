from datetime import datetime, timezone

import pytest_asyncio

from app.models.enums import Position
from app.models.tournament_match import TournamentMatch
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """create_club seeds a starting squad on every creation — same seeding every other club
    test file needs (see test_clubs.py's identical fixture)."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _make_club(client, db_session, bot_token, telegram_id):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    resp = await client.post(
        "/api/v1/clubs", headers=headers,
        json={"name": f"Stats Club {telegram_id}", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 200
    club_id = resp.json()["id"]
    captain = await get_user_by_telegram_id(db_session, telegram_id)
    return club_id, captain, headers


async def test_stats_with_no_matches_is_all_zero(client, db_session, bot_token):
    _club_id, _captain, headers = await _make_club(client, db_session, bot_token, 880101)

    resp = await client.get("/api/v1/clubs/me/stats", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "matches_played": 0, "wins": 0, "draws": 0, "losses": 0,
        "goals_scored": 0, "goals_conceded": 0,
        "win_rate_pct": 0.0, "draw_rate_pct": 0.0, "loss_rate_pct": 0.0,
        "goals_scored_per_match": 0.0, "goals_conceded_per_match": 0.0,
    }


async def test_stats_aggregate_wins_draws_losses_across_tournaments_and_perspectives(client, db_session, bot_token):
    """4 matches for one club, spanning two different (fake) tournament ids and both the
    club_a and club_b positions, to exercise: (1) the all-time/all-tournament aggregation
    (not scoped to a single tournament_id) and (2) the perspective-flip logic that reads
    own/opponent score correctly regardless of which side the club is listed on."""
    club_id, _captain, headers = await _make_club(client, db_session, bot_token, 880102)
    now = datetime.now(timezone.utc)

    matches = [
        # Win as club_a, tournament 1.
        TournamentMatch(tournament_id=1, round_number=1, club_a_id=club_id, club_b_id=9001, score_a=3, score_b=1, event_log=[], simulated_at=now),
        # Win as club_b, tournament 1.
        TournamentMatch(tournament_id=1, round_number=2, club_a_id=9002, club_b_id=club_id, score_a=0, score_b=2, event_log=[], simulated_at=now),
        # Draw as club_a, tournament 2 (a different, older tournament — must still count).
        TournamentMatch(tournament_id=2, round_number=1, club_a_id=club_id, club_b_id=9003, score_a=1, score_b=1, event_log=[], simulated_at=now),
        # Loss as club_b, tournament 2.
        TournamentMatch(tournament_id=2, round_number=2, club_a_id=9004, club_b_id=club_id, score_a=2, score_b=0, event_log=[], simulated_at=now),
    ]
    for m in matches:
        db_session.add(m)
    await db_session.commit()

    resp = await client.get("/api/v1/clubs/me/stats", headers=headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["matches_played"] == 4
    assert body["wins"] == 2
    assert body["draws"] == 1
    assert body["losses"] == 1
    assert body["goals_scored"] == 6   # 3 + 2 + 1 + 0
    assert body["goals_conceded"] == 4  # 1 + 0 + 1 + 2
    assert body["win_rate_pct"] == 50.0
    assert body["draw_rate_pct"] == 25.0
    assert body["loss_rate_pct"] == 25.0
    assert body["goals_scored_per_match"] == 1.5
    assert body["goals_conceded_per_match"] == 1.0


async def test_stats_requires_club_membership(client, db_session, bot_token):
    headers = telegram_headers(880103, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.get("/api/v1/clubs/me/stats", headers=headers)
    assert resp.status_code == 404
