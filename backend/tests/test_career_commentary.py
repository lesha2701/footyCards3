"""«Карьера тренера»: what a goal meant, the match in two phrases, league
scorers and bots answering the score at the break."""
from datetime import datetime, timedelta

from sqlalchemy import select  # noqa: F401

from app.services import career_commentary_service as commentary
from app.services import career_service
from tests.test_career import API, _reset_rate_limits  # noqa: F401  (autouse fixture)
from tests.test_career_tactics import _runner, _season, _season_row


def goal(team, minute, name="Иванов"):
    return {"minute": minute, "event_type": "goal", "team": team, "description": "⚽ Гол", "payload": {"shooter": name}}


def test_goals_learn_what_they_meant_from_the_past_only():
    events = [goal("a", 10, "Смит"), goal("a", 20, "Смит"), goal("b", 30, "Петров"), goal("b", 60, "Петров"),
              goal("b", 88, "Петров")]
    rich = commentary.enrich(events)
    assert rich[0]["description"] == "⚽ Гол"
    assert "Дубль" in rich[1]["description"]
    assert "Игра началась заново" in rich[3]["description"]
    assert "Хет-трик" in rich[4]["description"]
    assert events[4]["description"] == "⚽ Гол"  # the stored log is untouched
    # An event never depends on what follows it (the live viewer shows them one by one).
    assert commentary.enrich(events[:2]) == rich[:2]


def test_late_goals_and_tension():
    rich = commentary.enrich([goal("a", 10), goal("b", 87, "Петров"),
                              {"minute": 89, "event_type": "save", "team": "a", "description": "Сэйв"}, goal("a", 90, "Смит")])
    assert "концовке" in rich[1]["description"]
    assert rich[2]["description"] != "Сэйв"
    assert "последних минутах" in rich[3]["description"]


def test_story_tells_comeback_rout_and_goalless():
    comeback = [goal("b", 5, "Петров"), goal("a", 50, "Смит"), goal("a", 70, "Смит")]
    first, second = commentary.story(comeback, "Арсенал", "Сокол", 2, 1)
    assert "отыгрывается" in first and "«Арсенал»" in first and "Смит: дубль" in second
    rout = [goal("a", m, n) for m, n in ((10, "А"), (20, "Б"), (30, "В"))]
    assert "Разгром" in commentary.story(rout, "Арсенал", "Сокол", 3, 0)[0]
    assert "Нулевая ничья" in commentary.story([], "Арсенал", "Сокол", 0, 0)[0]


def test_scorers_add_up_and_leave_out_a_round_on_air():
    state = {"teams": [{"name": "Мы"}, {"name": "Они"}]}
    commentary.add_scorers(state, 0, [goal("a", 1, "Смит"), goal("b", 2, "Петров")], 0, 1)
    commentary.add_scorers(state, 1, [goal("b", 3, "Смит")], 1, 0)
    assert commentary.top_scorers(state)[0] == {"name": "Смит", "team_index": 0, "team": "Мы", "goals": 2}
    assert commentary.top_scorers(state, upto=1)[0]["goals"] == 1


def _bot(on, tired_bench=True, **kw):
    runner = _runner(bench_positions=("ST", "CM") if tired_bench else (), **kw)
    runner.react_subs = 1
    return runner


def test_bot_behind_goes_forward_and_brings_on_a_sub():
    runner = _bot(None)
    runner.mentality = "BALANCED"
    events = runner._react_at_half(46, 0, 1)
    assert len(events) == 1 and events[0]["event_type"] == "substitution"
    assert runner.halftime == {"mentality": "ATTACKING"}
    assert runner._react_at_half(47, 0, 2) == []  # once


def test_bot_two_up_shuts_the_game_and_a_close_score_changes_nothing():
    runner = _bot(None)
    runner.mentality = "BALANCED"
    runner._react_at_half(46, 3, 1)
    assert runner.halftime == {"mentality": "DEFENSIVE"}
    level = _bot(None)
    assert level._react_at_half(46, 1, 1) == [] and level.halftime is None
    ahead = _bot(None)
    assert ahead._react_at_half(46, 2, 1) == [] and ahead.halftime is None


async def test_season_view_lists_scorers_and_match_has_a_story(client, db_session, bot_token):
    _user, headers, season = await _season(client, db_session, bot_token, 881001)
    first = datetime.fromisoformat(season["schedule"][1])
    await career_service.resolve_due(db_session, season["id"], now=first + timedelta(minutes=40))
    row = await _season_row(db_session, season["id"])
    teams = [t for t in row.state["teams"] if t.get("user_id") is None]
    assert all("bench" in t for t in teams)
    goals = sum(m["hs"] + m["as"] for rnd in row.state["results"] for m in rnd)
    assert sum(sum(b.values()) for b in row.state["scorers"].values()) <= goals
    view = (await client.get(f"{API}/career", headers=headers)).json()["season"]
    assert view["top_scorers"] or goals == 0
    index = next(i for i, m in enumerate(row.state["results"][0]) if m.get("events"))
    match = (await client.get(f"{API}/career/seasons/{season['id']}/rounds/0/matches/{index}", headers=headers)).json()
    assert match["story"]
    replay = await client.get(f"{API}/career/seasons/{season['id']}/rounds/0/matches/{index}/replay", headers=headers)
    assert replay.status_code == 200


