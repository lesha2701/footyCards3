"""«Карьера тренера» tactics (career_tactics_service) and divisions: the
axis model and its interaction table (engine, scouting and bots read the
same table; the versioned simulation confirms it), per-round tactics and the
kick-off deadline, match plan (instructions/substitutions), familiarity,
adaptive bots without reading the future, the post-match analysis, the
22-player squad, old-season compatibility, promotion/relegation."""
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

PRESS = tactics.PRESETS["HIGH_PRESS"]
POSSESSION = tactics.PRESETS["POSSESSION"]
COUNTER = tactics.PRESETS["COUNTER_ATTACK"]
NEUTRAL = tactics.NEUTRAL_TACTIC


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


def _runner(label="a", tactic=None, plan=None, fatigue=0, bench_positions=(), config=None,
            familiarity=0, offset=0, rating=75):
    config = config or _defaults()
    on_pitch = [tactics.LivePlayer(_card(offset + i, s.ideal_position, rating), rating, fatigue, slot=s)
                for i, s in enumerate(get_formation_slots("4-3-3"))]
    bench = [tactics.LivePlayer(_card(offset + 50 + i, pos, rating - 2), rating - 2, 0)
             for i, pos in enumerate(bench_positions)]
    return tactics.CareerSideRunner(label, f"Team {label}", "4-3-3", "BALANCED", dict(tactic or NEUTRAL), on_pitch,
                                    bench, config, familiarity=familiarity, plan=plan)


# --- axes, interactions, scouting and the versioned table ----------------------------------

def test_presets_and_tactic_validation():
    for code, axes in tactics.PRESETS.items():
        assert tactics.clean_tactic(axes) == axes and tactics.preset_of(axes) == code
    assert tactics.preset_of({**PRESS, "direction": "wings"}) == tactics.CUSTOM
    with pytest.raises(tactics.TacticError):
        tactics.clean_tactic({**PRESS, "block": "sky_high"})
    with pytest.raises(tactics.TacticError):
        tactics.clean_tactic({"block": "high"})  # incomplete
    with pytest.raises(tactics.TacticError):
        tactics.clean_tactic({**PRESS, "tiki_taka": "yes"})
    assert tactics.clean_tactic({"block": "high"}, partial=True) == {"block": "high"}
    # Old seasons' playstyles map onto presets.
    assert tactics.tactic_for(None, "COUNTER_ATTACK") == COUNTER


def test_every_axis_value_is_a_real_lever_with_a_cost():
    tuning = tactics.tuning_of(_defaults())
    high, low = tactics.TacticAxes({**NEUTRAL, "block": "high"}, tuning), tactics.TacticAxes({**NEUTRAL, "block": "low"}, tuning)
    assert high.initiative_mult() > low.initiative_mult()           # high block wins the ball back more
    assert high.pool_mult() < low.pool_mult()                       # ...with fewer defenders behind
    assert high.fatigue_mult() > low.fatigue_mult()                 # ...and tires faster
    fast = tactics.TacticAxes({**NEUTRAL, "on_win": "fast"}, tuning)
    keep = tactics.TacticAxes({**NEUTRAL, "on_win": "keep"}, tuning)
    assert fast.transition_bonus() > keep.transition_bonus() and keep.initiative_mult() > fast.initiative_mult()
    short = tactics.TacticAxes({**NEUTRAL, "buildup": "short"}, tuning)
    direct = tactics.TacticAxes({**NEUTRAL, "buildup": "direct"}, tuning)
    assert short.retry_chance(90) > direct.retry_chance(90) and short.zone_weights()["none"] > direct.zone_weights()["none"]
    wings = tactics.TacticAxes({**NEUTRAL, "direction": "wings"}, tuning).zone_weights()
    assert wings["wing_attack"] > wings["central_attack"]
    assert abs(sum(wings.values()) - 1) < 1e-9


