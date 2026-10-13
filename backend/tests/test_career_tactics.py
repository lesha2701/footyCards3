"""«Карьера тренера» tactics (career_tactics_service) and divisions:
counters + scouting consistency with the engine, per-round tactics and the
kick-off deadline, match plan (instructions/substitutions), familiarity,
adaptive bots without reading the future, the post-match analysis,
old-season compatibility, promotion/relegation."""
import copy
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.career import CareerParticipant, CareerSeason
from app.models.enums import Position, Rarity
from app.models.game_config import GameConfig
from app.services import career_service
from app.services import career_tactics_service as tactics
from app.services import club_tactical_matchup_service as matchup
from app.services import tournament_match_engine as engine
from app.services.club_formation_service import get_formation_slots
from app.services.game_config_service import get_config
from tests.test_career import API, _player_with_cards, _reset_rate_limits  # noqa: F401  (autouse fixture)


def _defaults(**overrides) -> SimpleNamespace:
    values = {}
    for column in GameConfig.__table__.columns:
        if column.default is None:
            continue
        value = column.default.arg
        if callable(value):
            try:
                value = value(None)
            except TypeError:
                value = value()
        values[column.name] = value
    values.update(overrides)
    return SimpleNamespace(**values)


@dataclass
class _Card:
    id: int
    player_id: int
    player: SimpleNamespace
    skill: None = None


def _card(n, position, rating):
    return _Card(n, n, SimpleNamespace(display_name=f"P{n}", position=position, rating=rating, rarity=Rarity.common,
                                       club=f"C{n}", country=f"N{n}", attack_rating=None, defense_rating=None))


def _runner(label="a", playstyle="CENTRAL_PLAY", plan=None, fatigue=0, bench_positions=(), config=None,
            familiarity=0, offset=0, rating=75):
    config = config or _defaults()
    on_pitch = [tactics.LivePlayer(_card(offset + i, s.ideal_position, rating), rating, fatigue, slot=s)
                for i, s in enumerate(get_formation_slots("4-3-3"))]
    bench = [tactics.LivePlayer(_card(offset + 50 + i, pos, rating - 2), rating - 2, 0)
             for i, pos in enumerate(bench_positions)]
    return tactics.CareerSideRunner(label, f"Team {label}", "4-3-3", "BALANCED", playstyle, on_pitch, bench, config,
                                    familiarity=familiarity, plan=plan)


# --- counters, scouting hint and the versioned table ---------------------------------

def test_counter_table_is_a_balanced_cycle():
    for style in matchup.PLAYSTYLES:
        beaten = tactics.COUNTERS[style]
        assert len(set(beaten)) == 2 and style not in beaten
        assert len(tactics.counters_of(style)) == 2
        assert not set(beaten) & set(tactics.counters_of(style))  # never both ways


def test_hint_comes_from_the_same_table_the_engine_applies():
    config = _defaults()
    for mine in matchup.PLAYSTYLES:
        for theirs in matchup.PLAYSTYLES:
            a = matchup.ClubTacticalSide([], None, "BALANCED", mine, style_edge=tactics.style_edge_for(mine, config))
            b = matchup.ClubTacticalSide([], None, "BALANCED", theirs, style_edge=tactics.style_edge_for(theirs, config))
            # Positive shift favors the defender: my attack vs their defence.
            shift = matchup.style_edge_shift(a, b)
            hint = tactics.matchup_hint(mine, theirs)
            assert (hint == "advantage") == (shift < 0)
            assert (hint == "disadvantage") == (shift > 0)
            assert (hint == "neutral") == (shift == 0)
    assert tactics.style_edge_for("WING_PLAY", _defaults(career_style_counter_permille=0)) is None


