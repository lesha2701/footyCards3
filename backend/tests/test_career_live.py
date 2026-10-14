"""«Карьера тренера», part 2: player roles and man-marking at duel level,
fresh-legs substitutions and plan hints, the live match centre (first half,
half-time orders, an exact replay of the first half), the friend league
carrying over, achievements and the trophy cabinet, the coach leaderboard,
smarter reminders and the weekly digest."""
import random
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.career import CareerParticipant, CareerProfile, CareerSeason
from app.models.enums import NotificationType
from app.models.notification import Notification
from app.services import career_achievements_service as achievements
from app.services import career_service
from app.services import career_tactics_service as tactics
from app.services import tournament_match_engine as engine
from app.services.club_formation_service import get_formation_slots
from app.services.game_config_service import get_config
from app.models.enums import Position
from tests.test_career import API, _player_with_cards, _reset_rate_limits  # noqa: F401  (autouse fixture)
from tests.test_career_tactics import NEUTRAL, _card, _defaults, _runner, _season, _season_row


# --- roles and marking -----------------------------------------------------------------------

def test_roles_validation_and_slots():
    assert tactics.clean_roles({"winger": "crosser", "pivot": None}) == {"winger": "crosser"}
    for bad in ({"winger": "dribbler"}, {"keeper": "sweeper"}, "wings"):
        with pytest.raises(tactics.TacticError):
            tactics.clean_roles(bad)
    by_slot = tactics.roles_by_slot({"winger": "inside", "pivot": "destroyer", "fullback": "holding"},
                                    get_formation_slots("4-3-3"))
    assert by_slot == {"FWD1": "winger:inside", "FWD3": "winger:inside", "MID1": "pivot:destroyer",
                       "DEF1": "fullback:holding", "DEF4": "fullback:holding"}
    # A line the formation doesn't have simply has no role.
    assert not any(v.startswith("pivot") for v in tactics.roles_by_slot({"pivot": "playmaker"},
                                                                        get_formation_slots("4-4-2")).values())


def test_roles_and_marking_shift_duels():
    tuning = tactics.tuning_of(_defaults())
    att_card, def_card = _card(1, Position.LW, 80), _card(2, Position.CDM, 80)
    att = tactics.TacticAxes(NEUTRAL, tuning, roles_by_card={1: "winger:crosser"})
    dfn = tactics.TacticAxes(NEUTRAL, tuning, roles_by_card={2: "pivot:destroyer"})
    value, ids = att.player_shift(dfn, att_card, def_card, "wing_attack")
    assert ids == ("role:winger:crosser", "role_def:pivot:destroyer")
    assert value == pytest.approx(0.10 - 0.04)
    value, _ = att.player_shift(dfn, att_card, def_card, "central_attack")
    assert value == pytest.approx(-0.06 - 0.12)

    # Their star (player_id 1) runs into my marker; the marker drawn by
    # someone else leaves a gap; my marker attacking is less of a threat.
    marked = tactics.TacticAxes(NEUTRAL, tuning, marking={"marker": 2, "target": 1})
    plain = tactics.TacticAxes(NEUTRAL, tuning)
    assert plain.player_shift(marked, att_card, def_card, "wing_attack") == (-tuning["marking"]["star"], ("mark_star",))
    other = _card(3, Position.ST, 80)
    assert plain.player_shift(marked, other, def_card, "central_attack") == (tuning["marking"]["gap"], ("mark_gap",))
    assert marked.player_shift(plain, def_card, other, "central_attack") == (-tuning["marking"]["marker_attack"],
                                                                             ("mark_marker_attack",))


def test_marking_lasts_while_the_marker_plays_and_is_tracked():
    config = _defaults()
    a = _runner("a", config=config, bench_positions=(Position.CDM,))
    b = _runner("b", config=config, offset=100)
    star = max((p for p in b.on_pitch if p.slot.category != "GK"), key=lambda p: p.card.id)
    marker = next(p for p in a.on_pitch if p.slot.ideal_position.value == "CDM")
    a.marking = {"marker": marker.card.id, "target": star.card.player_id}
    assert a._player_levers()["marking"] == a.marking
    a.plan = {"rules": [], "subs": [{"minute": 30, "slot": marker.slot.code, "card_id": None, "min_fatigue": 0}]}
    random.seed(3)
    tracker: dict = {}
    engine.simulate_match_controlled(tactics.CareerMatchController(a, b), config, tracker=tracker)
    assert a._player_levers()["marking"] is None  # marker went off
    ids = set((tracker.get("b") or {}).get("interactions") or {}) | set((tracker.get("a") or {}).get("interactions") or {})
    assert ids & {"mark_star", "mark_gap", "mark_marker_attack"}


