import copy
import random

import pytest

from app.services import kontra_engine as engine


def _unit(uid, side, position="ST", tier="legendary", rating=85, attack=85, defense=70, **kw):
    return engine.make_unit(uid, side, name=uid, card=None, position=position, tier=tier,
                            rating=rating, attack=attack, defense=defense, **kw)


def _squad(side, prefix, tier="legendary", rating=85):
    positions = ("ST", "RW", "CM", "CB", "GK")
    return [_unit(f"{prefix}{i}", side, position=p, tier=tier, rating=rating) for i, p in enumerate(positions, 1)]


def _battle(me=None, foe=None, manual=False, mode="arena", max_rounds=80):
    return engine.new_battle("t", me or _squad("me", "m"), foe or _squad("foe", "f"),
                             mode=mode, max_rounds=max_rounds, manual=manual)


def test_rarity_ladder_and_legendary_level_passives():
    assert engine.abilities_for("attacker", "common") == ["strike"]
    assert len(engine.abilities_for("attacker", "rare")) == 2
    assert len(engine.abilities_for("attacker", "epic")) == 3
    for tier in ("legendary", "diamond", "path", "my_player"):
        assert len(engine.abilities_for("attacker", tier)) == 3
        assert engine.passive_for("attacker", tier) is not None
    assert engine.passive_for("goalkeeper", "epic") is None
    assert engine.passive_for("defender", "diamond") == "star_hour"
    assert engine.passive_for("defender", "path") == "grows"
    assert engine.passive_for("defender", "my_player") == "captain"
    assert engine.passive_for("defender", "legendary") == "armor"


def test_roles_follow_positions():
    assert _unit("a", "me", position="RW")["role"] == "attacker"
    assert _unit("a", "me", position="CDM")["role"] == "midfielder"
    assert _unit("a", "me", position="LB")["role"] == "defender"
    gk = _unit("a", "me", position="GK", tier="epic")
    assert gk["role"] == "goalkeeper" and [a["code"] for a in gk["abilities"]] == ["strike", "save", "medics"]


def test_turn_meter_lets_the_fastest_act_first():
    fast = _unit("m1", "me", position="RW", rating=95)
    slow = _unit("f1", "foe", position="CB", rating=70)
    state = _battle([fast], [slow])
    assert engine.advance(state)["id"] == "m1"


def test_auto_battle_is_deterministic_and_ends():
    a = _battle()
    b = copy.deepcopy(a)
    engine.run_until_input(a)
    engine.run_until_input(b)
    assert a["finished"] and a["winner"] in ("me", "foe")
    assert a["events"] == b["events"]


def test_stronger_squad_wins_more_often():
    wins = 0
    for i in range(20):
        state = engine.new_battle(f"s{i}", _squad("me", "m", rating=92), _squad("foe", "f", tier="rare", rating=70),
                                  mode="arena", max_rounds=80, manual=False)
        engine.run_until_input(state)
        wins += state["winner"] == "me"
    assert wins >= 18


def test_manual_battle_waits_for_the_player_and_validates_actions():
    state = _battle(manual=True)
    engine.run_until_input(state)
    actor = engine.unit(state, state["turn_of"])
    assert actor["side"] == "me" and not state["finished"]
    other = next(u for u in state["units"] if u["side"] == "me" and u["id"] != actor["id"])
    with pytest.raises(engine.EngineError):
        engine.act(state, other["id"], "strike")
    with pytest.raises(engine.EngineError):
        engine.act(state, actor["id"], "medics" if actor["role"] != "goalkeeper" else "penalty")
    active = actor["abilities"][1]["code"]
    events = engine.act(state, actor["id"], active)
    assert events[0]["kind"] == "ability" and events[0]["ability"] == active
    assert engine.unit(state, actor["id"])["abilities"][1]["cd"] > 0
    state["turn_of"] = actor["id"]
    with pytest.raises(engine.EngineError):
        engine.act(state, actor["id"], active)  # still on cooldown


