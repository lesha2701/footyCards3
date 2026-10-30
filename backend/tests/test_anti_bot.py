"""Anti-bot (services/anti_bot_service.py): «усталость» after a too long
stretch of play, the daily ranked limit, and the admin «похоже на ботов» list."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.core.rate_limit as rate_limit_module
from app.models.game import GameSession
from app.models.enums import GameSessionStatus, GameType, MatchDifficulty
from app.models.user import User
from app.services import admin_antifraud_service, anti_bot_service
from app.services.game_config_service import get_config
from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers

CONFIG = SimpleNamespace(anti_bot_enabled=True, anti_bot_max_streak_hours=20, anti_bot_rest_hours=4, ranked_daily_limit=40)
T0 = datetime(2026, 10, 30, 8, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


def _user(**fields):
    base = dict(play_streak_started_at=None, last_play_at=None, rest_required_until=None, game_rewards_blocked_flag=False)
    base.update(fields)
    return User(**base)


def _play(user, at):
    values = anti_bot_service.next_state(user, CONFIG, at)
    if values:
        for key, value in values.items():
            setattr(user, key, value)


def test_a_human_who_sleeps_never_gets_tired():
    user = _user()
    for day in range(3):
        for hour in range(8, 24, 2):  # 08:00-22:00 every two hours, sleep at night
            _play(user, T0 + timedelta(days=day, hours=hour - 8))
    assert user.rest_required_until is None


def test_a_script_playing_around_the_clock_gets_tired_and_recovers_after_rest():
    user = _user()
    at = T0
    while at < T0 + timedelta(hours=21):
        _play(user, at)
        at += timedelta(minutes=20)
    assert user.rest_required_until is not None
    assert user.rest_required_until > at - timedelta(minutes=20)

    # Keeps going: the rest is pushed forward from the last action.
    _play(user, at + timedelta(hours=1))
    assert user.rest_required_until == at + timedelta(hours=1) + timedelta(hours=4)

    # Rests four hours: a fresh stretch, rewards back.
    back = at + timedelta(hours=5, minutes=1)
    _play(user, back)
    assert user.play_streak_started_at == back
    assert user.rest_required_until <= back


def test_game_rewards_blocked_covers_the_admin_flag_and_the_rest():
    now = datetime.now(timezone.utc)
    assert _user(game_rewards_blocked_flag=True).game_rewards_blocked is True
    assert _user(rest_required_until=now + timedelta(hours=1)).game_rewards_blocked is True
    assert _user(rest_required_until=now - timedelta(hours=1)).game_rewards_blocked is False
    flagged = _user()
    flagged.game_rewards_blocked = True  # the setter writes the admin flag
    assert flagged.game_rewards_blocked_flag is True


def test_only_game_posts_count_as_play():
    assert anti_bot_service.is_game_action("POST", "/api/v1/games/memory/start")
    assert anti_bot_service.is_game_action("POST", "/api/v1/tactico/matches/5/pick")
    assert not anti_bot_service.is_game_action("GET", "/api/v1/tactico/matches/5")
    assert not anti_bot_service.is_game_action("POST", "/api/v1/packs/1/open")
    assert not anti_bot_service.is_game_action("POST", "/api/v1/gamesx")


async def test_game_post_tracks_play_and_limits_show_the_rest(client, db_session, bot_token):
    headers = telegram_headers(990001, bot_token)
    assert (await client.post("/api/v1/auth/session", headers=headers)).status_code == 200
    user = await get_user_by_telegram_id(db_session, 990001)
    await get_config(db_session)
    await client.post("/api/v1/games/memory/start", headers=headers, json={})
    await db_session.refresh(user)
    assert user.last_play_at is not None and user.play_streak_started_at is not None

    user.play_streak_started_at = datetime.now(timezone.utc) - timedelta(hours=21)
    user.last_play_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    await db_session.commit()
    await client.post("/api/v1/games/memory/start", headers=headers, json={})
    limits = (await client.get("/api/v1/games/limits", headers=headers)).json()
    assert limits["rest_until"] is not None and limits["rest_hours"] == 4


async def test_ranked_limit_for_arena(db_session):
    from app.models.match import Match

    user = User(telegram_id=990101, username="r", balance=0)
    db_session.add(user)
    await db_session.commit()
    config = await get_config(db_session)
    config.ranked_daily_limit = 2
    await db_session.commit()
    for _ in range(2):
        db_session.add(Match(user_id=user.id, opponent_name="bot", difficulty=MatchDifficulty.easy, user_team_strength=70,
                     opponent_team_strength=70, user_score=1, opponent_score=0))
    await db_session.commit()
    assert await anti_bot_service.ranked_allowed(db_session, user, config, "arena") is True  # 2 of 2 (the current one included)
    db_session.add(Match(user_id=user.id, opponent_name="bot", difficulty=MatchDifficulty.easy, user_team_strength=70,
                     opponent_team_strength=70, user_score=1, opponent_score=0))
    await db_session.commit()
    assert await anti_bot_service.ranked_allowed(db_session, user, config, "arena") is False


async def test_bot_suspects_list(db_session):
    bot = User(telegram_id=990201, username="bot", balance=0)
    human = User(telegram_id=990202, username="human", balance=0)
    db_session.add_all([bot, human])
    await db_session.commit()
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for i in range(24 * 6 * 3):  # every 10 minutes for 3 days
        db_session.add(GameSession(user_id=bot.id, game_type=GameType.memory_sequence, status=GameSessionStatus.won,
                                   created_at=now - timedelta(minutes=10 * i)))
    for d in range(3):
        for h in range(10, 22):  # 12 hours a day, sleeps
            for m in (0, 20, 40):
                db_session.add(GameSession(user_id=human.id, game_type=GameType.memory_sequence, status=GameSessionStatus.won,
                                           created_at=now - timedelta(days=d + 1) + timedelta(hours=h - now.hour, minutes=m)))
    await db_session.commit()

    rows = await admin_antifraud_service.bot_suspects(db_session, days=7, min_games=50)
    by_name = {r["username"]: r for r in rows}
    assert by_name["bot"]["days_without_sleep"] >= 2
    assert by_name["human"]["days_without_sleep"] == 0
    assert rows[0]["username"] == "bot"

    changed = await admin_antifraud_service.set_rewards_blocked(db_session, [bot.id], True)
    await db_session.commit()
    await db_session.refresh(bot)
    assert changed == [bot.id] and bot.game_rewards_blocked_flag is True
