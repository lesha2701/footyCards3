import pytest

import app.core.rate_limit as rate_limit_module
from app.models.enums import (
    GameSessionStatus,
    GameType,
    MatchResult,
    PenaltyMatchStatus,
    TacticoMatchStatus,
    TacticoOpponentType,
)
from app.models.game import GameSession
from app.models.penalty import PenaltyMatch
from app.models.tactico import TacticoMatch
from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def test_league_rank_reflects_summed_rating(client, db_session, bot_token):
    low_headers = telegram_headers(770001, bot_token)
    await client.post("/api/v1/auth/session", headers=low_headers)
    low_user = await get_user_by_telegram_id(db_session, 770001)
    low_user.tactics_rating = 5
    db_session.add(low_user)

    high_headers = telegram_headers(770002, bot_token)
    await client.post("/api/v1/auth/session", headers=high_headers)
    high_user = await get_user_by_telegram_id(db_session, 770002)
    high_user.arena_rating = 10
    high_user.tactics_rating = 10
    high_user.penalty_rating = 10
    db_session.add(high_user)
    await db_session.commit()

    low_profile = await client.get("/api/v1/profile/me", headers=low_headers)
    high_profile = await client.get("/api/v1/profile/me", headers=high_headers)

    assert high_profile.json()["league_rank"] == 1
    assert low_profile.json()["league_rank"] == 2


async def test_profile_reports_tactico_record_across_bot_friend_and_online(client, db_session, bot_token):
    """result is stored from the row's own user_id's perspective — a match
    where this player is the opponent side must have its result flipped."""
    headers = telegram_headers(770003, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 770003)

    other_headers = telegram_headers(770004, bot_token)
    await client.post("/api/v1/auth/session", headers=other_headers)
    other = await get_user_by_telegram_id(db_session, 770004)

    db_session.add_all([
        # Bot win — user_id is always "me" for a bot match.
        TacticoMatch(
            user_id=user.id, opponent_name="Bot Team", opponent_type=TacticoOpponentType.bot,
            status=TacticoMatchStatus.finished, result=MatchResult.win,
        ),
        # Friend match where I'm the challenger and lost.
        TacticoMatch(
            user_id=user.id, opponent_user_id=other.id, opponent_name=other.full_display_name(),
            opponent_type=TacticoOpponentType.friend, status=TacticoMatchStatus.finished, result=MatchResult.loss,
        ),
        # Online match where I'm the OPPONENT side — stored result (win, from
        # the other user's perspective) must flip to a loss for me.
        TacticoMatch(
            user_id=other.id, opponent_user_id=user.id, opponent_name=user.full_display_name(),
            opponent_type=TacticoOpponentType.online, status=TacticoMatchStatus.finished, result=MatchResult.win,
        ),
        # A draw, again as the opponent side — a draw flips to a draw.
        TacticoMatch(
            user_id=other.id, opponent_user_id=user.id, opponent_name=user.full_display_name(),
            opponent_type=TacticoOpponentType.online, status=TacticoMatchStatus.finished, result=MatchResult.draw,
        ),
        # Still in progress — must not be counted.
        TacticoMatch(
            user_id=user.id, opponent_name="Bot Team", opponent_type=TacticoOpponentType.bot,
            status=TacticoMatchStatus.in_progress, result=None,
        ),
    ])
    await db_session.commit()

    resp = await client.get("/api/v1/profile/me", headers=headers)
    body = resp.json()
    assert body["tactics_matches_won"] == 1
    assert body["tactics_matches_drawn"] == 1
    assert body["tactics_matches_lost"] == 2


async def test_profile_reports_penalty_record_across_pvp_and_bot(client, db_session, bot_token):
    headers = telegram_headers(770005, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 770005)

    other_headers = telegram_headers(770006, bot_token)
    await client.post("/api/v1/auth/session", headers=other_headers)
    other = await get_user_by_telegram_id(db_session, 770006)

    db_session.add_all([
        # PvP win as the challenger.
        PenaltyMatch(
            user_id=user.id, opponent_user_id=other.id, opponent_name=other.full_display_name(),
            status=PenaltyMatchStatus.finished, result=MatchResult.win,
        ),
        # PvP loss as the opponent side (stored result "win" flips to a loss for me).
        PenaltyMatch(
            user_id=other.id, opponent_user_id=user.id, opponent_name=user.full_display_name(),
            status=PenaltyMatchStatus.finished, result=MatchResult.win,
        ),
        # Bot session, won.
        GameSession(user_id=user.id, game_type=GameType.penalty, status=GameSessionStatus.won),
        # Bot session, won then reward already claimed — still a win.
        GameSession(user_id=user.id, game_type=GameType.penalty, status=GameSessionStatus.rewarded),
        # Bot session, lost.
        GameSession(user_id=user.id, game_type=GameType.penalty, status=GameSessionStatus.lost),
        # Still in progress — must not be counted.
        GameSession(user_id=user.id, game_type=GameType.penalty, status=GameSessionStatus.in_progress),
        # A different game type's session must not leak into the penalty count.
        GameSession(user_id=user.id, game_type=GameType.memory_sequence, status=GameSessionStatus.won),
    ])
    await db_session.commit()

    resp = await client.get("/api/v1/profile/me", headers=headers)
    body = resp.json()
    assert body["penalty_matches_won"] == 3  # 1 PvP win + 2 bot wins (won + rewarded)
    assert body["penalty_matches_drawn"] == 0
    assert body["penalty_matches_lost"] == 2  # 1 PvP loss (flipped) + 1 bot loss