def test_effects_taunt_shield_stun_and_offside():
    defender = _unit("m1", "me", position="CB")
    striker = _unit("f1", "foe", position="ST")
    state = _battle([defender, _unit("m2", "me", position="GK")], [striker])
    state["turn_of"] = "m1"
    engine.act(state, "m1", "wall")
    assert engine.has(defender, "taunt") and engine.has(defender, "shield")
    state["turn_of"] = "f1"
    events = engine.act(state, "f1", "strike", "m2")  # taunt forces the target
    hit = next(e for e in events if e["kind"] == "hit")
    assert hit["target"] == "m1" and hit["absorbed"] > 0

    state["turn_of"] = "m1"
    engine.act(state, "m1", "offside")
    state["turn_of"] = "f1"
    events = engine.act(state, "f1", "strike")
    assert any(e["kind"] == "miss" for e in events)

    engine.add_effect(striker, "stun", 1)
    for u in state["units"]:
        u["meter"] = 0
    striker["meter"] = engine.TURN_METER
    engine.advance(state)
    assert not engine.has(striker, "stun")
    assert any(e["kind"] == "stunned" and e["target"] == "f1" for e in state["events"])


def test_star_hour_gives_an_extra_turn_once():
    star = _unit("m1", "me", tier="diamond", defense=40)
    brute = _unit("f1", "foe", attack=99, rating=99)
    state = _battle([star], [brute])
    star["hp"] = star["max_hp"] * 35 // 100
    state["turn_of"] = "f1"
    engine.act(state, "f1", "strike")
    if star["alive"]:
        assert star["star_used"] and star["meter"] >= engine.TURN_METER


def test_boss_fight_counts_damage_and_ends_on_time():
    boss = engine.make_boss("boss", name="Тренер-тиран", max_hp=10_000_000, atk=200, defense=150, spd=100,
                            abilities=["boss_slam", "boss_card", "boss_chant"])
    state = engine.new_battle("b", _squad("me", "m"), [boss], mode="boss", max_rounds=10, manual=False)
    engine.run_until_input(state)
    assert state["finished"] and state["winner"] in ("time", "foe")
    assert state["damage_to_foe"] > 0 and state["damage_to_foe"] == boss["max_hp"] - boss["hp"]


def test_team_bonuses_leader_aura_and_chemistry():
    squad = _squad("me", "m")
    base_spd = [u["spd"] for u in squad]
    base_atk = [u["atk"] for u in squad]
    engine.apply_team_bonuses(squad, "m3", 6)  # CM leader: +8% speed
    assert all(u["spd"] >= s for u, s in zip(squad, base_spd))
    assert all(u["atk"] > a for u, a in zip(squad, base_atk))
    assert squad[2].get("leader")


def test_gear_percentages_apply():
    plain = _unit("a", "me")
    geared = _unit("a", "me", gear={"pct": {"spd": 10, "atk": 5, "crit": 7}})
    assert geared["spd"] > plain["spd"] and geared["atk"] > plain["atk"] and geared["crit"] == plain["crit"] + 7


# ---------------------------------------------------------------------------
# Tactics and the leader's ultimate
# ---------------------------------------------------------------------------

def test_tactics_cycle_and_stat_bonus():
    assert engine.beats("pressing", "tiki") and engine.beats("tiki", "bus") and engine.beats("bus", "pressing")
    assert not engine.beats("tiki", "pressing") and not engine.beats(None, "bus") and not engine.beats("bus", None)
    squad = _squad("me", "m")
    atk = [u["atk"] for u in squad]
    engine.apply_tactic(squad, "pressing")
    assert all(u["atk"] == round(a * 108 / 100) for u, a in zip(squad, atk))
    engine.apply_tactic(squad, None)  # no scheme: nothing changes
    assert all(u["atk"] == round(a * 108 / 100) for u, a in zip(squad, atk))


