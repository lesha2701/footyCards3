"""The «Воспитанник Академии» in Пенальти (classic / 3D), Штрафной (classic /
3D) and «Атака 1 на 1» (prospect_games): he starts instead of a card, his
rating is the age-relative one, the claim gives him XP (prospect_life.award_game);
card play is unchanged."""

import pytest
from sqlalchemy import select, update

import app.core.rate_limit as rate_limit_module
from app.core.timeutil import local_today
from app.models.academy_prospect import AcademyProspect
from app.models.game import GameSession
from app.models.user import User
from app.services import prospect_service as ps
from app.services.game_config_service import get_config
from tests.test_free_kick import _grant_card, _register
from tests.test_free_kick_3d import SWIPE as FK_SWIPE
from tests.test_free_kick_3d import _age_current_kick as _age_fk_kick
from tests.test_one_on_one import ATTACK, _age_current_attack
from tests.test_prospect import NEW
from tests.utils import telegram_headers

MODES = {
    # start path → (claim prefix, award mode)
    "penalty": ("penalty", "penalty"),
    "penalty-3d": ("penalty", "penalty"),
    "free-kick": ("free-kick", "free_kick"),
    "free-kick-3d": ("free-kick", "free_kick"),
    "one-on-one": ("one-on-one", "one_on_one"),
}


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    rate_limit_module._hits.clear()
    yield
    rate_limit_module._hits.clear()


async def _with_prospect(client, db_session, tg_id, bot_token):
    user = await _register(client, db_session, tg_id, bot_token)
    headers = telegram_headers(tg_id, bot_token)
    res = await client.post("/api/v1/prospect", json=NEW, headers=headers)
    assert res.status_code == 200, res.text
    return user, headers


async def _finish(client, headers, db_session, path: str, data: dict) -> None:
    """Plays the session to its end (a shootout is forfeited: it is still a
    finished, claimable session)."""
    sid = data["session_id"]
    if path in ("penalty", "penalty-3d"):
        res = await client.post(f"/api/v1/games/penalty/{sid}/forfeit", headers=headers)
        assert res.status_code == 200, res.text
    elif path == "free-kick":
        for _ in range(3):
            res = await client.post(f"/api/v1/games/free-kick/{sid}/kick", headers=headers, json={"elapsed_ms": 0})
            assert res.status_code == 200, res.text
        assert res.json()["is_finished"]
    elif path == "free-kick-3d":
        for _ in range(data["total_kicks"]):
            await _age_fk_kick(db_session, sid)
            res = await client.post(f"/api/v1/games/free-kick-3d/{sid}/shot", headers=headers, json=FK_SWIPE)
            assert res.status_code == 200, res.text
        assert res.json()["is_finished"]
    else:
        for _ in range(data["total_attacks"]):
            await _age_current_attack(db_session, sid)
            res = await client.post(f"/api/v1/games/one-on-one/{sid}/attack", headers=headers, json=ATTACK)
            assert res.status_code == 200, res.text
        assert res.json()["is_finished"]


async def _prospect(db_session, user_id: int) -> AcademyProspect:
    db_session.expire_all()
    return (await db_session.execute(select(AcademyProspect).where(AcademyProspect.user_id == user_id))).scalar_one()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", list(MODES))
async def test_prospect_plays_the_mode_and_gets_xp_once(client, db_session, bot_token, path):
    tg_id = 881000 + list(MODES).index(path)
    user, headers = await _with_prospect(client, db_session, tg_id, bot_token)
    uid = user.id
    claim_prefix, mode = MODES[path]

    res = await client.post(f"/api/v1/games/{path}/start", json={"prospect": True}, headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    if path != "free-kick":  # the classic free kick's start shows no name / rating
        assert data["prospect_name"] == NEW["name"]
    session = await db_session.get(GameSession, data["session_id"])
    await db_session.refresh(session)
    assert session.server_state["prospect"] is True
    c = ps.cfg(await get_config(db_session))
    assert session.server_state["player_rating"] == ps.match_rating(await _prospect(db_session, uid), c, local_today())

    await _finish(client, headers, db_session, path, data)
    claim = await client.post(f"/api/v1/games/{claim_prefix}/{data['session_id']}/claim", headers=headers)
    assert claim.status_code == 200, claim.text
    xp = claim.json()["prospect_xp"]
    assert xp is not None and xp >= c["game_match_xp"]

    p = await _prospect(db_session, uid)
    assert p.xp == xp
    assert (p.stats or {})["games"][mode] == 1
    # Claimed once: no second XP.
    again = await client.post(f"/api/v1/games/{claim_prefix}/{data['session_id']}/claim", headers=headers)
    assert again.status_code == 409
    assert (await _prospect(db_session, uid)).xp == xp


@pytest.mark.asyncio
@pytest.mark.parametrize("path", list(MODES))
async def test_start_without_a_card_or_prospect_is_refused(client, db_session, bot_token, path):
    tg_id = 881100 + list(MODES).index(path)
    await _register(client, db_session, tg_id, bot_token)
    headers = telegram_headers(tg_id, bot_token)
    res = await client.post(f"/api/v1/games/{path}/start", json={}, headers=headers)
    assert res.status_code == 409, res.text
    assert res.json()["error"]["message"] == "Выбери карту"
    # No prospect yet.
    assert (await client.post(f"/api/v1/games/{path}/start", json={"prospect": True}, headers=headers)).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("path", list(MODES))
async def test_card_play_is_unchanged(client, db_session, bot_token, path):
    tg_id = 881200 + list(MODES).index(path)
    user, headers = await _with_prospect(client, db_session, tg_id, bot_token)
    uid = user.id
    card = await _grant_card(db_session, user.id, rating=84)
    claim_prefix, _ = MODES[path]

    res = await client.post(f"/api/v1/games/{path}/start", json={"user_card_id": card.id}, headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data.get("prospect_name") is None
    session = await db_session.get(GameSession, data["session_id"])
    await db_session.refresh(session)
    assert session.server_state["player_rating"] == 84
    assert not session.server_state["prospect"]

    await _finish(client, headers, db_session, path, data)
    claim = await client.post(f"/api/v1/games/{claim_prefix}/{data['session_id']}/claim", headers=headers)
    assert claim.status_code == 200, claim.text
    assert claim.json()["prospect_xp"] is None
    assert (await _prospect(db_session, uid)).xp == 0


@pytest.mark.asyncio
async def test_rewards_blocked_user_gets_no_prospect_xp(client, db_session, bot_token):
    user, headers = await _with_prospect(client, db_session, 881300, bot_token)
    uid = user.id
    await db_session.execute(update(User).where(User.id == uid).values(game_rewards_blocked=True))
    await db_session.commit()

    res = await client.post("/api/v1/games/one-on-one/start", json={"prospect": True}, headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    await _finish(client, headers, db_session, "one-on-one", data)
    claim = await client.post(f"/api/v1/games/one-on-one/{data['session_id']}/claim", headers=headers)
    assert claim.status_code == 200, claim.text
    assert claim.json()["prospect_xp"] == 0
    assert (await _prospect(db_session, uid)).xp == 0