def test_versioned_matrix_is_current_and_agrees_with_the_hint():
    matrix = tactics.load_matrix()
    permille = _defaults().career_style_counter_permille
    assert matrix["counter_permille"] == permille
    # Engine constants or the counter table changed -> regenerate with
    # `python scripts/simulate_career_tactics.py --n 2000 --write`.
    assert matrix["fingerprint"] == tactics.engine_fingerprint(permille)
    table = matrix["table"]
    for target in matchup.PLAYSTYLES:
        mirror = table[target][target]["win"]
        for counter in tactics.counters_of(target):
            assert tactics.matchup_hint(counter, target) == "advantage"
            # The simulated outcome agrees with the hint: a counter beats the mirror.
            assert table[counter][target]["win"] > mirror
            assert table[counter][target]["win"] > table[counter][target]["loss"]
    assert matrix["pp_per_rating_point"] > 0


def test_tracker_and_untagged_sides_do_not_change_the_club_engine():
    """Clubs/tournaments: no style edge, and the analysis tracker never
    consumes randomness — the same seed gives the same phases."""
    def sides():
        cards = [(_card(i, s.ideal_position, 70 + i), s) for i, s in enumerate(get_formation_slots("4-3-3"))]
        other = [(_card(100 + i, s.ideal_position, 75), s) for i, s in enumerate(get_formation_slots("4-3-3"))]
        return matchup.build_side(cards, "BALANCED", "WING_PLAY"), matchup.build_side(other, "DEFENSIVE", "HIGH_PRESS")

    config = _defaults()
    a, b = sides()
    random.seed(5)
    plain = [matchup.simulate_phase(m, a, b, config) for m in range(1, 80)]
    random.seed(5)
    tracker: dict = {}
    tracked = [matchup.simulate_phase(m, a, b, config, tracker) for m in range(1, 80)]
    assert [(c.attacking_side, c.minute, c.quality) if c else None for c in plain] == \
           [(c.attacking_side, c.minute, c.quality) if c else None for c in tracked]
    assert tracker["a"]["attacks"] + tracker["b"]["attacks"] == 79


# --- familiarity ------------------------------------------------------------------------

def test_familiarity_grows_to_the_cap_and_a_change_partly_resets_it():
    config = _defaults(career_familiarity_step_tenths=20, career_familiarity_max_tenths=100, career_familiarity_keep_pct=50)
    value, last = 0, (None, None)
    for _ in range(7):
        used = tactics.familiarity_for(value, *last, "4-3-3", "WING_PLAY", config)
        value, last = tactics.familiarity_after_match(used, config), ("4-3-3", "WING_PLAY")
    assert value == 100  # capped
    assert tactics.familiarity_for(value, *last, "4-3-3", "WING_PLAY", config) == 100
    assert tactics.familiarity_for(value, *last, "4-4-2", "WING_PLAY", config) == 50
    assert tactics.familiarity_for(value, *last, "4-4-2", "POSSESSION", config) == 25
    # A mid-match style switch (instruction) also plays at the reduced level.
    runner = _runner(config=config, familiarity=100, playstyle="WING_PLAY")
    assert runner._familiarity_pct("WING_PLAY") == 10 and runner._familiarity_pct("POSSESSION") == 5


def test_familiarity_raises_the_ratings_the_engine_sees():
    config = _defaults()
    plain, familiar = _runner(config=config), _runner(config=config, familiarity=100)
    side_plain, _, _ = plain.state_at(1, 0, 0)
    side_fam, _, _ = familiar.state_at(1, 0, 0)
    assert side_fam.cards[0].player.rating > side_plain.cards[0].player.rating
    assert side_fam.profile.midfield_control > side_plain.profile.midfield_control


# --- match plan ---------------------------------------------------------------------------