def _hit_damage(tactics, edge):
    state = engine.new_battle("edge", _squad("me", "m"), _squad("foe", "f"), mode="arena", max_rounds=50,
                              manual=True, tactics=tactics, edge=edge)
    attacker, target = engine.unit(state, "m1"), engine.unit(state, "f1")
    engine._hit(state, attacker, target, 100, random.Random(1), "strike")
    return state["events"][-1]


def test_a_countering_tactic_hits_harder():
    plain = _hit_damage({"me": "pressing", "foe": "bus"}, 10)  # bus beats pressing, not the other way
    edged = _hit_damage({"me": "pressing", "foe": "tiki"}, 10)
    assert "edge" not in plain and edged["edge"] is True
    assert edged["damage"] > plain["damage"]


def _with_leader(role_position="CB"):
    me = _squad("me", "m")
    leader = next(u for u in me if u["position"] == role_position)
    engine.apply_team_bonuses(me, leader["id"], 0)
    return me, leader


def test_only_the_leader_gets_the_ultimate_and_it_needs_full_charge():
    me, leader = _with_leader("ST")
    assert [a["code"] for a in leader["abilities"]][-1] == "ult_attacker"
    assert all(not any(engine.is_ult(a["code"]) for a in u["abilities"]) for u in me if u is not leader)
    state = engine.new_battle("u", me, _squad("foe", "f"), mode="arena", max_rounds=50, manual=True)
    state["turn_of"] = leader["id"]
    assert "ult_attacker" not in engine.available(leader, state)
    with pytest.raises(engine.EngineError):
        engine.act(state, leader["id"], "ult_attacker", "f1")
    state["charge"]["me"] = engine.ULT_FULL
    assert "ult_attacker" in engine.available(leader, state)
    target = engine.unit(state, "f2")
    engine.add_effect(target, "shield", 2, 10_000)
    events = engine.act(state, leader["id"], "ult_attacker", "f2")
    assert events[0]["ult"] is True and state["charge"]["me"] == 0
    hit = next(e for e in events if e["kind"] == "hit")
    assert hit["target"] == "f2" and hit["absorbed"] == 0 and hit["damage"] > 0  # straight through the shield


def test_charge_fills_from_actions_and_hits_taken():
    state = _battle(manual=True)
    actor = engine.advance(state)
    engine.act(state, actor["id"], "strike", None)
    side, other_side = actor["side"], engine.other(actor["side"])
    assert state["charge"][side] == engine.ULT_CHARGE_ACTION
    assert state["charge"][other_side] == engine.ULT_CHARGE_HIT_TAKEN


@pytest.mark.parametrize("position,code", [("CB", "ult_defender"), ("GK", "ult_goalkeeper"), ("CM", "ult_midfielder")])
def test_team_ultimates(position, code):
    me, leader = _with_leader(position)
    state = engine.new_battle("t", me, _squad("foe", "f"), mode="arena", max_rounds=50, manual=True)
    state["turn_of"], state["charge"]["me"] = leader["id"], engine.ULT_FULL
    for u in me:
        u["hp"] = u["max_hp"] // 2
        engine.add_effect(u, "yellow", 2)
    engine.act(state, leader["id"], code)
    if code == "ult_defender":
        assert all(engine.has(u, "shield") for u in me)
    elif code == "ult_goalkeeper":
        assert all(not engine.has(u, "yellow") and u["hp"] > u["max_hp"] // 2 for u in me)
    else:
        assert all(engine.has(u, "haste") for u in me)


def test_the_ai_spends_a_full_charge():
    me, _ = _with_leader("ST")
    foe = _squad("foe", "f")
    engine.apply_team_bonuses(foe, "f1", 0)
    state = engine.new_battle("ai", me, foe, mode="arena", max_rounds=80, manual=False)
    engine.run_until_input(state)
    assert state["finished"]
    assert any(e["kind"] == "ability" and e.get("ult") for e in state["events"])