def test_scouting_report_reads_the_same_table_the_engine_applies():
    """Every item the report shows is an interaction the engine applies in
    a duel between these tactics (and vice versa, minus "base" trade-offs);
    the report is antisymmetric."""
    config = _defaults()
    tuning = tactics.tuning_of(config)
    for a in tactics.PRESETS.values():
        for b in tactics.PRESETS.values():
            report = tactics.matchup_report(a, b, config)
            assert report["score"] == pytest.approx(-tactics.matchup_report(b, a, config)["score"], abs=1e-3)
            for who, att, dfn in (("me", a, b), ("them", b, a)):
                engine_ids = set()
                for kind in ("build_up", "counter"):
                    for zone in ("wing_attack", "central_attack"):
                        _, ids = tactics.TacticAxes(att, tuning).duel_shift(tactics.TacticAxes(dfn, tuning), kind, zone)
                        engine_ids |= set(ids)
                engine_ids -= {ix["id"] for ix in tactics.INTERACTIONS if ix.get("base")}
                assert {i["id"] for i in report["items"] if i["attacker"] == who} == engine_ids
    assert tactics.matchup_report(COUNTER, PRESS, config)["hint"] == "advantage"
    assert tactics.matchup_report(PRESS, COUNTER, config)["hint"] == "disadvantage"


def test_engine_bias_tilts_duels_toward_the_favoured_side():
    weights = matchup._stage1_weights(0.5)
    tilted = matchup._stage1_weights(0.5, 0.2)
    assert tilted[2] > weights[2] and tilted[0] < weights[0] and tilted[1] == weights[1]
    assert matchup._stage1_weights(0.5, 0.0) == list(matchup._band(0.5, matchup.STAGE1_BANDS))


def test_versioned_matrix_is_current_and_agrees_with_the_table():
    matrix = tactics.load_matrix()
    # Engine constants, the interaction table or presets changed -> regenerate
    # with `python scripts/simulate_career_tactics.py --n 1500 --write`.
    assert matrix["fingerprint"] == tactics.engine_fingerprint()
    # Measured one at a time, every interaction helps the side it says it helps.
    assert set(matrix["interactions"]) == {ix["id"] for ix in tactics.INTERACTIONS}
    for ix_id, effect in matrix["interactions"].items():
        assert effect["favoured_delta_pp"] > 0, ix_id
    assert set(matrix["presets"]) == set(tactics.PRESETS)
    assert 5 <= matrix["best_answer_gain_pp"] <= 15
    assert matrix["pp_per_rating_point"] > 0