def test_plan_validation_limits_and_formats():
    config = _defaults(career_max_plan_rules=3, career_max_substitutions=3)
    slots = {s.code for s in get_formation_slots("4-3-3")}
    rule = {"score": "behind", "margin": 1, "from_minute": 60, "mentality": "ATTACKING"}
    plan = tactics.clean_plan({"rules": [rule], "subs": [{"minute": 70, "slot": "FWD2", "card_id": 5}]}, slots, {5}, config)
    assert plan["rules"][0]["mentality"] == "ATTACKING" and plan["subs"][0]["min_fatigue"] == 0
    bad = [
        {"rules": [rule] * 4},
        {"subs": [{"minute": 60}] * 4},
        {"rules": [{**rule, "from_minute": 95}]},
        {"rules": [{**rule, "score": "winning"}]},
        {"rules": [{"score": "level", "from_minute": 10}]},  # changes nothing
        {"rules": [{**rule, "mentality": "YOLO"}]},
        {"subs": [{"minute": 60, "card_id": 999}]},  # not in the squad
        {"subs": [{"minute": 60, "slot": "XX"}]},
        {"subs": [{"minute": 60, "card_id": 5}, {"minute": 70, "card_id": 5}]},
    ]
    for raw in bad:
        with pytest.raises(tactics.PlanError):
            tactics.clean_plan(raw, slots, {5}, config)
    assert tactics.clean_plan({"rules": [], "subs": []}, slots, {5}, config) is None
    assert tactics.drop_stale_subs({"rules": [], "subs": [{"minute": 60, "slot": "MID3"}]}, {"GK"}) is None


def test_instruction_fires_only_on_its_score_and_minute():
    plan = {"rules": [
        {"score": "behind", "margin": 1, "from_minute": 60, "mentality": "ATTACKING", "playstyle": None},
        {"score": "ahead", "margin": 2, "from_minute": 70, "mentality": "DEFENSIVE", "playstyle": "COUNTER_ATTACK"},
    ], "subs": []}
    r = _runner(plan=plan)
    assert r.state_at(55, 0, 1)[2] == []                   # behind, but before 60'
    assert r.state_at(61, 1, 1)[2] == []                   # 60'+, but level
    side, _, events = r.state_at(62, 1, 2)                 # behind after 60'
    assert side.mentality == "ATTACKING" and events[0]["event_type"] == "tactic_change"
    assert events[0]["payload"]["rule"] == 0
    assert r.state_at(63, 1, 2)[2] == []                   # no repeat while in force
    side, _, events = r.state_at(70, 2, 2)                 # equalised -> back to base
    assert side.mentality == "BALANCED" and events[0]["payload"]["rule"] is None
    assert r.state_at(71, 3, 2)[2] == []                   # ahead by 1 only
    side, _, events = r.state_at(72, 4, 2)                 # ahead by 2 after 70'
    assert (side.mentality, side.playstyle) == ("DEFENSIVE", "COUNTER_ATTACK")
    assert [m["rule"] for m in r.events_meta] == [0, None, 1]


def test_substitutions_by_minute_fatigue_and_limit():
    config = _defaults(career_fatigue_per_match=35)
    plan = {"rules": [], "subs": [
        {"minute": 60, "slot": None, "card_id": None, "min_fatigue": 90},   # most tired, once fatigue >= 90
        {"minute": 65, "slot": "FWD2", "card_id": 52, "min_fatigue": 0},   # a named striker for FWD2
        {"minute": 75, "slot": "GK", "card_id": None, "min_fatigue": 0},   # no keeper on the bench -> skipped
    ]}
    r = _runner(plan=plan, fatigue=40, bench_positions=(Position.CB, Position.CM, Position.ST), config=config)
    r.on_pitch[6].pre_fatigue = 60                         # MID2 (CM, card 6) came in tired
    assert r.state_at(50, 0, 0)[2] == []                   # too early
    assert r.state_at(61, 0, 0)[2] == []                   # 60 + 35*61/90 = 84 < 90, FWD2 sub not due
    _, lineup, events = r.state_at(80, 0, 0)               # 60 + 31 = 91 now, FWD2 sub due too
    subs = [e for e in events if e["event_type"] == "substitution"]
    assert len(subs) == 2
    assert subs[0]["payload"]["out"] == "P6" and subs[0]["payload"]["in_id"] == 51  # bench CM fits MID2
    assert subs[1]["payload"]["in_id"] == 52 and subs[1]["payload"]["out"] == "P9"
    assert any(p["club_card_id"] == 52 for p in lineup)
    assert [m["kind"] for m in r.events_meta] == ["sub", "sub", "sub_skipped"]
    assert r.state_at(85, 0, 0)[2] == []                   # each plan sub at most once
    minutes = r.minutes_played()
    assert minutes[52] == 10 and minutes[9] == 80 and minutes[51] == 10 and minutes[6] == 80
    assert len([m for m in minutes.values() if m]) == 13


