import random
from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy.orm.attributes import flag_modified

import app.core.rate_limit as rate_limit_module
from app.models.game import GameSession
from app.schemas.game import OtvetkaEpisodeRequest
from app.services import otvetka_service as service
from tests.factories import get_user_by_telegram_id
from tests.test_free_kick import _grant_card, _register
from tests.utils import telegram_headers

# Stands still until the episode runs out: no goal, whatever the seed.
STAND = {"controls": [[0, 0, 0]]}
# Straight up over the bar.
SWIPE = {"swipe": {"dx": 0, "dy": -1500, "curve": 0, "duration_ms": 40}}


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    rate_limit_module._hits.clear()
    yield
    rate_limit_module._hits.clear()


def test_a_match_keeps_every_limit():
    rnd = random.Random(7)
    seen = set()
    for _ in range(3000):
        kinds = service.plan_kinds(rnd)
        assert len(kinds) == service.EPISODES
        count = Counter(kinds)
        for kind, (least, most) in service.LIMITS.items():
            assert least <= count[kind] <= most, kind
        seen.update(count.items())
    # Every allowed count of every kind does come up.
    for kind, (least, most) in service.LIMITS.items():
        for n in range(least, most + 1):
            assert (kind, n) in seen


def test_minutes_ascend_within_the_90():
    rnd = random.Random(3)
    for _ in range(500):
        minutes = service.plan_minutes(rnd)
        assert len(minutes) == service.EPISODES
        assert minutes == sorted(set(minutes))
        assert 1 <= minutes[0] and minutes[-1] <= 90


def test_passes_must_ascend_and_be_real():
    with pytest.raises(ValidationError):
        OtvetkaEpisodeRequest(passes=[{"tick": 5, "target": 0, "mode": 0, "power": 0}] * 2)
    with pytest.raises(ValidationError):
        OtvetkaEpisodeRequest(passes=[{"tick": 5, "target": 0, "mode": 4, "power": 0}])


async def _start(client, db_session, tg_id: int, bot_token: str) -> tuple[dict, dict]:
    user = await _register(client, db_session, tg_id, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(tg_id, bot_token)
    res = await client.post("/api/v1/games/otvetka/start", json={"user_card_id": card.id}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json(), headers


async def _rig(db_session, session_id: int, answers: dict[int, bool] | None = None) -> None:
    """Pretend the current episode took its time; set the bot's answers."""
    session = await db_session.get(GameSession, session_id)
    await db_session.refresh(session)
    state = dict(session.server_state)
    episodes = [dict(e) for e in state["episodes"]]
    for i, answer in (answers or {}).items():
        episodes[i]["opponent_goal"] = answer
    episodes[state["current_index"]]["issued_at"] = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    state["episodes"] = episodes
    session.server_state = state
    flag_modified(session, "server_state")
    db_session.add(session)
    await db_session.commit()


def _input(kind: str) -> dict:
    return SWIPE if kind in service.SET_PIECES else STAND


async def _play(client, headers: dict, db_session, session_id: int, episode: dict) -> dict:
    await _rig(db_session, session_id)
    res = await client.post(
        f"/api/v1/games/otvetka/{session_id}/episode", json=_input(episode["kind"]), headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()


async def _play_all(client, headers: dict, db_session, data: dict, answer: bool) -> dict:
    """The 90 minutes, with the bot answering every episode or none."""
    sid = data["session_id"]
    await _rig(db_session, sid, {i: answer for i in range(10)})
    episode = data["episode"]
    result = None
    for _ in range(10):
        result = await _play(client, headers, db_session, sid, episode)
        assert result["opponent_goal"] is answer
        episode = result["next_episode"]
    return result


@pytest.mark.asyncio
async def test_start_says_nothing_of_the_answers(client, db_session, bot_token):
    data, _ = await _start(client, db_session, 870301, bot_token)
    assert data["total_episodes"] == 10
    assert data["opponent"] == "Бот"
    assert set(data["episode"]) == {"episode_index", "kind", "minute", "seed"}


@pytest.mark.asyncio
async def test_a_lost_match_pays_the_loss_once(client, db_session, bot_token):
    data, headers = await _start(client, db_session, 873021, bot_token)
    last = await _play_all(client, headers, db_session, data, True)
    assert last["is_finished"] and last["result"] == "loss"
    assert (last["my_score"], last["opponent_score"]) == (0, 10)
    assert last["reward_coins"] == data["loss_coins"]
    sid = data["session_id"]
    res = await client.post(f"/api/v1/games/otvetka/{sid}/claim", headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["reward_coins"] == data["loss_coins"]
    again = await client.post(f"/api/v1/games/otvetka/{sid}/claim", headers=headers)
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_a_draw_goes_to_sudden_death_penalties(client, db_session, bot_token):
    data, headers = await _start(client, db_session, 873031, bot_token)
    sid = data["session_id"]
    level = await _play_all(client, headers, db_session, data, False)
    assert not level["is_finished"]
    assert (level["my_score"], level["opponent_score"]) == (0, 0)
    shootout = level["next_episode"]
    assert (shootout["kind"], shootout["minute"], shootout["episode_index"]) == ("penalty", None, 10)

    # A round both miss goes on; the round only the bot scores ends it.
    await _rig(db_session, sid, {10: False})
    second = await _play(client, headers, db_session, sid, shootout)
    assert not second["is_finished"]
    await _rig(db_session, sid, {11: True})
    end = await _play(client, headers, db_session, sid, second["next_episode"])
    assert end["is_finished"] and end["result"] == "loss"
    assert (end["shootout_my"], end["shootout_opponent"]) == (0, 1)


@pytest.mark.asyncio
async def test_too_fast_and_the_wrong_input_are_refused(client, db_session, bot_token):
    data, headers = await _start(client, db_session, 873041, bot_token)
    sid = data["session_id"]
    kind = data["episode"]["kind"]
    url = f"/api/v1/games/otvetka/{sid}/episode"
    res = await client.post(url, json=SWIPE if kind in service.SET_PIECES else {"controls": [[0, 0, 0]]}, headers=headers)
    assert res.status_code == 409
    await _rig(db_session, sid)
    wrong = STAND if kind in service.SET_PIECES else SWIPE
    res = await client.post(url, json=wrong, headers=headers)
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_past_the_daily_cap_the_match_pays_nothing(client, db_session, bot_token):
    data, headers = await _start(client, db_session, 873051, bot_token)
    user = await get_user_by_telegram_id(db_session, 873051)
    user.otvetka_rewarded_attempts_today = 5
    user.otvetka_attempts_reset_at = datetime.now(timezone.utc)
    db_session.add(user)
    await db_session.commit()
    await _play_all(client, headers, db_session, data, True)
    res = await client.post(f"/api/v1/games/otvetka/{data['session_id']}/claim", headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["reward_coins"] == 0
