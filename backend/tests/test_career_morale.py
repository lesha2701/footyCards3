"""Team morale of «Карьера тренера» (services/career_morale_service.py): the
mood levels and their rating shift, pre-match speeches, half-time talks,
the after-match update, character traits, the coach's specialization and the season
integration (state["morale"], «Сплочение», the API)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.career import CareerParticipant, CareerProfile, CareerSeason
from app.models.enums import Position
from app.services import career_morale_service as morale
from app.services import career_service, duel_service
from tests.test_career import _reset_rate_limits  # noqa: F401  (autouse fixture)
from tests.test_career_tactics import API, _defaults, _runner, _season, _season_row

T = morale.DEFAULT_TUNING


def test_levels_and_the_mood_shift():
    assert [morale.level_of(v) for v in (95, 90, 75, 50, 30, 10)] == [
        (2, "Эйфория"), (2, "Эйфория"), (1, "На подъёме"), (0, "Ровная"), (-1, "Не в духе"), (-2, "Подавлена")]
    assert morale.match_bonus(95, None, 0, T)[:2] == (2, 0)
    assert morale.match_bonus(10, None, 0, T)[:2] == (-2, 0)


def test_speeches_depend_on_the_mood_and_the_favourite():
    # «Вдохновить» lifts a team that isn't flying already.
    assert morale.match_bonus(50, "inspire", 0, T)[:2] == (0, 1)
    assert morale.match_bonus(80, "inspire", 0, T)[:2] == (1, 0)
    # «Снять давление» takes the bad mood away for this match.
    assert morale.match_bonus(10, "calm", 0, T)[:2] == (-2, 2)
    assert morale.match_bonus(50, "calm", 0, T)[:2] == (0, 0)
    # «Потребовать»: good for a favourite, pressure for an underdog…
    assert morale.match_bonus(50, "demand", 1, T)[:2] == (0, 1)
    assert morale.match_bonus(50, "demand", -1, T)[:2] == (0, -1)
    # …unless the coach is an «Оратор» 2+; from 5 a good speech is stronger.
    assert morale.match_bonus(50, "demand", -1, T, {"orator": 1})[:2] == (0, -1)
    assert morale.match_bonus(50, "demand", -1, T, {"orator": 2})[:2] == (0, 0)
    assert morale.match_bonus(50, "demand", 1, T, {"orator": 5})[:2] == (0, 2)
    assert morale.match_bonus(50, "inspire", 0, T, {"orator": 10})[:2] == (0, 3)
    assert morale.favourite_of(80, 76, T) == 1 and morale.favourite_of(76, 80, T) == -1 and morale.favourite_of(78, 77, T) == 0


def test_half_time_talks():
    assert morale.talk_bonus("praise", 50, 1, 0) == 1 and morale.talk_bonus("praise", 50, 0, 1) == -1
    assert morale.talk_bonus("praise", 95, 1, 0) == 0                     # euphoric: no effect
    assert morale.talk_bonus("rouse", 50, 0, 1) == 1 and morale.talk_bonus("rouse", 50, 2, 0) == -1
    assert morale.talk_bonus("rouse", 25, 0, 1) == -1                     # a low team breaks
    assert morale.talk_bonus("calm", 50, 1, 1) == 1 and morale.talk_bonus("calm", 50, 2, 1) == 0
    # «Оратор»: 1 — never backfires, 3 — a good talk gives one more, 8 — two.
    assert morale.talk_bonus("rouse", 25, 0, 1, orator=1) == 0
    assert morale.talk_bonus("calm", 50, 1, 1, orator=2) == 1
    assert morale.talk_bonus("calm", 50, 1, 1, orator=3) == 2
    assert morale.talk_bonus("calm", 50, 1, 1, orator=8) == 3


def test_after_match():
    start = T["start"]
    value, reasons = morale.after_match(60, 2, 1, 0, None, None, T)
    assert value == round(60 + T["win"] + (start - 60 - T["win"]) * T["regress"]) and reasons == ["победа +8"]
    # An upset and a rout count more; «Потребовать» raises the stakes.
    up, why = morale.after_match(60, 4, 0, -1, "demand", None, T)
    assert "обыграли фаворита +4" in why and "разгром +3" in why and "требование выполнено +4" in why
    assert up > value
    down, _ = morale.after_match(60, 0, 1, 0, None, None, T)
    soft, why = morale.after_match(60, 0, 1, 0, "calm", None, T)
    assert soft > down and "вдвое мягче" in why[0]
    # The coach's specialization grows with its level, and the flank duels.
    m5, why = morale.after_match(60, 2, 1, 0, None, None, T, {"motivator": 5})
    assert m5 > value and "Мотиватор +4" in why                          # +50% of the +8 win
    assert morale.after_match(60, 2, 1, 0, None, None, T, {"motivator": 10})[0] > m5
    p3 = morale.after_match(60, 0, 1, 0, None, None, T, {"psychologist": 3})[0]
    assert down < p3 < morale.after_match(60, 0, 1, 0, None, None, T, {"psychologist": 10})[0]
    assert morale.after_match(60, 1, 1, 0, None, (9, 2), T)[1] == ["выиграли дуэли +2"]
    assert morale.after_match(60, 1, 1, 0, None, (2, 9), T)[1] == ["проиграли дуэли -2"]
    # Bounds.
    assert morale.after_match(100, 5, 0, -1, "demand", None, T)[0] <= 100
    assert morale.after_match(0, 0, 5, 1, "demand", None, T)[0] >= 0


def test_traits():
    p = SimpleNamespace(display_name="Игрок", person_key=None, character_trait="stoic")
    assert morale.trait_of(p) == "stoic"
    p.character_trait = "none"
    assert morale.trait_of(p) is None
    derived = [morale.trait_of(SimpleNamespace(display_name=f"P{i}", person_key=None, character_trait=None))
               for i in range(2000)]
    share = sum(t is not None for t in derived) / len(derived)
    assert 0.25 < share < 0.35 and set(derived) - {None} == set(morale.TRAITS)
    assert morale.player_mood(-2, "stoic") == 0 and morale.player_mood(2, "stoic") == 2
    assert morale.player_mood(-1, "emotional") == -2 and morale.player_mood(1, None) == 1
    assert morale.trait_delta(2, 0, {"spark"}, set(), T) == (2, ["заводила в составе +2"])
    assert morale.trait_delta(0, 2, {"peacemaker", "spark"}, {"grumbler"}, T) == (0, ["миротворец в составе +2",
                                                                                     "ворчун без игры -2"])


def test_runner_rating_mood_traits_and_the_talk():
    config = _defaults()
    a = _runner("a", config=config)
    base = a._rating(a.on_pitch[0], 1, 0)
    a.morale_mood, a.morale_extra = -2, 1
    assert a._rating(a.on_pitch[0], 1, 0) == base - 1
    a.traits_by_card = {a.on_pitch[0].card.id: "stoic"}
    assert a._rating(a.on_pitch[0], 1, 0) == base + 1                    # the bad mood doesn't touch him
    a.morale_mood, a.morale_extra, a.traits_by_card = 2, 2, {}
    assert a._rating(a.on_pitch[0], 1, 0) == base + 3                    # capped
    a.morale_mood, a.morale_extra, a.talk, a.morale_value = 0, 0, "rouse", 50
    assert a._apply_talk(40, 0, 1) == []
    events = a._apply_talk(46, 0, 1)
    assert events[0]["payload"] == {"talk": "rouse", "bonus": 1} and "Встряхнуть" in events[0]["description"]
    assert a._rating(a.on_pitch[0], 50, 0) == base + 1
    assert a._apply_talk(60, 0, 1) == []
    # The match screen lists the talk with what it gave in the match, before
    # what moved the morale after it.
    info = {"value": 50, "reasons": ["речь «Вдохновить»: +1"]}
    out = career_service._match_morale(info, (50, 58, ["речь «Вдохновить»: +1", "победа +8"]), a)
    assert out == {"before": 50, "after": 58,
                   "match": ["речь «Вдохновить»: +1", "разговор «Встряхнуть»: +1 во втором тайме"],
                   "reasons": ["речь «Вдохновить»: +1", "разговор «Встряхнуть»: +1 во втором тайме", "победа +8"]}
    b = _runner("b", config=config)
    assert career_service._match_morale(info, (50, 50, info["reasons"]), b)["match"] == info["reasons"]


def test_coach_specialization_levels_and_switching():
    tuning = morale.COACH_TUNING
    now = datetime(2026, 11, 1, tzinfo=timezone.utc)
    profile = SimpleNamespace(coach_skills={})
    assert morale.add_xp(profile, 2, 0, tuning) == 0                    # no specialization: no experience
    assert morale.skills_of(profile) == {c: 0 for c in morale.COACH_SPECS}
    morale.choose(profile, "analyst", tuning, now)
    assert morale.skills_of(profile)["analyst"] == 1                    # level 1 right away, the rest 0
    assert morale.skills_of(profile)["orator"] == 0
    # A win 3, a draw 2, a loss 1 — all into the chosen one.
    assert [morale.add_xp(profile, *r, tuning) for r in ((2, 0), (1, 1), (0, 1))] == [3, 2, 1]
    assert morale.add_season_xp(profile, 1, tuning) == 15 and morale.add_season_xp(profile, 3, tuning) == 10
    assert morale.add_season_xp(profile, 6, tuning) == 5
    view = morale.coach_view(profile, tuning, now)
    analyst = next(s for s in view["specs"] if s["code"] == "analyst")
    assert view["spec"] == "analyst" and view["max_level"] == 10 and analyst["xp"] == 36
    assert analyst["level"] == 3 and analyst["level_xp"] == 35 and analyst["next_xp"] == 60
    assert len(analyst["levels"]) == 10 and analyst["levels"][-1] == "страх в дуэлях слабее на 100%"
    # Switching: not before switch_days; the experience of each stays.
    assert view["switch_at"] is not None
    with pytest.raises(ValueError, match="Сменить"):
        morale.choose(profile, "orator", tuning, now + timedelta(days=29))
    with pytest.raises(ValueError):
        morale.choose(profile, "analyst", tuning, now + timedelta(days=31))   # already chosen
    morale.choose(profile, "orator", tuning, now + timedelta(days=31))
    assert morale.skills_of(profile) == {"motivator": 0, "psychologist": 0, "orator": 1, "analyst": 0}
    morale.add_xp(profile, 2, 0, tuning)
    assert profile.coach_skills["xp"] == {"analyst": 36, "orator": 3}
    with pytest.raises(ValueError):
        morale.choose(profile, "magic", tuning, now + timedelta(days=90))
    # The whole way: 450 experience, ~3 months of active play.
    assert morale.level_for(449, tuning) == 9 and morale.level_for(450, tuning) == 10


def test_orator_perks_add_up():
    assert [morale.orator_perk(lvl, "team_building") for lvl in (3, 4, 9, 10)] == [0, 1, 4, 4]
    assert morale.orator_perk(10, "talk_plus") == 2 and morale.orator_perk(10, "speech_plus") == 2


def test_analyst_softens_the_fear_in_duels():
    players = {1: ("ямаль", "speed", "Ямаль"), 2: ("бэк", "reading", "Бэк")}
    book = duel_service.DuelBook(tuning=dict(duel_service.DEFAULT_TUNING), players=players,
                                 history={("ямаль", "бэк"): (5.0, 20.0)})
    card = lambda pid: SimpleNamespace(id=pid, player_id=pid)  # noqa: E731
    afraid = book.edge(card(1), card(2))["bias"]
    book.fear_left["ямаль"] = 0.0
    assert book.edge(card(1), card(2))["bias"] == 0 and afraid < 0


# --- the season -------------------------------------------------------------------------------

async def test_a_season_with_morale(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 890001)
    row = await db_session.get(CareerSeason, season["id"])
    assert morale.is_on(row.state) and set(row.state["morale"]["teams"]) == {str(i) for i in range(8)}
    card = season["morale"]
    assert card["value"] == T["start"] and card["label"] == "Ровная" and card["speech"] is None
    assert {s["code"] for s in card["speeches"]} == set(morale.SPEECHES)
    assert any(t["code"] == "team_building" for t in season["trainings"])
    assert all(c["trait"] in (None, *morale.TRAITS) for c in season["squad"])

    resp = await client.put(f"{API}/career/speech", headers=headers, json={"speech": "inspire", "round_index": 0})
    assert resp.status_code == 200, resp.text
    assert resp.json()["season"]["morale"]["speech"] == "inspire"
    assert (await client.put(f"{API}/career/speech", headers=headers, json={"speech": "shout"})).status_code == 409
    resp = await client.put(f"{API}/career/training", headers=headers, json={"training": "team_building"})
    assert resp.status_code == 200, resp.text
    resp = await client.post(f"{API}/career/coach/spec/psychologist", headers=headers)
    assert resp.status_code == 200, resp.text

    first = datetime.fromisoformat(season["schedule"][0])
    await career_service.resolve_due(db_session, season["id"], now=first + timedelta(minutes=30))
    row = await _season_row(db_session, season["id"])
    assert row.rounds_played == 1
    me = season["my_team_index"]
    entry = row.state["morale"]["log"][str(me)][-1]
    # «Сплочение» before the match, then the result.
    assert entry["round"] == 0 and entry["before"] == T["start"] + T["team_building"]
    assert entry["after"] == row.state["morale"]["teams"][str(me)]
    assert any("Вдохновить" in r for r in entry["reasons"]) or entry["before"] >= 70
    match_index = next(i for i, m in enumerate(row.state["results"][0]) if me in (m["home"], m["away"]))
    events = (await client.get(f"{API}/career/seasons/{season['id']}/rounds/0/matches/{match_index}",
                               headers=headers)).json()
    assert events["morale"]["before"] == entry["before"] and events["morale"]["after"] == entry["after"]
    # The flank duels reach the client too (they did not before: the schema dropped them).
    assert isinstance(events["duels"], list) and isinstance(events["duel_stories"], list)
    # The speech was for round 0 only.
    view = (await client.get(f"{API}/career", headers=headers)).json()["season"]
    assert view["morale"]["speech"] is None and view["morale"]["log"]
    # Coach experience from the result.
    profile = (await db_session.execute(select(CareerProfile).where(CareerProfile.user_id == user_id))).scalar_one()
    own, opp = ((lambda m: (m["hs"], m["as"]) if m["home"] == me else (m["as"], m["hs"]))(row.state["results"][0][match_index]))
    assert profile.coach_skills["xp"] == {"psychologist": 3 if own > opp else 2 if own == opp else 1}


async def test_a_whole_season_levels_the_specialization(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 890003)
    assert (await client.post(f"{API}/career/coach/spec/analyst", headers=headers)).status_code == 200
    await career_service.resolve_due(db_session, season["id"], now=datetime.now(timezone.utc) + timedelta(days=8))
    row = await _season_row(db_session, season["id"])
    me = season["my_team_index"]
    part = (await db_session.execute(select(CareerParticipant).where(
        CareerParticipant.user_id == user_id, CareerParticipant.season_id == season["id"]))).scalar_one()
    tuning = morale.COACH_TUNING
    expected = 0
    for round_ in row.state["results"]:
        m = next(m for m in round_ if me in (m["home"], m["away"]))
        own, opp = (m["hs"], m["as"]) if m["home"] == me else (m["as"], m["hs"])
        expected += tuning["xp_win"] if own > opp else tuning["xp_draw"] if own == opp else tuning["xp_loss"]
    expected += tuning["xp_season"][0 if part.final_place == 1 else 1 if part.final_place <= 3 else 2]
    profile = (await db_session.execute(select(CareerProfile).where(CareerProfile.user_id == user_id))).scalar_one()
    # 14 league matches and the final place: a week of play is a few levels, not all ten.
    assert profile.coach_skills["xp"] == {"analyst": expected}
    assert 2 <= morale.skills_of(profile)["analyst"] <= 5


async def test_coach_spec_endpoint(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 890002)
    resp = await client.post(f"{API}/career/coach/spec/motivator", headers=headers)
    assert resp.status_code == 200, resp.text
    coach = resp.json()["profile"]["coach"]
    assert coach["spec"] == "motivator" and coach["switch_at"] is not None
    assert next(s for s in coach["specs"] if s["code"] == "motivator")["level"] == 1
    resp = await client.post(f"{API}/career/coach/spec/orator", headers=headers)
    assert resp.status_code == 409 and "Сменить" in resp.json()["error"]["message"]
    assert (await client.post(f"{API}/career/coach/spec/magic", headers=headers)).status_code == 409


async def test_a_season_without_morale(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 890003)
    row = await db_session.get(CareerSeason, season["id"])
    row.state = {k: v for k, v in row.state.items() if k != "morale"}
    await db_session.commit()
    view = (await client.get(f"{API}/career", headers=headers)).json()["season"]
    assert view["morale"] is None and not any(t["code"] == "team_building" for t in view["trainings"])
    assert (await client.put(f"{API}/career/speech", headers=headers, json={"speech": "calm"})).status_code == 409
    await career_service.resolve_due(db_session, season["id"], now=datetime.now(timezone.utc) + timedelta(days=8))
    assert "morale" not in (await _season_row(db_session, season["id"])).state


async def test_admin_sets_a_character_trait(client, db_session, bot_token):
    from tests.factories import create_player
    from tests.test_duels import _admin

    admin = await _admin(client, bot_token)
    player = await create_player(db_session, position=Position.CM, display_name="Характер")
    resp = await client.put(f"/api/v1/admin/players/{player.id}", headers=admin, json={"character_trait": "grumbler"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["character_trait"] == "grumbler" and resp.json()["character_trait_auto"] == "grumbler"
    resp = await client.put(f"/api/v1/admin/players/{player.id}", headers=admin, json={"character_trait": "none"})
    assert resp.json()["character_trait_auto"] is None
    assert (await client.put(f"/api/v1/admin/players/{player.id}", headers=admin,
                             json={"character_trait": "lazy"})).status_code == 422
