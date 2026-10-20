"""«Экипировка» in Card Arena: the worn things' shot accuracy and 1-on-1
dribble bonuses lower the failure chance of the card that acts, frozen at
kickoff; without them every roll draws exactly as before."""

import random
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.card import UserCard
from app.models.game_config import GameConfig
from app.models.match import Match
from app.services import match_service
from app.services.match_situations import ATTACK_SITUATIONS_BY_ID

ONE_ON_ONE = NS(tags=("one_on_one",))
FLANK = NS(tags=("flank",))
PLAIN = NS(tags=())


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


def _state(boosts: dict | None) -> dict:
    return {"equipment": {"7": boosts} if boosts else None}


def test_shot_and_dribble_bonuses_lower_the_failure_chance():
    actor = {"user_card_id": 7, "name": "Игрок"}
    notes: list = []
    adjust = match_service._equipment_adjusted
    # Shot accuracy: always on a shot.
    assert adjust(_state({"shot_pp": 5}), actor, 0.40, PLAIN, shot=True, notes=notes) == pytest.approx(0.35)
    assert notes == [{"player": "Игрок", "effect": "shot_pp", "bonus_pp": 5}]
    # «Обыгрыш»: only where the carrier beats a man (one-on-one, flank run).
    assert adjust(_state({"shot_pp": 5, "dribble_pp": 4}), actor, 0.40, ONE_ON_ONE, shot=True, notes=[]) == pytest.approx(0.31)
    assert adjust(_state({"dribble_pp": 4}), actor, 0.40, PLAIN, shot=True, notes=[]) == 0.40
    # A pass from the flank: dribble yes, shot accuracy no.
    assert adjust(_state({"shot_pp": 5, "dribble_pp": 4}), actor, 0.30, FLANK, shot=False, notes=[]) == pytest.approx(0.26)
    # Floor 2%, and a chance already at/below it is left alone.
    assert adjust(_state({"shot_pp": 50}), actor, 0.10, PLAIN, shot=True, notes=[]) == 0.02
    assert adjust(_state({"shot_pp": 5}), actor, 0.01, PLAIN, shot=True, notes=[]) == 0.01
    # Another card's things, or none at all: untouched.
    other = {"user_card_id": 8, "name": "Другой"}
    assert adjust(_state({"shot_pp": 5}), other, 0.40, PLAIN, shot=True, notes=[]) == 0.40
    assert adjust({}, actor, 0.40, PLAIN, shot=True, notes=[]) == 0.40


def _attack_moment(situation_id: str) -> dict:
    situation = ATTACK_SITUATIONS_BY_ID[situation_id]
    return {
        "minute": 30, "kind": "attack", "team": "user", "situation_id": situation_id, "shot_type": situation.shot_type,
        "actors": {
            "shooter": {"user_card_id": 7, "player_id": 1, "name": "Бомбардир", "rating": 70, "position": "ST"},
            "pass_target": {"user_card_id": 8, "player_id": 2, "name": "Партнёр", "rating": 70, "position": "LW"},
        },
    }


def _base_state(equipment=None) -> dict:
    return {
        "ratings": {"user_fwd": 70, "user_def": 70, "user_gk": 70, "opponent_fwd": 70, "opponent_def": 70, "opponent_gk": 70},
        "skills": None, "equipment": equipment,
    }


@pytest.mark.parametrize("situation_id", ["att_box_one_on_one", "att_box_narrow_angle", "att_long_range_edge_box"])
@pytest.mark.parametrize("action", ["shoot", "pass"])
def test_without_things_every_roll_is_unchanged(situation_id, action):
    config = GameConfig(id=1)
    for column in GameConfig.__table__.columns:
        if getattr(config, column.key) is None and column.default is not None and not callable(column.default.arg):
            setattr(config, column.key, column.default.arg)
    moment = _attack_moment(situation_id)
    for seed in range(40):
        random.seed(seed)
        plain = match_service._resolve_attack(moment, action, _base_state(), config, "Соперник")
        random.seed(seed)
        empty = match_service._resolve_attack(moment, action, _base_state({}), config, "Соперник")
        assert plain == empty
        assert "equipment" not in plain[0]["payload"]


def test_things_raise_the_goal_rate_and_are_noted():
    config = GameConfig(id=1)
    for column in GameConfig.__table__.columns:
        if getattr(config, column.key) is None and column.default is not None and not callable(column.default.arg):
            setattr(config, column.key, column.default.arg)
    moment = _attack_moment("att_box_one_on_one")
    boosted_state = _base_state({"7": {"shot_pp": 8, "dribble_pp": 8}})

    def goals(state) -> int:
        random.seed(11)
        return sum(match_service._resolve_attack(moment, "shoot", state, config, "С")[1] == "user" for _ in range(3000))

    assert goals(boosted_state) > goals(_base_state())
    event, _ = match_service._resolve_attack(moment, "shoot", boosted_state, config, "С")
    assert {n["effect"] for n in event["payload"]["equipment"]} == {"shot_pp", "dribble_pp"}


async def test_match_freezes_the_lineups_things_at_kickoff(client, db_session, bot_token, monkeypatch):
    from tests.test_lineups_matches import _build_full_squad
    from tests.factories import get_user_by_telegram_id
    from tests.utils import telegram_headers

    headers = telegram_headers(930001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 930001)
    slots = await _build_full_squad(db_session, user.id)
    assert (await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})).status_code == 200
    striker_id = next(s["user_card_id"] for s in slots if s["slot_code"] == "FWD2")
    card = (await db_session.execute(select(UserCard).where(UserCard.id == striker_id))).scalar_one()
    card.equipment_boosts = {"shot_pp": 5}
    await db_session.commit()

    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 200, resp.text
    match = await db_session.get(Match, resp.json()["id"])
    await db_session.refresh(match)
    assert match.server_state["equipment"] == {str(striker_id): {"shot_pp": 5}}
