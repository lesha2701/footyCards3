from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import GameSessionStatus, GameType, TaskCategory, TaskConditionType
from app.models.game import GameSession
from app.models.game_config import NEWBIE_DEFAULT_TASKS
from app.models.task import TaskDefinition
from app.models.user import User
from app.services import fergie_service, newbie_service, task_service
from app.services.game_config_service import get_config


async def _user(db, telegram_id=9100) -> User:
    joined = datetime.now(timezone.utc) - timedelta(days=1)
    user = User(telegram_id=telegram_id, username=f"u{telegram_id}", first_name="F", created_at=joined)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _played_out(db, user) -> int:
    out = await fergie_service.start(db, user)
    session = await db.get(GameSession, out.session_id)
    session.created_at = session.created_at - timedelta(seconds=fergie_service.MIN_SECONDS + 1)
    await db.commit()
    await fergie_service.finish(db, user, out.session_id)
    return out.session_id


async def _task(db, metric: str, target: int, code: str = "t", period: str = "daily") -> TaskDefinition:
    definition = TaskDefinition(
        code=code, name=code, category=TaskCategory.regular, condition_type=TaskConditionType.metric_counter,
        metric=metric, target_value=target, reward_coins=10, period=period,
    )
    db.add(definition)
    await db.commit()
    return definition


@pytest.mark.asyncio
async def test_a_match_cant_be_over_before_it_could_be(db_session):
    user = await _user(db_session)
    out = await fergie_service.start(db_session, user)
    with pytest.raises(ConflictError):
        await fergie_service.finish(db_session, user, out.session_id)
    assert await newbie_service.games_played(db_session, user, "game:fergie_time") == 0


@pytest.mark.asyncio
async def test_finishing_is_retryable_and_counts_once(db_session):
    user = await _user(db_session)
    session_id = await _played_out(db_session, user)
    balance = (await db_session.get(User, user.id)).balance
    again = await fergie_service.finish(db_session, user, session_id)
    assert again.reward_coins == (await get_config(db_session)).fergie_match_coins
    assert again.new_balance == balance  # paid once
    assert await newbie_service.games_played(db_session, user, "game:fergie_time") == 1


@pytest.mark.asyncio
async def test_a_match_pays_the_flat_fee_up_to_the_daily_cap(db_session):
    user = await _user(db_session)
    config = await get_config(db_session)
    config.fergie_match_coins, config.fergie_daily_limit = 150, 2
    await db_session.commit()
    start = (await db_session.get(User, user.id)).balance

    async def play():
        out = await fergie_service.start(db_session, user)
        session = await db_session.get(GameSession, out.session_id)
        session.created_at = session.created_at - timedelta(seconds=fergie_service.MIN_SECONDS + 1)
        await db_session.commit()
        return await fergie_service.finish(db_session, user, out.session_id)

    assert (await play()).reward_coins == 150
    second = await play()
    assert second.new_balance == start + 300
    third = await play()
    assert third.reward_coins == 0 and third.daily_cap_reached and third.new_balance == start + 300
    # Past the cap it still counts as played, for tasks.
    assert await newbie_service.games_played(db_session, user, "game:fergie_time") == 3


@pytest.mark.asyncio
async def test_a_blocked_player_gets_nothing(db_session):
    user = await _user(db_session)
    user.game_rewards_blocked = True
    await db_session.commit()
    out = await fergie_service.start(db_session, user)
    session = await db_session.get(GameSession, out.session_id)
    session.created_at = session.created_at - timedelta(seconds=fergie_service.MIN_SECONDS + 1)
    await db_session.commit()
    assert (await fergie_service.finish(db_session, user, out.session_id)).reward_coins == 0


@pytest.mark.asyncio
async def test_the_hourly_cap_stops_a_start(db_session):
    user = await _user(db_session)
    config = await get_config(db_session)
    config.hourly_game_limit = 1
    await db_session.commit()
    await fergie_service.start(db_session, user)
    with pytest.raises(ConflictError):
        await fergie_service.start(db_session, user)


@pytest.mark.asyncio
async def test_a_match_walked_out_of_doesnt_count(db_session):
    user = await _user(db_session)
    first = await fergie_service.start(db_session, user)
    await fergie_service.start(db_session, user)
    session = await db_session.get(GameSession, first.session_id)
    assert session.status == GameSessionStatus.expired
    with pytest.raises(ConflictError):
        await fergie_service.finish(db_session, user, first.session_id)


@pytest.mark.asyncio
async def test_someone_elses_match_is_not_found(db_session):
    user, other = await _user(db_session), await _user(db_session, 9101)
    out = await fergie_service.start(db_session, user)
    with pytest.raises(NotFoundError):
        await fergie_service.finish(db_session, other, out.session_id)


@pytest.mark.asyncio
async def test_a_played_task_counts_games_from_its_assignment(db_session):
    user = await _user(db_session)
    await _played_out(db_session, user)  # before the task: doesn't count
    await _task(db_session, "played:game:fergie_time", 2)
    config = await get_config(db_session)
    config.task_daily_slots, config.task_weekly_slots = 1, 0
    await db_session.commit()

    def only(listing):
        return listing.regular[0]

    assert only(await task_service.list_my_tasks(db_session, user)).progress == 0
    await _played_out(db_session, user)
    assert only(await task_service.list_my_tasks(db_session, user)).progress == 1
    await _played_out(db_session, user)
    assert only(await task_service.list_my_tasks(db_session, user)).is_completed


@pytest.mark.asyncio
async def test_a_switched_off_mode_gets_no_task(db_session):
    definition = await _task(db_session, "played:blackjack", 1)
    config = await get_config(db_session)
    config.blackjack_enabled = False
    await db_session.commit()
    assert await task_service._pick(db_session, "daily", set(), config) is None
    config.blackjack_enabled = True
    picked = await task_service._pick(db_session, "daily", set(), config)
    assert picked is not None and picked.id == definition.id


def test_the_debut_path_tries_the_new_modes():
    modes = newbie_service.known_modes()
    assert all(t["mode"] in modes for t in NEWBIE_DEFAULT_TASKS)
    assert {"game:fergie_time", "game:otvetka", "game:one_on_one"} <= {t["mode"] for t in NEWBIE_DEFAULT_TASKS}
    assert GameType.fergie_time.value == "fergie_time"