def test_fresh_legs_for_substitutes():
    config = _defaults()
    runner = _runner(bench_positions=(Position.ST,), config=config,
                     plan={"rules": [], "subs": [{"minute": 60, "slot": "FWD2", "card_id": None, "min_fatigue": 0}]})
    sub = runner.bench[0]
    before = runner._rating(sub, 60, 0)
    runner.state_at(61, 0, 0)
    assert sub.on_minute == 61
    assert runner._rating(sub, 61, 0) == before + tactics.tuning_of(config)["sub_fresh"]


# --- live match centre ------------------------------------------------------------------------

def _pair(config, orders=None):
    a = _runner("a", config=config, bench_positions=(Position.ST, Position.CM))
    b = _runner("b", config=config, offset=100)
    a.halftime = orders
    return a, b


def test_halftime_orders_replay_the_first_half_exactly():
    config = _defaults()
    a, b = _pair(config)
    random.seed(77)
    plain = engine.simulate_match_controlled(tactics.CareerMatchController(a, b), config)
    snap = a.snapshot
    assert snap and len(snap["on"]) == 11 and {x["card_id"] for x in snap["bench"]} == {50, 51}

    on = {x["card_id"] for x in snap["on"]}
    orders = tactics.clean_halftime({"mentality": "ATTACKING", "tactic": {"block": "high"},
                                     "subs": [{"out": 9, "in": 50}]}, on, {50, 51}, 3)
    a, b = _pair(config, orders)
    random.seed(77)
    ordered = engine.simulate_match_controlled(tactics.CareerMatchController(a, b), config)
    first = [e for e in plain.event_log if e["minute"] <= tactics.HALF_TIME]
    assert [e for e in ordered.event_log if e["minute"] <= tactics.HALF_TIME] == first
    later = [e for e in ordered.event_log if e["minute"] > tactics.HALF_TIME]
    assert any(e["event_type"] == "substitution" and "в перерыве" in e["description"] for e in later)
    assert any(e["event_type"] == "tactic_change" and "указания в перерыве" in e["description"] for e in later)
    assert a._effective[0] == "ATTACKING" and dict(a._effective[1])["block"] == "high"


def test_halftime_validation():
    with pytest.raises(tactics.PlanError):
        tactics.clean_halftime({"subs": [{"out": 99, "in": 50}]}, {1, 2}, {50}, 3)
    with pytest.raises(tactics.PlanError):
        tactics.clean_halftime({"subs": [{"out": 1, "in": 50}, {"out": 2, "in": 51}]}, {1, 2}, {50, 51}, 1)
    with pytest.raises(tactics.PlanError):
        tactics.clean_halftime({"mentality": "YOLO"}, {1}, set(), 3)


