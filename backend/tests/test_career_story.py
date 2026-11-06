"""«Карьера тренера»: the club around the matches — stands, moments, rivals,
the hot seat, legends and clubs that stay themselves between seasons."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services import career_service
from app.services import career_story_service as story
from app.services.game_config_service import get_config
from tests.test_career import API, _reset_rate_limits  # noqa: F401  (autouse fixture)
from tests.test_career_tactics import _season, _season_row

T = story.DEFAULT_TUNING


def profile(**league):
    return SimpleNamespace(league=league)


@pytest.fixture(autouse=True)
def _no_flag(monkeypatch):
    monkeypatch.setattr(story, "flag_modified", lambda *a: None)


def test_income_is_neutral_at_the_start_and_follows_the_stands():
    assert story.income_pct(T["fans_start"], T) == 100
    assert story.income_pct(0, T) == T["income_min_pct"] and story.income_pct(100, T) == T["income_max_pct"]
    assert story.attendance(100, {"matchday": 100}, T) == story.capacity({"matchday": 100}, T)
    assert story.attendance(0, None, T) < story.attendance(60, None, T)


def test_fans_carry_over_through_the_profile():
    state, coach = {}, profile()
    story._set_fans(state, 0, coach, 70)
    assert story.fans_mood({}, 0, coach, T) == 70
    assert story.fans_mood({}, 0, None, T) == T["fans_start"]


def test_moment_answers_once_and_only_for_the_last_round():
    state = {"moments": {"0": {"round": 2, "code": "press_big_loss", "answer": None,
                               "data": {"score": "0:3", "opp": "Сокол", "streak": 1}}}}
    out = story.moment_out(state, 0, 3)
    assert "0:3" in out["text"] and "Сокол" in out["text"] and len(out["answers"]) == 3
    assert story.moment_out(state, 0, 4) is None  # the next round has been played
    with pytest.raises(ValueError):
        story.answer_moment(state, 0, 3, "nonsense", profile(), T)
    assert story.answer_moment(state, 0, 3, "own", profile(), T) == 3
    assert story.moment_out(state, 0, 3) is None
    with pytest.raises(ValueError):
        story.answer_moment(state, 0, 3, "own", profile(), T)


def test_promise_is_checked_next_round():
    state = {"moments": {"0": {"round": 0, "code": "player_bench", "answer": None,
                               "data": {"name": "Иванов", "rounds": 3, "card_id": 7, "score": "1:1", "opp": "Сокол", "streak": 1}}},
             "teams": [{"name": "Мы"}, {"name": "Сокол"}], "results": [[]]}
    story.answer_moment(state, 0, 1, "promise", profile(), T)
    assert state["promises"]["0"] == {"card_id": 7, "name": "Иванов", "round": 1}
    match = {"home": 0, "away": 1, "hs": 1, "as": 0, "events": None}

    def play(played):
        return story.after_round(
            state, team=0, round_index=1, match=match, own=1, opp=0, is_home=False, opponent={"name": "Сокол"},
            results=[match], report={}, played_ids=played, fit_ids={7}, squad_ids=[7], names={7: "Иванов"}, traits={},
            profile=profile(), fx=None, tuning=T, standings=[], before_leader=None, top_before=None, moments_on=False,
        )

    assert play({7}) == T["promise_kept_morale"]
    state["promises"]["0"] = {"card_id": 7, "name": "Иванов", "round": 1}
    assert play(set()) == T["promise_broken_morale"]


def test_bench_patience_depends_on_the_character():
    state = {}
    args = ([1, 2], set(), {1, 2}, {1: "Спокойный", 2: "Ворчун"}, {2: "grumbler"}, T)
    assert story._bench_update(state, 0, *args) is None
    assert story._bench_update(state, 0, *args)[1] == "Ворчун"


def test_rivalry_nemesis_beats_derby():
    coach = profile(nemesis={"club_id": 5, "score": "0:4"}, history={"6": {"w": 2, "d": 1, "l": 1}})
    assert story.rivalry(coach, 5, "Сокол")["kind"] == "nemesis"
    assert story.rivalry(coach, 6, "Титан")["kind"] == "derby"
    assert story.rivalry(coach, 7, "Луч") is None


def test_nemesis_is_the_heaviest_defeat():
    state = {"teams": [{"index": 0}, {"index": 1, "club_id": 11}, {"index": 2, "club_id": 12}],
             "results": [[{"home": 0, "away": 1, "hs": 0, "as": 1}], [{"home": 2, "away": 0, "hs": 4, "as": 0}]]}
    coach = profile()
    story.set_nemesis(coach, state, 0)
    assert coach.league["nemesis"] == {"club_id": 12, "score": "0:4"}


def test_hot_seat_after_relegation_or_two_failures_and_cleared_by_success():
    coach = profile()
    assert story.board_verdict(coach, False, False, T)[0] == 0  # one failure: a warning, not the seat
    rep, text = story.board_verdict(coach, False, False, T)
    assert rep == T["hot_seat_rep"] and "Горячее кресло" in text and story.hot_seat_out(coach)["level"] == 1
    rep, _ = story.board_verdict(coach, False, False, T)
    assert rep == T["hot_seat_rep"] * 2 and story.hot_seat_out(coach)["level"] == 2
    rep, text = story.board_verdict(coach, True, False, T)
    assert rep == 0 and "доверяет" in text and story.hot_seat_out(coach) is None
    relegated = profile()
    assert story.board_verdict(relegated, False, True, T)[0] == T["hot_seat_rep"]


def test_legends_count_across_seasons():
    coach = profile()
    goal = {"event_type": "goal", "team": "a", "payload": {"shooter_id": 1, "assist_id": 2}}
    story.record_legends(coach, 10, {1: "Смит", 2: "Петров"}, [goal], "a", 3, 0, "Сокол")
    story.record_legends(coach, 11, {1: "Смит"}, [], "a", 1, 1, "Луч")
    out = story.legends_out(coach)
    assert out["players"][0] == {"name": "Смит", "apps": 2, "goals": 1, "assists": 0, "seasons": 2}
    assert out["players"][1]["assists"] == 1 and out["biggest_win"]["score"] == "3:0"


def test_rosters_are_kept_for_next_league_clubs_only():
    coach = profile(next_clubs=[1])
    teams = [{"club_id": 1, "spread": 3, "players": [{"slot": "ST", "player_id": 9, "edge": 2.5}]},
             {"club_id": 2, "spread": 1, "players": [{"slot": "ST", "player_id": 8}]}]
    story.keep_rosters(coach, teams)
    assert coach.league["rosters"] == {"1": {"players": {"ST": [9, 2.5]}, "spread": 3}}


async def test_round_fills_the_club_and_a_moment_can_be_answered(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 882001)
    first = datetime.fromisoformat(season["schedule"][0])
    await career_service.resolve_due(db_session, season["id"], now=first + timedelta(minutes=40))
    view = (await client.get(f"{API}/career", headers=headers)).json()["season"]
    assert view["news"] and view["fans"]["mood"] != T["fans_start"] or view["news"]
    assert view["legends"]["players"]

    row = await _season_row(db_session, season["id"])
    team = next(p for p in row.participants if p.user_id == user_id).team_index
    state = dict(row.state)
    state["moments"] = {str(team): {"round": 0, "code": "press_big_win", "answer": None,
                                    "data": {"score": "4:0", "opp": "Сокол", "streak": 1}}}
    row.state = state
    await db_session.commit()
    before = (await client.get(f"{API}/career", headers=headers)).json()["season"]
    assert before["moment"]["kind"] == "press"
    resp = await client.put(f"{API}/career/moment", headers=headers, json={"answer": "calm", "round_index": 1})
    assert resp.status_code == 200, resp.text
    assert resp.json()["season"]["moment"] is None
    assert any("Работаем дальше" in n["text"] for n in resp.json()["season"]["news"])
    again = await client.put(f"{API}/career/moment", headers=headers, json={"answer": "calm", "round_index": 1})
    assert again.status_code == 409


async def test_next_season_keeps_a_clubs_players_and_hot_seat_sets_the_task(client, db_session, bot_token):
    user_id, _headers, season = await _season(client, db_session, bot_token, 882002)
    row = await _season_row(db_session, season["id"])
    config = await get_config(db_session)
    bot = next(t for t in row.state["teams"] if t.get("user_id") is None)
    bots = await career_service._build_bots(
        db_session, row, [5], 75, config, clubs=[SimpleNamespace(
            id=bot["club_id"], name=bot["name"], formation=bot["formation"], pool_club=None, rating_offset=0, preset="WING_PLAY")],
        memory={str(bot["club_id"]): {"players": {p["slot"]: [p["player_id"], p["edge"]] for p in bot["players"]}, "spread": 2}},
    )
    assert [p["player_id"] for p in bots[0]["players"]] == [p["player_id"] for p in bot["players"]]
    assert bots[0]["spread"] == 2

    coach = await career_service.get_profile(db_session, user_id, config)
    coach.league = {**(coach.league or {}), "hot_seat": {"level": 1}}
    await db_session.flush()
    with pytest.raises(career_service.ConflictError):
        await career_service.set_ambition(db_session, SimpleNamespace(id=user_id), "promote")
