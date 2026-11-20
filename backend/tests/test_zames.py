from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import GameSessionStatus
from app.models.game import GameSession
from app.models.monetization import Cosmetic
from app.models.user import User
from app.schemas.game import ZamesFinishIn
from app.services import cosmetic_service, game_limits_service, zames_service
from app.services.game_config_service import get_config


async def _user(db, telegram_id=9300) -> User:
    joined = datetime.now(timezone.utc) - timedelta(days=1)
    user = User(telegram_id=telegram_id, username=f"u{telegram_id}", first_name="Z", created_at=joined)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _aged(db, session_id: int, seconds: int) -> None:
    session = await db.get(GameSession, session_id)
    session.created_at = session.created_at - timedelta(seconds=seconds)
    await db.commit()


def _claim(waves=6, knockouts=30, won=True) -> ZamesFinishIn:
    return ZamesFinishIn(waves=waves, knockouts=knockouts, best_combo=12, won=won)


@pytest.mark.asyncio
async def test_a_played_out_derby_pays_base_plus_waves(db_session):
    user = await _user(db_session)
    config = await get_config(db_session)
    out = await zames_service.start(db_session, user, "derby")
    assert out.seed > 0 and out.rewarded_left == config.zames_daily_limit
    await _aged(db_session, out.session_id, 600)
    result = await zames_service.finish(db_session, user, out.session_id, _claim())
    assert result.waves_paid == 6
    assert result.reward_coins == config.zames_base_coins + 6 * config.zames_wave_coins
    assert result.best_knockouts == 30 and result.new_record


@pytest.mark.asyncio
async def test_claims_are_clamped_by_the_clock_and_the_wave_cap(db_session):
    user = await _user(db_session)
    config = await get_config(db_session)
    # 13 s of play can't hold more than two waves, nor 500 knockouts.
    out = await zames_service.start(db_session, user, "endless")
    await _aged(db_session, out.session_id, 2 * zames_service.MIN_WAVE_SECONDS + 1)
    result = await zames_service.finish(db_session, user, out.session_id, _claim(waves=40, knockouts=500))
    assert result.waves_paid == 2
    assert result.best_knockouts == 3 * zames_service.MAX_KNOCKOUTS_PER_WAVE
    # A long endless run still pays at most zames_max_waves waves.
    out = await zames_service.start(db_session, user, "endless")
    await _aged(db_session, out.session_id, 3600)
    result = await zames_service.finish(db_session, user, out.session_id, _claim(waves=40, knockouts=100))
    assert result.waves_paid == config.zames_max_waves


@pytest.mark.asyncio
async def test_finishing_is_retryable_and_pays_once(db_session):
    user = await _user(db_session)
    out = await zames_service.start(db_session, user, "derby")
    await _aged(db_session, out.session_id, 600)
    first = await zames_service.finish(db_session, user, out.session_id, _claim())
    again = await zames_service.finish(db_session, user, out.session_id, _claim(waves=0, knockouts=0))
    assert again.reward_coins == first.reward_coins
    assert again.new_balance == first.new_balance
    assert again.waves_paid == first.waves_paid


@pytest.mark.asyncio
async def test_daily_cap_then_runs_pay_nothing(db_session):
    user = await _user(db_session)
    config = await get_config(db_session)
    config.zames_daily_limit = 1
    config.hourly_game_limit = 10
    await db_session.commit()
    out = await zames_service.start(db_session, user, "derby")
    await _aged(db_session, out.session_id, 600)
    assert (await zames_service.finish(db_session, user, out.session_id, _claim())).reward_coins > 0
    out = await zames_service.start(db_session, user, "derby")
    assert out.rewarded_left == 0
    await _aged(db_session, out.session_id, 600)
    capped = await zames_service.finish(db_session, user, out.session_id, _claim(knockouts=5))
    assert capped.reward_coins == 0 and capped.daily_cap_reached
    assert not capped.new_record and capped.best_knockouts == 30


@pytest.mark.asyncio
async def test_hourly_limit_and_a_new_start_abandons_the_old_run(db_session):
    user = await _user(db_session)
    config = await get_config(db_session)
    config.hourly_game_limit = 2
    await db_session.commit()
    first = await zames_service.start(db_session, user, "derby")
    await zames_service.start(db_session, user, "derby")
    assert (await db_session.get(GameSession, first.session_id)).status == GameSessionStatus.expired
    with pytest.raises(ConflictError):
        await zames_service.finish(db_session, user, first.session_id, _claim())
    with pytest.raises(ConflictError):
        await zames_service.start(db_session, user, "derby")
    locked = await db_session.get(User, user.id)
    assert game_limits_service.get_remaining_plays(locked, config).zames == 0


@pytest.mark.asyncio
async def test_info_shows_the_config_and_what_is_left(db_session):
    user = await _user(db_session)
    config = await get_config(db_session)
    info = await zames_service.info(db_session, user)
    assert info.base_coins == config.zames_base_coins and info.rewarded_left == config.zames_daily_limit
    out = await zames_service.start(db_session, user, "derby")
    await _aged(db_session, out.session_id, 600)
    await zames_service.finish(db_session, user, out.session_id, _claim())
    info = await zames_service.info(db_session, await db_session.get(User, user.id))
    assert info.rewarded_left == config.zames_daily_limit - 1 and info.best_knockouts == 30


@pytest.mark.asyncio
async def test_someone_elses_run_is_not_found(db_session):
    user = await _user(db_session)
    other = await _user(db_session, telegram_id=9301)
    out = await zames_service.start(db_session, user, "derby")
    with pytest.raises(NotFoundError):
        await zames_service.finish(db_session, other, out.session_id, _claim())


@pytest.mark.asyncio
async def test_a_bought_hero_skin_is_worn_in_the_brawl(db_session):
    user = await _user(db_session)
    viking = Cosmetic(kind="zames_hero", name="Викинг", style_key="viking", stars_price=50)
    gold = Cosmetic(kind="zames_hero", name="Золотой", style_key="gold", stars_price=75)
    db_session.add_all([viking, gold])
    await db_session.commit()
    assert (await zames_service.info(db_session, user)).skin is None
    ok, _ = await cosmetic_service.validate_stars(db_session, user.id, viking.id, 50)
    assert ok
    await cosmetic_service.deliver_stars(db_session, user, viking.id)  # equips into the empty slot
    await db_session.commit()
    user = await db_session.get(User, user.id)
    assert (await zames_service.info(db_session, user)).skin == "viking"
    with pytest.raises(ConflictError):  # not owned
        await cosmetic_service.equip(db_session, user, "zames_hero", gold.id)
    await cosmetic_service.equip(db_session, user, "zames_hero", None)  # back to the plain hero
    assert (await zames_service.info(db_session, user)).skin is None