async def test_live_round_first_half_break_and_second_half(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 880001)
    first = datetime.fromisoformat(season["schedule"][0])
    # Kick-off: only the first half is played, nothing is recorded yet.
    assert await career_service.resolve_due(db_session, season["id"], now=first + timedelta(minutes=1)) == 0
    row = await _season_row(db_session, season["id"])
    assert row.rounds_played == 0 and row.state["live"]["round"] == 0 and not row.state["results"]
    notes = (await db_session.execute(select(Notification).where(Notification.user_id == user_id))).scalars().all()
    assert any("перерыв" in n.title for n in notes)

    live = (await client.get(f"{API}/career", headers=headers)).json()["season"]["live"]
    assert live and len(live["on"]) == 11 and live["bench"] and live["subs_left"] == 3
    assert all(e["minute"] <= 45 for e in live["events"])
    # A second kick-off pass is a no-op (the first half is kept).
    await career_service.resolve_due(db_session, season["id"], now=first + timedelta(minutes=2))
    assert (await _season_row(db_session, season["id"])).state["live"]["matches"] == row.state["live"]["matches"]

    bad = await client.put(f"{API}/career/halftime", headers=headers, json={"subs": [{"out": -5, "in": live["bench"][0]["card_id"]}]})
    assert bad.status_code == 409
    out_id = next(p["card_id"] for p in live["on"] if p["slot"].startswith("FWD"))
    in_id = live["bench"][0]["card_id"]
    resp = await client.put(f"{API}/career/halftime", headers=headers, json={
        "mentality": "ATTACKING", "tactic": {"block": "high"}, "subs": [{"out": out_id, "in": in_id}]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["season"]["live"]["orders"]["subs"] == [{"out": out_id, "in": in_id}]

    # After the break: the round is played with the same first half.
    assert await career_service.resolve_due(db_session, season["id"], now=first + timedelta(minutes=11)) == 1
    row = await _season_row(db_session, season["id"])
    assert "live" not in row.state and row.rounds_played == 1
    rec = next(m for m in row.state["results"][0] if 0 in (m["home"], m["away"]))
    assert [e for e in rec["events"] if e["minute"] <= 45] == live["events"]
    assert any("в перерыве" in e["description"] for e in rec["events"] if e["event_type"] == "substitution")
    assert (await client.get(f"{API}/career", headers=headers)).json()["season"]["live"] is None


async def test_live_can_be_switched_off(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 880002)
    config = await get_config(db_session)
    config.career_live_enabled = False
    await db_session.commit()
    first = datetime.fromisoformat(season["schedule"][0])
    assert await career_service.resolve_due(db_session, season["id"], now=first + timedelta(minutes=1)) == 1


# --- plan hints, star, roles API ---------------------------------------------------------------

async def test_plan_hints_star_marking_and_roles_api(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 880003)
    codes = {h["code"] for h in season["plan_hints"]}
    assert {"no_subs", "no_behind_rule", "star"} <= codes
    star = season["scouting"]["star"]
    assert star and star["position"] != "GK"

    gk = next(s["card_id"] for s in season["squad"] if s["card"] and s["card"]["player"]["position"] == "GK")
    assert (await client.put(f"{API}/career/marking", headers=headers, json={"marker_card_id": gk})).status_code == 409
    cdm = season["lineup"]["MID1"]
    resp = await client.put(f"{API}/career/marking", headers=headers, json={"marker_card_id": cdm, "round_index": 0})
    assert resp.status_code == 200, resp.text
    view = resp.json()["season"]
    assert view["scouting"]["marking"]["marker"] == cdm and view["scouting"]["marking"]["target"] == star["player_id"]
    assert "star" not in {h["code"] for h in view["plan_hints"]}
    resp = await client.put(f"{API}/career/marking", headers=headers, json={"marker_card_id": None})
    assert resp.json()["season"]["scouting"]["marking"] is None

    assert (await client.put(f"{API}/career/roles", headers=headers, json={"roles": {"winger": "flying"}})).status_code == 409
    resp = await client.put(f"{API}/career/roles", headers=headers, json={"roles": {"winger": "inside", "pivot": "playmaker"}})
    assert resp.status_code == 200 and resp.json()["season"]["roles"] == {"winger": "inside", "pivot": "playmaker"}
    catalog = resp.json()["tactics_catalog"]["roles"]
    assert [g["group"] for g in catalog] == ["winger", "pivot", "fullback"]


# --- friend league ----------------------------------------------------------------------------

async def _friends(client, db_session, bot_token, a_tg, b_tg):
    a_id, a_headers = await _player_with_cards(client, db_session, bot_token, a_tg)
    b_id, b_headers = await _player_with_cards(client, db_session, bot_token, b_tg)
    await client.post(f"{API}/friends/requests", headers=a_headers, json={"user_id": b_id})
    req = (await client.get(f"{API}/friends", headers=b_headers)).json()["incoming"][0]["request_id"]
    await client.post(f"{API}/friends/requests/{req}/accept", headers=b_headers)
    season = (await client.post(f"{API}/career/seasons", headers=a_headers, json={"friend_id": b_id})).json()["season"]
    await client.post(f"{API}/career/seasons/{season['id']}/invite", headers=b_headers, json={"accept": True})
    await client.get(f"{API}/career", headers=b_headers)  # active
    return (a_id, a_headers), (b_id, b_headers), season


async def test_friend_league_carries_over_when_both_stay_together(client, db_session, bot_token):
    config = await get_config(db_session)
    config.career_division_promote, config.career_division_relegate = 0, 0
    await db_session.commit()
    (a_id, a_headers), (b_id, b_headers), season = await _friends(client, db_session, bot_token, 880010, 880011)
    await career_service.resolve_due(db_session, season["id"], now=datetime.now(timezone.utc) + timedelta(days=8))
    a_view = (await client.get(f"{API}/career", headers=a_headers)).json()["season"]
    b_view = (await client.get(f"{API}/career", headers=b_headers)).json()["season"]
    assert a_view["id"] == b_view["id"] != season["id"]
    assert sum(not t["is_bot"] for t in a_view["teams"]) == 2
    assert a_view["offseason"]["friend_league"] and b_view["offseason"]["prev_season_id"] == season["id"]
    # Each friend has an own off-season: friendly and camp.
    assert (await client.post(f"{API}/career/friendly", headers=b_headers)).status_code == 200
    assert (await client.post(f"{API}/career/friendly", headers=a_headers)).status_code == 200
    assert (await client.post(f"{API}/career/friendly", headers=b_headers)).status_code == 409


async def test_friends_split_when_divisions_differ(client, db_session, bot_token):
    config = await get_config(db_session)
    config.career_division_promote, config.career_division_relegate = 0, 0
    await db_session.commit()
    (a_id, a_headers), (b_id, b_headers), season = await _friends(client, db_session, bot_token, 880012, 880013)
    row = await _season_row(db_session, season["id"])
    part_b = next(p for p in row.participants if p.user_id == b_id)
    part_b.division = row.division - 1  # b moves on its own ladder: next season a division above a
    await db_session.commit()
    await career_service.resolve_due(db_session, season["id"], now=datetime.now(timezone.utc) + timedelta(days=8))
    a_view = (await client.get(f"{API}/career", headers=a_headers)).json()["season"]
    b_view = (await client.get(f"{API}/career", headers=b_headers)).json()["season"]
    assert a_view["id"] != b_view["id"]
    assert sum(not t["is_bot"] for t in a_view["teams"]) == 1 and not a_view["offseason"]["friend_league"]
    assert b_view["division"]["division"] == a_view["division"]["division"] - 1


# --- achievements, trophies, leaderboard --------------------------------------------------------

def _profile(**kw):
    return SimpleNamespace(**{"achievements": {}, "seasons_played": 0, "reputation": 0, **kw})


def test_match_achievements_and_streaks():
    p = _profile()
    assert achievements.record_match(p, 1, 0) == ["first_win"]
    for _ in range(4):
        achievements.record_match(p, 1, 0)
    assert "win_streak_5" in p.achievements["unlocked"] and "clean_sheets_3" in p.achievements["unlocked"]
    assert achievements.record_match(p, 0, 0) == []
    assert p.achievements["run"] == {"wins": 0, "unbeaten": 6, "clean": 6}
    events = [{"event_type": "goal", "team": "b"}, {"event_type": "goal", "team": "a"}, {"event_type": "goal", "team": "a"}]
    assert achievements.came_back(events, "a") and not achievements.came_back(events, "b")
    assert set(achievements.record_match(p, 5, 1, events=events, side="a", matchup_hint="disadvantage")) == {
        "big_win", "comeback", "tactician"}
    # Already unlocked: nothing new.
    assert achievements.record_match(p, 5, 1, events=events, side="a", matchup_hint="disadvantage") == []


def test_season_achievements_and_trophy_cabinet():
    p = _profile(seasons_played=10, reputation=300)
    new = achievements.record_season(p, place=1, division=1, division_label="Высшая лига", promoted=False,
                                     objective_met=True, cup_won=True, unbeaten=True, season_id=5)
    assert set(new) == {"title", "top_title", "cup", "double", "objective", "unbeaten_season", "veteran", "reputation"}
    out = achievements.achievements_out(p)
    assert [t["kind"] for t in out["trophies"]] == ["cup", "title"]  # newest first
    assert out["unlocked"] == 8 and out["total"] == len(achievements.ACHIEVEMENTS)


async def test_season_end_grants_achievement_coins_and_leaderboard(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 880020)
    other_id, other_headers, _ = await _season(client, db_session, bot_token, 880021)
    await career_service.resolve_due(db_session, season["id"], now=datetime.now(timezone.utc) + timedelta(days=8))
    view = (await client.get(f"{API}/career", headers=headers)).json()
    ach = view["profile"]["achievements"]
    assert ach["total"] == len(achievements.ACHIEVEMENTS)
    db_session.expire_all()
    old = (await db_session.execute(select(CareerParticipant).where(
        CareerParticipant.user_id == user_id, CareerParticipant.season_id == season["id"]))).scalar_one()
    profile = (await db_session.execute(select(CareerProfile).where(CareerProfile.user_id == user_id))).scalar_one()
    assert old.coins_earned > 0 and profile.achievements["run"]

    other = (await db_session.execute(select(CareerProfile).where(CareerProfile.user_id == other_id))).scalar_one()
    other.reputation = profile.reputation + 50
    await db_session.commit()
    board = (await client.get(f"{API}/career/leaderboard", headers=headers)).json()
    ranks = [r["user_id"] for r in board["rows"]]
    assert ranks.index(other_id) < ranks.index(user_id)
    assert next(r for r in board["rows"] if r["user_id"] == user_id)["is_me"]
    by_div = (await client.get(f"{API}/career/leaderboard?division={other.division}", headers=headers)).json()
    assert all(r["division"] == other.division for r in by_div["rows"])


# --- reminders and the weekly digest -------------------------------------------------------------

async def test_reminder_notes_cup_evening_and_offseason(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 880030)
    row = await _season_row(db_session, season["id"])
    part = next(p for p in row.participants if p.user_id == user_id)
    cup_round = career_service.CUP_AFTER_ROUNDS[0]
    notes = await career_service._reminder_notes(db_session, row, part, cup_round)
    assert any("кубок" in n for n in notes)
    await client.put(f"{API}/career/cup", headers=headers, json={"rotation": True})
    row = await _season_row(db_session, season["id"])
    part = next(p for p in row.participants if p.user_id == user_id)
    assert not any("кубок" in n for n in await career_service._reminder_notes(db_session, row, part, cup_round))

    # The evening before an off-season's first round: one reminder about the camp.
    await career_service.resolve_due(db_session, season["id"], now=datetime.now(timezone.utc) + timedelta(days=8))
    nxt = (await client.get(f"{API}/career", headers=headers)).json()["season"]
    first = datetime.fromisoformat(nxt["schedule"][0])
    assert await career_service.send_reminders(db_session, now=first - timedelta(hours=18)) == 1
    assert await career_service.send_reminders(db_session, now=first - timedelta(hours=17)) == 0
    note = (await db_session.execute(select(Notification).where(
        Notification.user_id == user_id, Notification.title == "Межсезонье: скоро старт сезона"))).scalars().all()
    assert len(note) == 1 and "Сборы ещё не выбраны" in note[0].body


async def test_weekly_digest_once_per_week(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 880040)
    schedule = [datetime.fromisoformat(t) for t in season["schedule"]]
    await career_service.resolve_due(db_session, season["id"], now=schedule[3] + timedelta(minutes=11))
    now = schedule[3] + timedelta(hours=1)
    assert await career_service.send_weekly_digests(db_session, now=now) == 1
    assert await career_service.send_weekly_digests(db_session, now=now + timedelta(hours=2)) == 0
    digest = (await db_session.execute(select(Notification).where(
        Notification.user_id == user_id, Notification.type == NotificationType.career_digest))).scalar_one()
    assert digest.body.startswith("Матчи: 4 ·")
    config = await get_config(db_session)
    config.career_digest_enabled = False
    await db_session.commit()
    assert await career_service.send_weekly_digests(db_session, now=now + timedelta(days=7)) == 0
