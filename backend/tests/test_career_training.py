"""«Карьера тренера»: the training plan — two sessions, intensity, the effects
in the match and what the coach is told afterwards."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services import career_service
from app.services import career_tactics_service as tactics
from app.services import career_training_service as plan
from tests.test_career import API, _reset_rate_limits  # noqa: F401  (autouse fixture)
from tests.test_career_tactics import _runner, _season, _season_row

TR = tactics.DEFAULT_TUNING["training"]


def test_one_main_session_at_normal_is_the_old_training():
    assert plan.plan_effects("recovery", None, "normal", TR)["fatigue"] == TR["recovery_fatigue"]
    fx = plan.plan_effects("set_pieces", None, "normal", TR)
    assert fx["fatigue"] == TR["load_fatigue"] and fx["set_piece_boost"] == TR["set_piece_boost"]
    assert plan.plan_effects("tactical", None, None, TR)["familiarity_tenths"] == TR["tactical_familiarity_tenths"]
    assert plan.plan_effects("team_building", None, "normal", TR, team_building=6) == {
        **plan.plan_effects(None, None, None, TR), "morale": 6}


def test_extra_session_is_weaker_and_both_load():
    fx = plan.plan_effects("attack", "set_pieces", "normal", TR)
    assert fx["units"] == {"FWD": 1} and fx["fatigue"] == 2 * TR["load_fatigue"]
    assert 1 < fx["set_piece_boost"] < TR["set_piece_boost"]


def test_intensity_trades_effect_for_load_and_injuries():
    light, hard = (plan.plan_effects("fitness", None, i, TR) for i in ("light", "hard"))
    assert hard["fitness_mult"] < TR["fitness_fatigue_mult"] < light["fitness_mult"]
    assert hard["fatigue"] > TR["load_fatigue"] > light["fatigue"]
    assert hard["injury_mult"] == 1.3 and light["injury_mult"] == 1.0


def test_medical_centre_still_helps_recovery():
    assert plan.plan_effects("recovery", None, "normal", TR, {"recovery": 3})["fatigue"] == TR["recovery_fatigue"] - 3


def test_preview_speaks_in_numbers():
    lines = plan.preview(plan.plan_effects("set_pieces", "defence", "hard", TR))
    assert any("Угловые" in line for line in lines) and any("Защитники" in line for line in lines)
    assert any("Риск травм +30%" == line for line in lines)


def test_results_tell_what_the_sessions_gave():
    goal = {"event_type": "goal", "team": "a", "minute": 80, "payload": {"set_piece": "corner"}}
    fx = plan.plan_effects("set_pieces", "fitness", "normal", TR)
    lines = plan.match_results("set_pieces", "fitness", fx, [goal], "a", 1, 0)
    assert lines == ["Стандарты: 1 гол с угловых и штрафных", "Физподготовка: концовка 1:0 после 70-й минуты"]
    assert plan.match_results("defence", None, fx, [], "a", 0, 0) == ["Оборона: сухой матч"]


def test_runner_applies_fitness_and_line_bonus():
    base, trained = _runner(), _runner()
    trained.fitness_mult, trained.unit_bonus = 0.5, {"FWD": 2}
    striker = next(i for i, p in enumerate(base.on_pitch) if p.slot.category == "FWD")
    assert trained._rating(trained.on_pitch[striker], 10, 0) == base._rating(base.on_pitch[striker], 10, 0) + 2
    assert trained._per_tactic()[0] == base._per_tactic()[0] * 0.5


def test_harder_training_hurts_more_often():
    config = SimpleNamespace(career_fatigue_per_match=5, career_injury_chance_pct=30, career_red_chance_pct=0,
                             career_yellow_chance_pct=0, career_form_max=2, career_fatigue_recovery=5)
    roll = SimpleNamespace(random=lambda: 0.4, randint=lambda a, b: a)

    def injured(mult):
        part = SimpleNamespace(condition={}, squad_card_ids=[1])
        return career_service._after_match(part, {1}, 1, 0, 0, config, roll, {1: "Иванов"}, injury_mult=mult)["injured"]

    assert injured(1.0) == [] and injured(1.5) == ["Иванов"]


async def test_plan_is_saved_validated_and_reported(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 883001)
    url = f"{API}/career/training"
    resp = await client.put(url, headers=headers, json={"training": "set_pieces", "extra": "fitness", "intensity": "hard", "round_index": 0})
    assert resp.status_code == 200, resp.text
    out = resp.json()["season"]
    assert out["training"] == "set_pieces" and out["training_plan"]["extra"] == "fitness"
    assert out["training_plan"]["intensity"] == "hard" and out["training_plan"]["lines"]
    same = await client.put(url, headers=headers, json={"training": "fitness", "round_index": 0})
    assert same.status_code == 409  # the kept extra is the same session
    bad = await client.put(url, headers=headers, json={"training": "attack", "intensity": "ultra", "round_index": 0})
    assert bad.status_code == 409
    # An old client sends only the main session: the rest stays.
    kept = await client.put(url, headers=headers, json={"training": "attack", "round_index": 0})
    assert kept.json()["season"]["training_plan"]["extra"] == "fitness"
    assert kept.json()["season"]["training_plan"]["intensity"] == "hard"

    first = datetime.fromisoformat(season["schedule"][0])
    await career_service.resolve_due(db_session, season["id"], now=first + timedelta(minutes=40))
    row = await _season_row(db_session, season["id"])
    team = next(p for p in row.participants if p.user_id == user_id).team_index
    lines = row.state["reports"]["0"][str(team)]["training"]
    assert lines[0].startswith("Атака") and lines[1].startswith("Физподготовка")
    assert any(n["text"] == lines[0] for n in row.state["news"][str(team)])


def test_programme_counts_only_matches_on_the_pitch():
    program = plan.program_start(None, 7, "Иванов", TR)
    program, line = plan.program_after_match(program, {1, 2}, TR)
    assert line is None and program["active"]["played"] == 0
    for n in range(1, TR["program_rounds"]):
        program, line = plan.program_after_match(program, {7}, TR)
        assert line == f"Программа: Иванов {n} из {TR['program_rounds']}"
    program, line = plan.program_after_match(program, {7}, TR)
    assert "завершена" in line and program["active"] is None
    assert plan.program_bonus(program, 7) == TR["program_bonus"] and plan.program_bonus(program, 8) == 0


def test_programme_rules():
    busy = plan.program_start(None, 7, "Иванов", TR)
    with pytest.raises(ValueError):
        plan.program_start(busy, 8, "Петров", TR)
    assert plan.program_card(plan.program_cancel(busy)) is None
    full = {"active": None, "done": {str(i): {"name": "x", "bonus": 1} for i in range(TR["program_limit"])}}
    with pytest.raises(ValueError):
        plan.program_start(full, 99, "Петров", TR)
    with pytest.raises(ValueError):
        plan.program_start({"done": {"7": {"name": "x", "bonus": 1}}}, 7, "Иванов", TR)


async def test_programme_through_the_api_lifts_the_rating_in_a_match(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 883002)
    url = f"{API}/career/program"
    assert (await client.put(url, headers=headers, json={"card_id": -1, "round_index": 0})).status_code == 409
    row = await _season_row(db_session, season["id"])
    part = next(p for p in row.participants if p.user_id == user_id)
    cards = await career_service._career_cards(db_session, user_id)
    by_id = {c.id: c for c in cards}
    xi = career_service.resolve_lineup(part, by_id, 0, cards, fill_any_position=True)
    star = xi[5][0].id
    resp = await client.put(url, headers=headers, json={"card_id": star, "round_index": 0})
    assert resp.status_code == 200, resp.text
    assert resp.json()["season"]["training_program"]["active"]["card_id"] == star

    first = datetime.fromisoformat(season["schedule"][0])
    await career_service.resolve_due(db_session, season["id"], now=first + timedelta(minutes=40))
    row = await _season_row(db_session, season["id"])
    part = next(p for p in row.participants if p.user_id == user_id)
    report = row.state["reports"]["0"][str(part.team_index)]
    assert any(line.startswith("Программа:") for line in report["training"])
    assert part.training_program["active"]["played"] == 1

    cancelled = await client.put(url, headers=headers, json={"card_id": None, "round_index": 1})
    assert cancelled.json()["season"]["training_program"]["active"] is None