def test_post_match_fatigue_scales_with_minutes():
    part = CareerParticipant(squad_card_ids=[1, 2, 3], condition={})
    cfg = SimpleNamespace(career_fatigue_per_match=36, career_fatigue_recovery=40, career_injury_chance_pct=0,
                          career_yellow_chance_pct=0, career_red_chance_pct=0, career_yellows_for_ban=3, career_form_max=2)
    rng = random.Random(1)
    career_service._after_match(part, {1, 2}, 1, 1, 0, cfg, rng, {}, minutes={1: 90, 2: 30})
    assert career_service._condition(part, 1)["fatigue"] == 36
    assert career_service._condition(part, 2)["fatigue"] == 12
    assert career_service._condition(part, 3)["fatigue"] == 0


# --- adaptive bots ---------------------------------------------------------------------------

def _bot_team(playstyle="WING_PLAY"):
    return {"index": 3, "formation": "4-3-3", "mentality": "BALANCED", "playstyle": playstyle,
            "players": [{"rating": 75}] * 11}


def test_bots_by_difficulty():
    config = _defaults(career_bot_counter_chance_pct=[100, 60, 85])
    history = [{"round": 0, "formation": "4-3-3", "mentality": "BALANCED", "playstyle": "POSSESSION"}]
    amateur = tactics.bot_tactics_for_round(_bot_team(), "amateur", history, {}, config, 0.0)
    assert amateur["playstyle"] == "WING_PLAY" and not amateur["adapted"] and amateur["plan"] is None
    pro = tactics.bot_tactics_for_round(_bot_team(), "pro", history, {}, config, 0.59)
    assert pro["adapted"] and pro["playstyle"] in tactics.counters_of("POSSESSION")
    assert not tactics.bot_tactics_for_round(_bot_team(), "pro", history, {}, config, 0.6)["adapted"]
    assert not tactics.bot_tactics_for_round(_bot_team(), "pro", [], {}, config, 0.0)["adapted"]  # nothing played yet
    # Legend: keeps a well-drilled style when the switch isn't worth the
    # familiarity it costs; switches when it is; always has its plan.
    drilled = tactics.bot_tactics_for_round(
        _bot_team(), "legend", history, {"playstyle": "WING_PLAY", "familiarity": 100},
        _defaults(career_familiarity_keep_pct=0, career_bot_counter_chance_pct=[0, 0, 100]), 0.0,
    )
    fresh = tactics.bot_tactics_for_round(
        _bot_team(), "legend", history, {"playstyle": "WING_PLAY", "familiarity": 0},
        _defaults(career_bot_counter_chance_pct=[0, 0, 100]), 0.0,
    )
    assert drilled["plan"] == tactics.LEGEND_BOT_PLAN and fresh["plan"] == tactics.LEGEND_BOT_PLAN
    gain = tactics.win_pct(fresh["playstyle"], "POSSESSION") - tactics.win_pct("WING_PLAY", "POSSESSION")
    loss = 100 / 1000 * 75 * tactics.pp_per_rating_point()
    assert fresh["adapted"]
    assert drilled["adapted"] == (gain > loss)


# --- analysis -------------------------------------------------------------------------------