def test_tracker_and_untagged_sides_do_not_change_the_club_engine():
    """Clubs/tournaments: no career axes, and the analysis tracker never
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
    assert "interactions" not in tracker["a"]


# --- familiarity ------------------------------------------------------------------------

def test_familiarity_grows_to_the_cap_and_changes_partly_reset_it():
    config = _defaults(career_familiarity_step_tenths=20, career_familiarity_max_tenths=90,
                       career_familiarity_keep_pct=50, career_familiarity_axis_keep_pct=80)
    value, last = 0, (None, None)
    for _ in range(6):
        used = tactics.familiarity_for(value, *last, "4-3-3", PRESS, config)
        value, last = tactics.familiarity_after_match(used, config), ("4-3-3", PRESS)
    assert value == 90  # capped
    assert tactics.familiarity_for(value, *last, "4-3-3", PRESS, config) == 90
    assert tactics.familiarity_for(value, *last, "4-4-2", PRESS, config) == 45           # new formation
    assert tactics.familiarity_for(value, *last, "4-3-3", {**PRESS, "block": "mid"}, config) == 72  # one axis
    two_axes = {**PRESS, "block": "mid", "direction": "wings"}
    assert tactics.familiarity_for(value, *last, "4-3-3", two_axes, config) == 57
    # A mid-match instruction plays at the reduced level too.
    runner = _runner(config=config, familiarity=90, tactic=PRESS)
    assert runner._familiarity_pct(PRESS) == 9 and runner._familiarity_pct({**PRESS, "block": "low"}) == 7.2


def test_familiarity_raises_the_ratings_the_engine_sees():
    config = _defaults()
    plain, familiar = _runner(config=config), _runner(config=config, familiarity=90)
    side_plain, _, _ = plain.state_at(1, 0, 0)
    side_fam, _, _ = familiar.state_at(1, 0, 0)
    assert side_fam.cards[0].player.rating > side_plain.cards[0].player.rating
    assert side_fam.profile.midfield_control > side_plain.profile.midfield_control


# --- match plan ---------------------------------------------------------------------------

def test_plan_validation_limits_and_formats():
    config = _defaults(career_max_plan_rules=3, career_max_substitutions=3)
    slots = {s.code for s in get_formation_slots("4-3-3")}
    rule = {"score": "behind", "margin": 1, "from_minute": 60, "mentality": "ATTACKING", "tactic": {"block": "high"}}
    plan = tactics.clean_plan({"rules": [rule], "subs": [{"minute": 70, "slot": "FWD2", "card_id": 5}]}, slots, {5}, config)
    assert plan["rules"][0]["tactic"] == {"block": "high"} and plan["subs"][0]["min_fatigue"] == 0
    bad = [
        {"rules": [rule] * 4},
        {"subs": [{"minute": 60}] * 4},
        {"rules": [{**rule, "from_minute": 95}]},
        {"rules": [{**rule, "score": "winning"}]},
        {"rules": [{"score": "level", "from_minute": 10}]},  # changes nothing
        {"rules": [{**rule, "mentality": "YOLO"}]},
        {"rules": [{**rule, "tactic": {"block": "sky_high"}}]},
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
        {"score": "behind", "margin": 1, "from_minute": 60, "mentality": "ATTACKING", "tactic": {"block": "high"}},
        {"score": "ahead", "margin": 2, "from_minute": 70, "mentality": "DEFENSIVE", "tactic": {"block": "low", "on_win": "fast"}},
    ], "subs": []}
    r = _runner(plan=plan)
    assert r.state_at(55, 0, 1)[2] == []                   # behind, but before 60'
    assert r.state_at(61, 1, 1)[2] == []                   # 60'+, but level
    side, _, events = r.state_at(62, 1, 2)                 # behind after 60'
    assert side.mentality == "ATTACKING" and side.career.tactic["block"] == "high"
    assert events[0]["event_type"] == "tactic_change" and events[0]["payload"]["rule"] == 0
    assert r.state_at(63, 1, 2)[2] == []                   # no repeat while in force
    side, _, events = r.state_at(70, 2, 2)                 # equalised -> back to base
    assert side.mentality == "BALANCED" and side.career.tactic == NEUTRAL and events[0]["payload"]["rule"] is None
    assert r.state_at(71, 3, 2)[2] == []                   # ahead by 1 only
    side, _, events = r.state_at(72, 4, 2)                 # ahead by 2 after 70'
    assert side.mentality == "DEFENSIVE" and side.career.tactic["block"] == "low" and side.career.tactic["on_win"] == "fast"
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
    r.finish()
    minutes = r.minutes_played()
    assert minutes[52] == 10 and minutes[9] == 80 and minutes[51] == 10 and minutes[6] == 80
    assert len([m for m in minutes.values() if m]) == 13
    gained = r.fatigue_gained()
    assert gained[0] == 35 and gained[52] == 4             # full match vs 10 minutes


def test_pressing_tires_players_faster():
    config = _defaults(career_fatigue_per_match=35)
    calm, pressing = _runner(tactic={**NEUTRAL, "block": "low"}), _runner(tactic={**PRESS})
    for r in (calm, pressing):
        r.state_at(45, 0, 0)
        r.finish()
    assert pressing.fatigue_gained()[3] > 35 > calm.fatigue_gained()[3]


def test_post_match_fatigue_uses_what_was_gained():
    part = CareerParticipant(squad_card_ids=[1, 2, 3], condition={})
    cfg = SimpleNamespace(career_fatigue_per_match=36, career_fatigue_recovery=40, career_injury_chance_pct=0,
                          career_yellow_chance_pct=0, career_red_chance_pct=0, career_yellows_for_ban=3, career_form_max=2)
    career_service._after_match(part, {1, 2}, 1, 1, 0, cfg, random.Random(1), {}, gains={1: 45, 2: 12})
    assert career_service._condition(part, 1)["fatigue"] == 45
    assert career_service._condition(part, 2)["fatigue"] == 12
    assert career_service._condition(part, 3)["fatigue"] == 0


# --- adaptive bots ---------------------------------------------------------------------------

def _bot_team(preset="WING_PLAY"):
    return {"index": 3, "formation": "4-3-3", "mentality": "BALANCED", "playstyle": preset,
            "tactic": dict(tactics.PRESETS[preset]), "players": [{"rating": 75}] * 11}


def test_bots_by_difficulty():
    config = _defaults(career_bot_counter_chance_pct=[100, 60, 85])
    history = [{"round": 0, "formation": "4-3-3", "mentality": "BALANCED", "tactic": PRESS}]
    best = max(tactics.PRESETS.values(), key=lambda t: tactics.matchup_report(t, PRESS, config)["score"])
    amateur = tactics.bot_tactics_for_round(_bot_team(), "amateur", history, {}, config, 0.0)
    assert amateur["tactic"] == tactics.PRESETS["WING_PLAY"] and not amateur["adapted"] and amateur["plan"] is None
    pro = tactics.bot_tactics_for_round(_bot_team(), "pro", history, {}, config, 0.59)
    assert pro["adapted"] and pro["tactic"] == best
    assert not tactics.bot_tactics_for_round(_bot_team(), "pro", history, {}, config, 0.6)["adapted"]
    assert not tactics.bot_tactics_for_round(_bot_team(), "pro", [], {}, config, 0.0)["adapted"]  # nothing played yet
    # Legend: keeps a well-drilled tactic when switching costs more familiarity
    # than it gains; switches when it's fresh; always has its plan.
    legend_cfg = _defaults(career_bot_counter_chance_pct=[0, 0, 100], career_familiarity_axis_keep_pct=0)
    drilled = tactics.bot_tactics_for_round(
        _bot_team(), "legend", history, {"tactic": tactics.PRESETS["WING_PLAY"], "familiarity": 900}, legend_cfg, 0.0,
    )
    fresh = tactics.bot_tactics_for_round(
        _bot_team(), "legend", history, {"tactic": tactics.PRESETS["WING_PLAY"], "familiarity": 0}, legend_cfg, 0.0,
    )
    assert fresh["adapted"] and fresh["tactic"] == best
    assert not drilled["adapted"] and drilled["tactic"] == tactics.PRESETS["WING_PLAY"]
    assert drilled["plan"] == tactics.LEGEND_BOT_PLAN == fresh["plan"]


# --- analysis -------------------------------------------------------------------------------

def test_analysis_reports_only_what_the_engine_recorded():
    config = _defaults()
    # One instruction for every score state from 30': at least one fires.
    plan = {"rules": [
        {"score": "level", "margin": 0, "from_minute": 30, "mentality": "ATTACKING", "tactic": {}},
        {"score": "behind", "margin": 1, "from_minute": 30, "mentality": "ATTACKING", "tactic": {}},
        {"score": "ahead", "margin": 1, "from_minute": 30, "mentality": "DEFENSIVE", "tactic": {}},
    ], "subs": [{"minute": 60, "slot": None, "card_id": None, "min_fatigue": 0}]}
    random.seed(11)
    a = _runner("a", PRESS, plan=plan, bench_positions=(Position.CM, Position.ST, Position.CB), config=config)
    b = _runner("b", POSSESSION, config=config, offset=1000)
    tracker: dict = {}
    result = engine.simulate_match_controlled(tactics.CareerMatchController(a, b), config, "A", "B", tracker=tracker)
    analysis = tactics.build_analysis(result.event_log, tracker, "a", a, b)
    assert sum(analysis["goals_mine"].values()) == result.score_a
    assert sum(analysis["goals_theirs"].values()) == result.score_b
    assert analysis["matchup"] == tactics.matchup_report(PRESS, POSSESSION, config)
    rule_events = [e for e in result.event_log if e["event_type"] == "tactic_change" and e["team"] == "a"]
    sub_events = [e for e in result.event_log if e["event_type"] == "substitution" and e["team"] == "a"]
    assert len(analysis["instructions"]) == len(rule_events) >= 1
    assert len([s for s in analysis["substitutions"] if s["kind"] == "sub"]) == len(sub_events) == 1
    mine = analysis["mine"]
    assert mine["attacks"] == tracker["a"].get("attacks", 0)
    assert mine["wing_attack"] + mine["central_attack"] + mine["recycled"] == mine["attacks"]
    assert mine["counters"] == analysis["theirs"]["breakdown"]  # every won ball starts a counter
    # Interaction duels: only ones the table says apply between these tactics.
    for duel in analysis["duels"]:
        att, dfn = (PRESS, POSSESSION) if duel["attacker"] == "me" else (POSSESSION, PRESS)
        applicable = {ix["id"] for kind in ("build_up", "counter") for ix in tactics.interactions_for(att, dfn, kind, None)}
        assert duel["id"] in applicable and 0 <= duel["attacker_won"] <= duel["applied"]
    press = next(d for d in analysis["duels"] if d["id"] == "press_vs_short")
    assert press["attacker"] == "them" and press["applied"] > 0


# --- season integration ----------------------------------------------------------------------

async def _season(client, db_session, bot_token, tg_id):
    user_id, headers = await _player_with_cards(client, db_session, bot_token, tg_id)
    resp = await client.post(f"{API}/career/seasons", headers=headers, json={})
    assert resp.status_code == 200, resp.text
    return user_id, headers, resp.json()["season"]


async def _season_row(db_session, season_id) -> CareerSeason:
    db_session.expire_all()
    return await db_session.get(CareerSeason, season_id)


def _lineup(season, tactic, round_index, mentality="BALANCED", formation="4-3-3"):
    return {"slots": season["lineup"], "formation": formation, "mentality": mentality, "playstyle": "CENTRAL_PLAY",
            "tactic": tactic, "round_index": round_index}


async def test_scouting_tactics_deadline_and_round_history(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 870001)
    assert season["tactics_version"] == 1
    scout = season["scouting"]
    assert scout["round_index"] == 0 and scout["source"] == "season_start" and scout["is_bot"]
    config = await get_config(db_session)
    assert scout["matchup"] == tactics.matchup_report(season["tactic"], scout["tactic"], config)
    assert season["familiarity"]["current_pct"] == 0

    resp = await client.put(f"{API}/career/lineup", headers=headers, json=_lineup(season, PRESS, 0, "ATTACKING"))
    assert resp.status_code == 200, resp.text
    view = resp.json()["season"]
    assert view["tactic"] == PRESS and view["playstyle"] == "HIGH_PRESS"
    assert view["scouting"]["matchup"] == tactics.matchup_report(PRESS, scout["tactic"], config)

    # Preview of an unsaved tactic: the same report.
    resp = await client.post(f"{API}/career/tactics/preview", headers=headers, json={"tactic": COUNTER})
    assert resp.json()["matchup"] == tactics.matchup_report(COUNTER, scout["tactic"], config)

    first = datetime.fromisoformat(season["schedule"][0])
    assert await career_service.resolve_due(db_session, season["id"], now=first + timedelta(minutes=1)) == 1

    # Round 1 has kicked off: a change still aimed at it is refused.
    resp = await client.put(f"{API}/career/lineup", headers=headers, json=_lineup(season, COUNTER, 0))
    assert resp.status_code == 409 and resp.json()["error"]["details"]["code"] == "round_started"
    custom = {**PRESS, "block": "mid"}
    resp = await client.put(f"{API}/career/lineup", headers=headers, json=_lineup(season, custom, 1))
    assert resp.status_code == 200
    view = resp.json()["season"]
    assert view["playstyle"] == tactics.CUSTOM
    # Round 1 stays recorded with the tactic in force at kick-off.
    row = await _season_row(db_session, season["id"])
    my = row.state["played_tactics"]["0"]
    assert my == [{"round": 0, "formation": "4-3-3", "mentality": "ATTACKING", "tactic": PRESS, "preset": "HIGH_PRESS"}]
    part = (await db_session.execute(select(CareerParticipant).where(CareerParticipant.user_id == user_id))).scalar_one()
    assert part.familiarity == 20 and part.familiar_tactic == PRESS
    # One axis changed keeps 80%.
    assert view["familiarity"]["stored_pct"] == 2 and view["familiarity"]["current_pct"] == 1.6
    scout = view["scouting"]
    assert scout["source"] == "last_match" and len(scout["form"]) == 1
    assert scout["tactic"] == row.state["played_tactics"][str(scout["opponent_index"])][-1]["tactic"]

    match_index = next(i for i, m in enumerate(row.state["results"][0]) if 0 in (m["home"], m["away"]))
    data = (await client.get(f"{API}/career/seasons/{season['id']}/rounds/0/matches/{match_index}", headers=headers)).json()
    assert data["my_side"] in ("a", "b") and data["analysis"]["tactic"] == PRESS
    assert data["analysis"]["mentality"] == "ATTACKING"


async def test_squad_of_22_and_bench_for_substitutions(client, db_session, bot_token):
    user_id, headers = await _player_with_cards(client, db_session, bot_token, 870006)
    # 16 cards from the helper + 8 more: enough for a 22-player squad.
    from app.models.card import UserCard
    from app.models.enums import CardSource
    from tests.factories import create_player
    for i, pos in enumerate([Position.LB, Position.RB, Position.CB, Position.CDM, Position.CAM, Position.LW, Position.ST, Position.GK]):
        player = await create_player(db_session, rating=70, position=pos)
        db_session.add(UserCard(owner_id=user_id, player_id=player.id, source=CardSource.seed, serial_number=880000 + i))
    await db_session.commit()
    season = (await client.post(f"{API}/career/seasons", headers=headers, json={})).json()["season"]
    config = await get_config(db_session)
    assert season["squad_size"] == config.career_squad_size == 22 and len(season["squad"]) == 22
    keepers = [s for s in season["squad"] if s["card"] and s["card"]["player"]["position"] == "GK"]
    assert len(keepers) >= 2  # a backup per line


async def test_plan_api_validates_and_is_snapshotted_at_kick_off(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 870002)
    bench = [s["card_id"] for s in season["squad"]
             if s["card_id"] not in season["lineup"].values() and s["card"] and s["card"]["player"]["position"] == "ST"]
    plan = {
        "rules": [{"score": "behind", "margin": 1, "from_minute": 60, "mentality": "ATTACKING", "tactic": {"block": "high"}}],
        "subs": [{"minute": 70, "slot": "FWD2", "card_id": bench[0], "min_fatigue": 0}],
        "round_index": 0,
    }
    resp = await client.put(f"{API}/career/plan", headers=headers, json=plan)
    assert resp.status_code == 200, resp.text
    saved = resp.json()["season"]["match_plan"]
    assert saved["rules"][0]["tactic"] == {"block": "high"} and saved["subs"][0]["card_id"] == bench[0]
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

    assert (await client.put(f"{API}/career/lineup", headers=headers, json=_lineup(season, POSSESSION, 0))).status_code == 200
    first = datetime.fromisoformat(season["schedule"][0])
    await career_service.resolve_due(db_session, season["id"], now=first + timedelta(minutes=1))
    # Before round 2 the human switches to COUNTER — the bot must not see it.
    assert (await client.put(f"{API}/career/lineup", headers=headers, json=_lineup(season, COUNTER, 1))).status_code == 200
    second = datetime.fromisoformat(season["schedule"][1])
    await career_service.resolve_due(db_session, season["id"], now=second + timedelta(minutes=1))

    row = await _season_row(db_session, season["id"])
    match = next(m for m in row.state["results"][1] if 0 in (m["home"], m["away"]))
    bot_index = match["away"] if match["home"] == 0 else match["home"]
    defaults = _defaults()
    best_vs_possession = max(tactics.PRESETS.values(), key=lambda t: tactics.matchup_report(t, POSSESSION, defaults)["score"])
    assert match["tactics"][str(bot_index)]["tactic"] == best_vs_possession  # answer to the last PLAYED tactic
    assert match["tactics"]["0"]["tactic"] == COUNTER
    # Bot-vs-bot matches never adapt (no human history to read).
    for m in row.state["results"][1]:
        if 0 not in (m["home"], m["away"]):
            for index in (m["home"], m["away"]):
                assert m["tactics"][str(index)]["tactic"] == row.state["teams"][index]["tactic"]


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
    assert view["tactics_version"] == 0 and view["familiarity"] is None and view["scouting"]["matchup"] is None
    assert view["division"] is None
    assert (await client.put(f"{API}/career/plan", headers=headers,
                             json={"rules": [{"score": "level", "from_minute": 5, "mentality": "ATTACKING"}]})).status_code == 409
    # Old seasons: presets only (the original engine has no axes).
    assert (await client.put(f"{API}/career/lineup", headers=headers,
                             json=_lineup(view, {**PRESS, "block": "low"}, None))).status_code == 409
    assert (await client.put(f"{API}/career/lineup", headers=headers, json=_lineup(view, COUNTER, None))).status_code == 200

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
    assert {a["key"] for a in view["tactics_catalog"]["axes"]} == set(tactics.AXES)

    part.next_division = count - 1
    await db_session.commit()
    second = (await client.post(f"{API}/career/seasons", headers=headers, json={"difficulty": "amateur"})).json()["season"]
    assert second["division"]["division"] == count - 1
    assert second["difficulty"] == config.career_division_bot_level[count - 2]  # the manual choice is ignored

    assert (await client.post(f"{API}/career/leave", headers=headers)).status_code == 204
    db_session.expire_all()
    left = (await db_session.execute(
        select(CareerParticipant).where(CareerParticipant.user_id == user_id).order_by(CareerParticipant.id.desc())
    )).scalars().first()
    assert left.next_division == count