def test_analysis_reports_only_what_the_engine_recorded():
    config = _defaults()
    plan = {"rules": [{"score": "level", "margin": 0, "from_minute": 30, "mentality": "ATTACKING", "playstyle": None}],
            "subs": [{"minute": 60, "slot": None, "card_id": None, "min_fatigue": 0}]}
    random.seed(11)
    a = _runner("a", "HIGH_PRESS", plan=plan, bench_positions=(Position.CM, Position.ST, Position.CB), config=config)
    b = _runner("b", "POSSESSION", config=config, offset=1000)
    tracker: dict = {}
    result = engine.simulate_match_controlled(tactics.CareerMatchController(a, b), config, "A", "B", tracker=tracker)
    analysis = tactics.build_analysis(result.event_log, tracker, "a", a, b.playstyle)
    assert sum(analysis["goals_mine"].values()) == result.score_a
    assert sum(analysis["goals_theirs"].values()) == result.score_b
    assert analysis["matchup"] == "advantage"  # HIGH_PRESS counters POSSESSION
    rule_events = [e for e in result.event_log if e["event_type"] == "tactic_change" and e["team"] == "a"]
    sub_events = [e for e in result.event_log if e["event_type"] == "substitution" and e["team"] == "a"]
    assert len(analysis["instructions"]) == len(rule_events) >= 1
    assert len([s for s in analysis["substitutions"] if s["kind"] == "sub"]) == len(sub_events) == 1
    counter_goals = [e for e in result.event_log
                     if e["event_type"] == "goal" and e["team"] == "a" and (e["payload"] or {}).get("origin") == "counter"]
    assert analysis["goals_mine"]["counter"] == len(counter_goals)
    mine = analysis["mine"]
    assert mine["attacks"] == tracker["a"].get("attacks", 0)
    assert mine["wing_attack"] + mine["central_attack"] + mine["recycled"] == mine["attacks"]
    assert analysis["theirs"]["breakdown"] == tracker["b"].get("breakdown", 0)
    assert mine["counters"] <= analysis["theirs"]["breakdown"]  # every counter starts from a won ball


# --- season integration ----------------------------------------------------------------------

async def _season(client, db_session, bot_token, tg_id):
    user_id, headers = await _player_with_cards(client, db_session, bot_token, tg_id)
    resp = await client.post(f"{API}/career/seasons", headers=headers, json={})
    assert resp.status_code == 200, resp.text
    return user_id, headers, resp.json()["season"]


async def _season_row(db_session, season_id) -> CareerSeason:
    db_session.expire_all()
    return await db_session.get(CareerSeason, season_id)


async def test_scouting_tactics_deadline_and_round_history(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 870001)
    assert season["tactics_version"] == 1
    scout = season["scouting"]
    assert scout["round_index"] == 0 and scout["source"] == "season_start" and scout["is_bot"]
    assert scout["hint"] == tactics.matchup_hint(season["playstyle"], scout["playstyle"])
    assert season["familiarity"]["current_pct"] == 0

    # Tactics for round 1, sent while preparing for round 1 (index 0).
    lineup = season["lineup"]
    resp = await client.put(f"{API}/career/lineup", headers=headers, json={
        "slots": lineup, "formation": "4-3-3", "mentality": "ATTACKING", "playstyle": "WING_PLAY", "round_index": 0,
    })
    assert resp.status_code == 200, resp.text
    hint = resp.json()["season"]["scouting"]["hint"]
    assert hint == tactics.matchup_hint("WING_PLAY", scout["playstyle"])

    first = datetime.fromisoformat(season["schedule"][0])
    assert await career_service.resolve_due(db_session, season["id"], now=first + timedelta(minutes=1)) == 1

    # Round 1 has kicked off: a change still aimed at it is refused.
    resp = await client.put(f"{API}/career/lineup", headers=headers, json={
        "slots": lineup, "formation": "4-3-3", "mentality": "BALANCED", "playstyle": "POSSESSION", "round_index": 0,
    })
    assert resp.status_code == 409 and resp.json()["error"]["details"]["code"] == "round_started"
    resp = await client.put(f"{API}/career/lineup", headers=headers, json={
        "slots": lineup, "formation": "4-3-3", "mentality": "BALANCED", "playstyle": "POSSESSION", "round_index": 1,
    })
    assert resp.status_code == 200
    view = resp.json()["season"]
    # Round 1 was played (and stays recorded) with the tactics in force at kick-off.
    row = await _season_row(db_session, season["id"])
    my = row.state["played_tactics"]["0"]
    assert my == [{"round": 0, "formation": "4-3-3", "mentality": "ATTACKING", "playstyle": "WING_PLAY"}]
    part = (await db_session.execute(select(CareerParticipant).where(CareerParticipant.user_id == user_id))).scalar_one()
    assert part.familiarity == 20 and part.familiar_playstyle == "WING_PLAY"
    # The switch to POSSESSION keeps half of it.
    assert view["familiarity"]["stored_pct"] == 2 and view["familiarity"]["current_pct"] == 1
    # Scouting the round-2 opponent shows what it actually played in round 1.
    scout = view["scouting"]
    assert scout["source"] == "last_match" and len(scout["form"]) == 1
    assert scout["playstyle"] == row.state["played_tactics"][str(scout["opponent_index"])][-1]["playstyle"]

    # The match report carries the analysis for my side only.
    match_index = next(i for i, m in enumerate(row.state["results"][0]) if 0 in (m["home"], m["away"]))
    resp = await client.get(f"{API}/career/seasons/{season['id']}/rounds/0/matches/{match_index}", headers=headers)
    data = resp.json()
    assert data["my_side"] in ("a", "b") and data["analysis"]["playstyle"] == "WING_PLAY"
    assert data["analysis"]["mentality"] == "ATTACKING"


async def test_plan_api_validates_and_is_snapshotted_at_kick_off(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 870002)
    bench = [s["card_id"] for s in season["squad"]
             if s["card_id"] not in season["lineup"].values() and s["card"] and s["card"]["player"]["position"] == "ST"]
    plan = {
        "rules": [{"score": "behind", "margin": 1, "from_minute": 60, "mentality": "ATTACKING"}],
        "subs": [{"minute": 70, "slot": "FWD2", "card_id": bench[0], "min_fatigue": 0}],
        "round_index": 0,
    }
    resp = await client.put(f"{API}/career/plan", headers=headers, json=plan)
    assert resp.status_code == 200, resp.text
    saved = resp.json()["season"]["match_plan"]
    assert saved["rules"][0]["mentality"] == "ATTACKING" and saved["subs"][0]["card_id"] == bench[0]
    assert resp.json()["season"]["plan_limits"] == {"rules": 3, "subs": 3}

    too_many = {**plan, "rules": plan["rules"] * 4}
    assert (await client.put(f"{API}/career/plan", headers=headers, json=too_many)).status_code == 409
    foreign = {**plan, "subs": [{"minute": 70, "card_id": 10 ** 9}]}
    assert (await client.put(f"{API}/career/plan", headers=headers, json=foreign)).status_code == 409

    first = datetime.fromisoformat(season["schedule"][0])
    await career_service.resolve_due(db_session, season["id"], now=first + timedelta(minutes=1))
    row = await _season_row(db_session, season["id"])
    match = next(m for m in row.state["results"][0] if 0 in (m["home"], m["away"]))
    assert match["analysis"]["0"]["plan"] == saved
    # The bench sub came on (fatigue 0 threshold) and is logged as an event.
    subs = [e for e in match["events"] if e["event_type"] == "substitution"]
    assert len(subs) == 1 and subs[0]["payload"]["in_id"] == bench[0]


async def test_pro_bot_counters_only_already_played_tactics(client, db_session, bot_token):
    config = await get_config(db_session)
    config.career_bot_counter_chance_pct = [0, 100, 100]
    await db_session.commit()
    user_id, headers, season = await _season(client, db_session, bot_token, 870003)
    row = await _season_row(db_session, season["id"])
    row.difficulty = "pro"
    await db_session.commit()

    lineup = season["lineup"]
    put = lambda style, r: client.put(f"{API}/career/lineup", headers=headers, json={  # noqa: E731
        "slots": lineup, "formation": "4-3-3", "mentality": "BALANCED", "playstyle": style, "round_index": r,
    })
    assert (await put("CENTRAL_PLAY", 0)).status_code == 200
    first = datetime.fromisoformat(season["schedule"][0])
    await career_service.resolve_due(db_session, season["id"], now=first + timedelta(minutes=1))
    # Before round 2 the human switches to WING_PLAY — the bot must not see it.
    assert (await put("WING_PLAY", 1)).status_code == 200
    second = datetime.fromisoformat(season["schedule"][1])
    await career_service.resolve_due(db_session, season["id"], now=second + timedelta(minutes=1))

    row = await _season_row(db_session, season["id"])
    match = next(m for m in row.state["results"][1] if 0 in (m["home"], m["away"]))
    bot_index = match["away"] if match["home"] == 0 else match["home"]
    bot_style = match["tactics"][str(bot_index)]["playstyle"]
    assert bot_style in tactics.counters_of("CENTRAL_PLAY")  # last PLAYED style
    assert match["tactics"]["0"]["playstyle"] == "WING_PLAY"
    # Bot-vs-bot matches never adapt (no human history to read).
    for m in row.state["results"][1]:
        if 0 not in (m["home"], m["away"]):
            for index in (m["home"], m["away"]):
                assert m["tactics"][str(index)]["playstyle"] == row.state["teams"][index]["playstyle"]


async def test_old_seasons_play_on_the_original_path(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 870004)
    row = await _season_row(db_session, season["id"])
    state = copy.deepcopy(row.state)
    del state["tactics_version"]
    row.state, row.division = state, None
    for part in row.participants:
        part.division = None
    await db_session.commit()

    view = (await client.get(f"{API}/career", headers=headers)).json()["season"]
    assert view["tactics_version"] == 0 and view["familiarity"] is None and view["scouting"]["hint"] is None
    assert view["division"] is None
    assert (await client.put(f"{API}/career/plan", headers=headers,
                             json={"rules": [{"score": "level", "from_minute": 5, "mentality": "ATTACKING"}]})).status_code == 409

    later = datetime.now(timezone.utc) + timedelta(days=8)
    assert await career_service.resolve_due(db_session, season["id"], now=later) == 14
    row = await _season_row(db_session, season["id"])
    assert row.status == "finished" and "played_tactics" not in row.state
    for round_results in row.state["results"]:
        for m in round_results:
            assert "analysis" not in m and "tactics" not in m
            for e in m["events"] or []:
                assert e["event_type"] not in ("tactic_change", "substitution")
    part = (await db_session.execute(select(CareerParticipant).where(CareerParticipant.user_id == user_id))).scalar_one()
    assert part.familiarity == 0 and part.next_division is None


# --- divisions ---------------------------------------------------------------------------------

def test_division_after_promotion_and_relegation():
    config = _defaults(career_division_count=5, career_division_promote=2, career_division_relegate=2)
    assert career_service.division_after(5, 1, config) == 4
    assert career_service.division_after(5, 2, config) == 4
    assert career_service.division_after(5, 3, config) == 5
    assert career_service.division_after(3, 7, config) == 4
    assert career_service.division_after(5, 8, config) == 5   # nowhere lower
    assert career_service.division_after(1, 1, config) == 1   # nowhere higher
    assert career_service.division_name(1, config) == "Высшая лига"


async def test_divisions_set_difficulty_and_move_between_seasons(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 870005)
    config = await get_config(db_session)
    count = config.career_division_count
    assert season["division"]["division"] == count  # newcomers start at the bottom
    assert season["difficulty"] == config.career_division_bot_level[count - 1]

    later = datetime.now(timezone.utc) + timedelta(days=8)
    await career_service.resolve_due(db_session, season["id"], now=later)
    part = (await db_session.execute(select(CareerParticipant).where(CareerParticipant.user_id == user_id))).scalar_one()
    expected = career_service.division_after(count, part.final_place, config)
    assert part.next_division == expected

    view = (await client.get(f"{API}/career", headers=headers)).json()
    assert view["division"]["division"] == expected
    assert view["season"]["next_division"]["division"] == expected

    # Force a title to check the next season really starts one division up.
    part.next_division = count - 1
    await db_session.commit()
    second = (await client.post(f"{API}/career/seasons", headers=headers, json={"difficulty": "amateur"})).json()["season"]
    assert second["division"]["division"] == count - 1
    assert second["difficulty"] == config.career_division_bot_level[count - 2]  # the manual choice is ignored

    # Leaving a running season is a relegation.
    assert (await client.post(f"{API}/career/leave", headers=headers)).status_code == 204
    db_session.expire_all()
    left = (await db_session.execute(
        select(CareerParticipant).where(CareerParticipant.user_id == user_id).order_by(CareerParticipant.id.desc())
    )).scalars().first()
    assert left.next_division == count
