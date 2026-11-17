"""«Мяч и Магия» rules engine: maps, moves, battles, bot."""
import copy
import random

import pytest

from app.services import magic_engine as E


def _army(faction="dawn", tiers=(1, 2, 3, 4, 5), copies=9):
    units = E.FACTIONS[faction]["units"]
    return [{"unit": units[t - 1], "count": E.stack_count(t, copies, 300), "card": {"name": f"P{i}"},
             "position": "ST", "rating": 80, "copies": copies} for i, t in enumerate(tiers)]


def _run(seed="s1", faction="dawn", difficulty="normal", **kw):
    return E.new_run(seed, faction=faction, difficulty=difficulty, army=_army(faction, **kw), hero_level_=1,
                     days=7, moves_per_day=8, stack_cap=300)


def _see_all(s):
    s["seen"] = [(1 << E.MAP_W) - 1] * E.MAP_H


def _walk_to(s, obj):
    """Teleports the hero next to `obj` (a free neighbour) with moves to spare, then steps on it."""
    _see_all(s)
    for nx, ny in E._neighbours(s, obj["x"], obj["y"]):
        if (nx, ny) not in E._blocked(s) and E._object_at(s, nx, ny) is None and (nx, ny) != (s["bot"]["x"], s["bot"]["y"]):
            s["hero"]["x"], s["hero"]["y"] = nx, ny
            break
    s["hero"]["moves"] = 99
    E.move_hero(s, obj["x"], obj["y"])


def _autoplay(s, chest="gold"):
    for _ in range(400):
        if s["finished"]:
            return
        if s["phase"] == "battle":
            E.set_auto(s)
        elif s["phase"] == "battle_over":
            E.leave_battle(s)
        elif s["phase"] == "final_lost":
            E.accept_defeat(s)
        elif s["phase"] == "choice":
            E.choose(s, chest)
        else:
            E.end_day(s)


def test_stack_size_grows_with_the_square_root_of_copies():
    assert E.stack_count(1, 1, 300) == 10
    assert E.stack_count(1, 100, 300) == 100
    assert E.stack_count(5, 1, 300) == 3
    assert E.stack_count(1, 10_000, 300) == 300  # the cap


def test_map_is_seeded_and_every_object_is_reachable():
    a, b = _run("same"), _run("same")
    assert a["map"] == b["map"]
    assert a["map"]["blocks"] != _run("other")["map"]["blocks"]  # a new layout every run
    start = E.ME_CASTLE
    for o in a["map"]["objects"]:
        assert E.map_path(a, start, (o["x"], o["y"])) is not None
    kinds = [o["kind"] for o in a["map"]["objects"]]
    assert kinds.count("camp") == 14 and kinds.count("chest") == 8 and kinds.count("castle") == 2
    assert kinds.count("market") == 2 and kinds.count("mine") == 2
    assert a["map"]["biome"] in E.BIOMES and len(a["map"]["blocks"]) > 30


def test_maps_are_fair_mirror_images():
    s = _run("fair")
    cells = {(b[0], b[1]) for b in s["map"]["blocks"]}
    assert all(E._mirror(*c) in cells for c in cells)
    by_kind = {}
    for o in s["map"]["objects"]:
        by_kind.setdefault(o["kind"], set()).add((o["x"], o["y"]))
    for kind, where in by_kind.items():
        assert {E._mirror(*c) for c in where} == where, kind


def test_fog_hides_the_far_map():
    s = _run("fog")
    assert E.is_seen(s, *E.ME_CASTLE) and not E.is_seen(s, *E.BOT_CASTLE)
    assert all(E.is_seen(s, x, y) for x, y in E.reachable(s))
    far = next(o for o in s["map"]["objects"] if not E.is_seen(s, o["x"], o["y"]))
    with pytest.raises(E.EngineError):
        E.move_hero(s, far["x"], far["y"])


def test_hero_spends_moves_and_takes_objects():
    s = _run("walk")
    _see_all(s)
    chest = next(o for o in s["map"]["objects"] if o["kind"] == "chest")
    path = E.map_path(s, E.ME_CASTLE, (chest["x"], chest["y"]))
    s["hero"]["moves"] = 99
    E.move_hero(s, chest["x"], chest["y"])
    assert s["hero"]["moves"] == 99 - (len(path) - 1)
    assert s["phase"] == "choice" and chest["taken_by"] == "me"
    with pytest.raises(E.EngineError):
        E.end_day(s)  # the choice first
    E.choose(s, "gold")
    assert s["hero"]["gold"] == chest["gold"] and s["score"] == E.SCORE["chest"] and s["notice"]["kind"] == "chest"
    with pytest.raises(E.EngineError):
        E.move_hero(s, *s["map"]["blocks"][0][:2])


def test_chest_can_give_experience_instead():
    s = _run("xp")
    chest = next(o for o in s["map"]["objects"] if o["kind"] == "chest")
    _walk_to(s, chest)
    E.choose(s, "xp")
    assert s["hero"]["gold"] == 0 and s["score"] == E.SCORE["chest"] + chest["gold"] // 10


def test_market_hires_for_gold_and_mines_pay_every_morning():
    s = _run("market")
    market = next(o for o in s["map"]["objects"] if o["kind"] == "market")
    _walk_to(s, market)
    assert s["notice"]["kind"] == "market" and s["phase"] == "map"
    offer = market["offers"][0]
    with pytest.raises(E.EngineError):
        E.buy(s, market["id"], 0)  # no gold yet
    s["hero"]["gold"] = offer["price"]
    size = len(s["army"])
    E.buy(s, market["id"], 0)
    assert s["hero"]["gold"] == 0 and offer["bought"] and len(s["army"]) == size + 1
    with pytest.raises(E.EngineError):
        E.buy(s, market["id"], 0)
    mine = next(o for o in s["map"]["objects"] if o["kind"] == "mine")
    _walk_to(s, mine)
    assert mine["taken_by"] == "me"
    s["bot"]["x"], s["bot"]["y"] = E.BOT_CASTLE
    gold = s["hero"]["gold"]
    E.end_day(s)
    assert s["hero"]["gold"] >= gold + E.MINE_GOLD or mine["taken_by"] == "bot"


def test_moves_are_limited_per_day_and_reset_after_end_day():
    s = _run("limit")
    far = max(E.reachable(s) or [[0, 6]], key=lambda c: abs(c[0]) + abs(c[1] - 6))
    s["hero"]["moves"] = 0
    with pytest.raises(E.EngineError):
        E.move_hero(s, *far)
    E.end_day(s)
    assert s["day"] == 2 and s["hero"]["moves"] == 8 + E.QUICK["extra_moves"]


def test_camp_battle_on_autopilot_ends_and_returns_to_map():
    s = _run("camp")
    camp = next(o for o in s["map"]["objects"] if o["kind"] == "camp" and o["level"] == 1)
    _walk_to(s, camp)
    assert s["phase"] == "battle" and s["battle"]["kind"] == "camp"
    E.set_auto(s)
    assert s["battle"]["winner"] in ("me", "foe")
    if s["battle"]["winner"] == "me":
        assert s["phase"] == "battle_over" and camp["taken_by"] == "me" and s["hero"]["morale"] == E.CAMP_MORALE[1]
        E.leave_battle(s)
        assert s["phase"] == "map"


def test_manual_battle_waits_for_the_player_and_validates_moves():
    s = _run("manual")
    E._start_final(s)
    b = s["battle"]
    assert s["phase"] == "battle" and b["turn_of"] and E.bunit(s, b["turn_of"])["side"] == "me"
    u = E.bunit(s, b["turn_of"])
    with pytest.raises(E.EngineError):
        E.stack_act(s, u["id"], "move", None, 7, 0)  # too far / taken
    cell = next(iter(E.move_cells(s, u)))
    E.stack_act(s, u["id"], "move", None, *cell)
    assert (u["x"], u["y"]) == cell
    E.run_until_input(s)
    assert s["battle"]["turn_of"] != u["id"] or s["battle"]["round"] > 1


def test_spells_cost_mana_and_once_per_round():
    s = _run("spell")
    E._start_final(s)
    me = E._alive(s, "me")[0]
    mana = s["hero"]["mana"]
    E.cast(s, "me", "bless", me["id"])
    assert s["hero"]["mana"] == mana - E.SPELLS["bless"][1] and any(e["code"] == "bless" for e in me["effects"])
    with pytest.raises(E.EngineError):
        E.cast(s, "me", "wall", me["id"])
    with pytest.raises(E.EngineError):
        E.cast(s, "me", "sunstrike", me["id"])  # not learned at level 1


def test_retaliation_and_damage_reduce_counts():
    s = _run("hit")
    E._start_final(s)
    att = E._alive(s, "me")[0]
    dfn = E._alive(s, "foe")[0]
    att["x"], att["y"] = dfn["x"] - 1, dfn["y"]
    before_att, before_dfn = att["count"], dfn["count"]
    s["battle"]["turn_of"] = att["id"]
    E.stack_act(s, att["id"], "attack", dfn["id"], att["x"], att["y"])
    assert dfn["count"] < before_dfn or dfn["count"] == 0
    assert att["count"] <= before_att


def test_full_runs_always_finish_and_difficulty_matters():
    wins = {"easy": 0, "hard": 0}
    for n in range(60):
        r = random.Random(n)
        diff = "easy" if n % 2 else "hard"
        s = E.new_run(f"full{n}", faction=r.choice(["dawn", "ash"]), difficulty=diff,
                      army=_army(tiers=tuple(r.choice([1, 2, 3]) for _ in range(5)), copies=r.randint(1, 20)),
                      hero_level_=1, days=7, moves_per_day=8, stack_cap=300)
        _autoplay(s)
        assert s["finished"] and s["winner"] in ("me", "bot")
        wins[diff] += s["winner"] == "me"
    assert wins["easy"] > wins["hard"]


def test_replays_are_deterministic():
    a, b = _run("det"), _run("det")
    for s in (a, b):
        E._start_final(s)
        E.set_auto(s)
    assert a["battle"]["events"] == b["battle"]["events"] and a["winner"] == b["winner"]


def test_undead_bring_back_a_third_of_the_fallen():
    s = _run("undead", faction="ash", tiers=(1,))
    stack = s["army"][0]
    E._start_final(s)
    u = E._alive(s, "me")[0]
    u["count"] = u["start_count"] - 12
    s["battle"]["winner"] = "me"
    s["battle"]["kind"] = "camp"
    camp = next(o for o in s["map"]["objects"] if o["kind"] == "camp")
    s["battle"]["object"] = camp["id"]
    E._resolve_battle(s)
    assert stack["count"] == stack["max_count"] - 12 + 4


def test_state_survives_json_round_trip():
    import json

    s = _run("json")
    E._start_final(s)
    t = json.loads(json.dumps(s))
    E.set_auto(t)
    assert t["finished"]
    assert copy.deepcopy(t) == t


def test_a_lost_final_waits_for_a_second_chance_once():
    s = _run("retry", difficulty="hard")
    s["bot"]["gain_pct"] = 400  # a sure loss
    E._start_final(s)
    army_before = [dict(a) for a in s["final_snapshot"]["army"]]
    E.set_auto(s)
    assert s["phase"] == "final_lost" and not s["finished"]
    E.retry_final(s)
    assert s["retry_used"] and s["phase"] in ("battle", "final_lost", "finished")
    assert [a["start_count"] for a in s["battle"]["units"] if a["side"] == "me"] == [a["count"] for a in army_before]
    E.set_auto(s)
    assert s["finished"] and s["winner"] == "bot"  # no third try
    with pytest.raises(E.EngineError):
        E.retry_final(s)


def test_accepting_defeat_ends_the_run():
    s = _run("accept", difficulty="hard")
    s["bot"]["gain_pct"] = 400
    E._start_final(s)
    E.set_auto(s)
    E.accept_defeat(s)
    assert s["finished"] and s["winner"] == "bot"


def test_map_is_a_tall_band():
    for seed in ("a", "b", "c", "d", "e"):
        s = E.new_run(seed, faction="dawn", difficulty="normal", army=[{"unit": "dawn_spear", "count": 20}],
                      hero_level_=1, days=7, moves_per_day=8, stack_cap=300)
        assert s["map"]["shape"] == [E.MAP_HALF_W, E.MAP_V0, E.MAP_V1]
        cells = [(o["x"], o["y"]) for o in s["map"]["objects"]] + [tuple(c[:2]) for c in s["map"]["blocks"]]
        cells += [tuple(c) for c in s["map"]["road"]]
        assert all(E.inside(s, x, y) for x, y in cells)
        assert (s["hero"]["x"], s["hero"]["y"]) == E.ME_CASTLE
        assert not E.inside(s, 0, 0) and not E.inside(s, E.MAP_W - 1, 0)


def test_a_river_crosses_the_map_and_the_road_bridges_it():
    for i, mode in enumerate(["quick"] * 6 + ["hardcore"] * 3):
        s = E.new_run(f"river{i}", faction="dawn", difficulty="normal", army=[{"unit": "dawn_spear", "count": 20}],
                      hero_level_=1, days=7, moves_per_day=8, stack_cap=300, mode=mode)
        m, n = s["map"], s["map"]["w"]
        river = {tuple(c) for c in m["river"]}
        water = {(x, y) for x, y, kind, _ in m["blocks"] if kind == "water"}
        road = {tuple(c) for c in m["road"]}
        bridges = {tuple(c) for c in m["bridges"]}
        # Fair: the river is its own mirror, and it runs from one long edge of the band to the other.
        assert river == {(n - 1 - x, n - 1 - y) for x, y in river}
        span = [x - y for x, y in river]
        assert max(span) > m["shape"][0] and min(span) < -m["shape"][0]
        # In the band the river is water, except where the road crosses it on a bridge.
        assert {c for c in river if E.inside(s, *c)} - bridges <= water
        assert bridges and bridges <= road and len(bridges) <= 6


def test_a_long_walk_goes_as_far_as_today_allows():
    s = _run("far")
    _see_all(s)
    camp = max((o for o in s["map"]["objects"] if o["kind"] == "camp"),
               key=lambda o: len(E.map_path(s, E.ME_CASTLE, (o["x"], o["y"])) or []))
    path = E.map_path(s, E.ME_CASTLE, (camp["x"], camp["y"]))
    s["hero"]["moves"] = 3
    assert len(path) - 1 > 3
    E.move_hero(s, camp["x"], camp["y"])
    assert (s["hero"]["x"], s["hero"]["y"]) == path[3] and s["hero"]["moves"] == 0
    assert s["hero"]["goal"] == [camp["x"], camp["y"]] and s["phase"] == "map"
    with pytest.raises(E.EngineError):
        E.move_hero(s, camp["x"], camp["y"])  # no steps left today
    E.end_day(s)
    if s["phase"] == "map":
        assert s["hero"]["goal"] == [camp["x"], camp["y"]] and s["hero"]["moves"] > 0


def test_hardcore_is_a_bigger_longer_map():
    s = E.new_run("hc", faction="ash", difficulty="normal", army=[{"unit": "ash_imp", "count": 20}],
                  hero_level_=1, days=7, moves_per_day=9, stack_cap=300, mode="hardcore")
    L = E.MODES["hardcore"]
    assert s["mode"] == "hardcore" and s["days"] == 7 + L["extra_days"] and s["map"]["w"] == L["n"]
    assert len(E.BANDS["hardcore"]) > 3 * len(E.BANDS["quick"]) and s["days"] == 14
    assert s["moves_per_day"] == 9 and L["runs"] == 2
    assert sum(o["kind"] == "camp" for o in s["map"]["objects"]) == 2 * len(L["camps"])
    assert (s["hero"]["x"], s["hero"]["y"]) == L["me"] and all(E.inside(s, o["x"], o["y"]) for o in s["map"]["objects"])


def test_market_tops_up_a_stack_when_the_army_is_full():
    army = [{"unit": "dawn_guard", "count": 5, "card": {"id": i}} for i in range(6)]
    s = E.new_run("mk", faction="dawn", difficulty="normal", army=army, hero_level_=1, days=7,
                  moves_per_day=9, stack_cap=300)
    while len(s["army"]) < E.MAX_STACKS + 1:
        s["army"].append(E.make_stack(f"x{len(s['army'])}", "dawn_guard", 5, card={"id": 99}))
    before = sum(st["count"] for st in s["army"])
    assert E._add_stack(s, "dawn_guard", 7)
    assert sum(st["count"] for st in s["army"]) == before + 7 and len(s["army"]) == E.MAX_STACKS + 1
    assert not E._add_stack(s, "dawn_phoenix", 1)


def test_position_variants_and_camp_styles():
    assert E.faction_unit("dawn", 1, "ST") == "dawn_squire" and E.faction_unit("dawn", 1, "CM") == "dawn_banner"
    assert E.faction_unit("ash", 3, "CB") == "ash_butcher" and E.faction_unit("ash", 5, "ST") == "ash_dragon"
    s = _run("styles")
    camps = [o for o in s["map"]["objects"] if o["kind"] == "camp"]
    assert all(o["style"] in E.CAMP_STYLES for o in camps)
    for o in camps:
        assert all(f["unit"] in E.CAMP_STYLES[o["style"]]["units"] for f in E.camp_foes(s, o))


def test_battle_has_rocks_wait_and_no_retaliation_on_charge():
    s = _run("rocks")
    camp = next(o for o in s["map"]["objects"] if o["kind"] == "camp")
    _walk_to(s, camp)
    b = s["battle"]
    assert 5 <= len(b["rocks"]) <= 8
    rocks = {tuple(c[:2]) for c in b["rocks"]}
    if s["phase"] == "battle" and b["turn_of"]:
        u = E.bunit(s, b["turn_of"])
        assert not (set(E.move_cells(s, u)) & rocks)
        if u["side"] == "me":
            E.stack_act(s, u["id"], "wait")
            assert b["queue"][-1] == u["id"]


def test_perks_quests_and_events():
    s = _run("perk")
    assert len(s["quests"]) == 2 and s["bot"]["style"] in E.BOT_STYLES
    s["score"] = E.PERK_AT[0]
    E._progress(s)
    assert s["phase"] == "choice" and s["pending"]["kind"] == "perk" and len(s["pending"]["options"]) == 3
    code = s["pending"]["options"][0]["code"]
    E.choose(s, code)
    assert s["perks"] == [code] and s["phase"] == "map"
    s["quests"] = [{"code": "camps", "text": "x", "target": 1, "progress": 0, "done": False, "failed": False}]
    s["stats"]["camps"] = 1
    gold = s["hero"]["gold"]
    E._progress(s)
    assert s["quests"][0]["done"] and s["hero"]["gold"] == gold + E.QUEST_GOLD
    for _ in range(30):
        if E._morning_event(s):
            break
    assert s["event"] and s["event"]["code"] in E.EVENTS


def test_hero_classes_change_the_start():
    def start(cls):
        return E.new_run("cls", faction="dawn", difficulty="normal", army=[{"unit": "dawn_spear", "count": 20}],
                         hero_level_=3, days=7, moves_per_day=9, stack_cap=60, hero_class=cls)
    knight, mage, ranger = start("knight"), start("mage"), start("ranger")
    assert knight["hero"]["class"] == "knight" and mage["hero"]["class"] == "mage"
    assert mage["hero"]["max_mana"] == knight["hero"]["max_mana"] + 6
    assert mage["hero"]["spell_power"] == knight["hero"]["spell_power"] + 1
    assert knight["army"][0]["atk"] == mage["army"][0]["atk"] + 1 and knight["army"][0]["def"] == mage["army"][0]["def"] + 1
    assert ranger["moves_per_day"] == knight["moves_per_day"] + 2 and ranger["hero"]["moves"] == 11 + E.QUICK["extra_moves"]
    assert ranger["army"][0]["spd"] == mage["army"][0]["spd"] + 1
    # Skins dress only their own class.
    assert E.skin_for("ember", "mage") == "ember" and E.skin_for("ember", "knight") == "default"
    assert E.skin_for("unknown", "ranger") == "unknown"
    with pytest.raises(E.EngineError):
        start("bard")


def test_magic_pack_odds_and_pools():
    import random as _r
    r = _r.Random(7)
    cards = [c for _ in range(4000) for c in E.open_pack(r)]
    tiers = [E.UNITS[c]["tier"] for c in cards]
    share = {t: tiers.count(t) / len(tiers) for t in range(1, 6)}
    assert 0.5 < share[1] < 0.6 and 0.24 < share[2] < 0.32 and share[5] < 0.02
    # Every race drops: the army mixes them.
    assert {E.UNITS[c]["faction"] for c in cards} == {"dawn", "ash", "wild"}
    assert set(E.creature_pool(1)) == {"dawn_banner", "dawn_squire", "ash_bones", "ash_hound", "wild_thug"}
    assert all(E.UNITS[c]["faction"] == "ash" for c in E.starter_cards(r, "ash"))


def test_losses_split_into_dead_and_wounded_hired_fighters_fall_first():
    s = _run("loss1")
    st = s["army"][0]
    unit, own = st["unit"], st["own"]
    assert own == st["count"] and s["fallen"] == {}
    # 5 hired fighters joined this stack, then 7 fell: the hired go first, 2 of the collection's own fell.
    st["count"] += 5
    st["max_count"] += 5
    E._own_lost(s, st, 7)
    st["count"] -= 7
    assert s["fallen"] == {unit: 2} and st["own"] == own - 2
    # A tribune refill brings own fallen back first.
    E._own_back(s, st, 1)
    assert s["fallen"] == {unit: 1}
    s["fallen"] = {unit: 9}
    cas = E.casualties(s)
    assert cas["dead"] == {unit: 5} and cas["wounded"] == {unit: 4}  # half (rounded up) dies for good
    assert cas["essence"] == 5 * E.ESSENCE[st["tier"]]
    s["mode"] = "hardcore"
    hard = E.casualties(s)
    assert hard["dead"] == {unit: 9} and hard["wounded"] == {} and hard["essence"] == 2 * 9 * E.ESSENCE[st["tier"]]


def test_forfeit_inside_a_battle_counts_the_field_as_fallen():
    s = _run("loss2")
    s["phase"] = "battle"
    s["battle"] = {"units": [{"id": s["army"][0]["id"], "side": "me"}], "winner": None}
    first = s["army"][0]
    n, unit = first["count"], first["unit"]
    E.forfeit(s)
    assert s["fallen"] == {unit: n} and all(x["unit"] != unit or x["count"] > 0 for x in s["army"])


def test_captain_levels_traits_and_the_guard_on_the_field():
    assert not E.GUARD_CODES & {c for t in range(1, 6) for c in E.creature_pool(t)}
    assert E.level_of(0, E.CAPTAIN_XP) == 1 and E.level_of(8000, E.CAPTAIN_XP) == 3 and E.level_of(99999, E.CAPTAIN_XP) == 5
    assert E.trait_slots(3, E.CAPTAIN_TRAIT_LEVELS) == 1 and E.guard_size(1) == 15 and E.guard_size(10) == 40
    army = _army()
    plain = E.new_run("cap", faction="dawn", difficulty="normal", army=copy.deepcopy(army), hero_level_=1,
                      days=7, moves_per_day=8, stack_cap=300)
    army[0]["captain_level"], army[0]["traits"] = 3, ["striker"]
    grown = E.new_run("cap", faction="dawn", difficulty="normal", army=army, hero_level_=1, days=7, moves_per_day=8,
                      stack_cap=300, scaling_pct=60, guard={"count": 12, "level": 2, "traits": ["wall"], "card": {"name": "G"},
                                            "rating": 80, "position": "CB"})
    a0 = plain["army"][0]["atk"]
    assert grown["army"][0]["atk"] == a0 + E._pct(a0, 10) + E._pct(a0, 15)  # level 3: +10%, «Бомбардир» +15%
    g = grown["army"][-1]
    assert g["guard"] and g["unit"] == E.GUARD and g["count"] == 12 and g["own"] == 12
    # The guard's fallen: half lost in a quick run, all in hardcore; never counted as creature cards.
    # The rivals follow only part of the progress (levels, traits, the guard).
    assert grown["start_power"] < E.army_power(grown["army"])
    full = E.new_run("cap", faction="dawn", difficulty="normal", army=copy.deepcopy(army), hero_level_=1, days=7,
                     moves_per_day=8, stack_cap=300, scaling_pct=100,
                     guard={"count": 12, "level": 2, "card": {"name": "G"}})
    assert full["start_power"] == E.army_power(full["army"])
    grown["fallen"] = {E.GUARD: 5}
    cas = E.casualties(grown)
    assert cas["guard_lost"] == 3 and cas["dead"] == {}
    grown["mode"] = "hardcore"
    assert E.casualties(grown)["guard_lost"] == 5
    grown["battles_won"], grown["winner"] = 2, "me"
    assert E.run_xp(grown) == 40 + 18 + 80  # hardcore: the per-run part ×2 (it costs 2 runs)
    grown["mode"] = "quick"
    assert E.run_xp(grown) == 20 + 14 + 40 and E.run_xp(grown, 50) == 37


def test_every_guard_rarity_has_the_same_power_budget():
    budgets = []
    for rarity in ("common", "rare", "epic", "legendary"):
        unit = E.guard_unit(rarity)
        assert E.UNITS[unit]["faction"] == "guard"
        budgets.append(E.guard_size(10, unit) * E.unit_value(E.UNITS[unit]))
    assert max(budgets) / min(budgets) < 1.06
    assert E.guard_size(10, "magic_guard_common") > E.guard_size(10, E.GUARD) > E.guard_size(10, "magic_guard_legend")
    assert E.guard_fighter_points("magic_guard_legend") > E.guard_fighter_points(E.GUARD) == E.GUARD_POINTS_PER_FIGHTER


def _adventure(seed="adv"):
    return E.new_run(seed, faction="dawn", difficulty="normal", army=_army(), hero_level_=1,
                     days=7, moves_per_day=9, stack_cap=300, mode="adventure")


def test_adventure_is_a_huge_solo_map_with_lost_lairs_far_from_home():
    s = _adventure()
    L = E.MODES["adventure"]
    assert s["days"] == 31 and s["moves_per_day"] == 13 and s["map"]["w"] == L["n"] and L["runs"] == 4
    assert len(E.BANDS["adventure"]) > 1.5 * len(E.BANDS["hardcore"])
    camps = [o for o in s["map"]["objects"] if o["kind"] == "camp"]
    assert len(camps) == 30 and {o["level"] for o in camps} == {1, 2, 3, 4}
    me = E.MODES["adventure"]["me"]
    far = lambda o: abs(o["x"] - me[0]) + abs(o["y"] - me[1])  # noqa: E731
    lairs = [o for o in camps if o["level"] == 4]
    assert all(o["style"] == "lost" and set(o["lost"]) <= set(E.LOST_UNITS) for o in lairs)
    assert min(far(o) for o in lairs) > max(far(o) for o in camps if o["level"] == 1)
    foes = E.camp_foes(s, lairs[0])
    assert [f["unit"] for f in foes] == lairs[0]["lost"]
    # No rival walks the map; the lost units never come in packs.
    bot = dict(s["bot"])
    E.end_day(s)
    assert (s["bot"]["x"], s["bot"]["y"]) == (bot["x"], bot["y"]) and s["bot"]["gain_pct"] == 0
    assert not any(c in E.LOST_UNITS + [E.BOSS] for t in range(1, 6) for c in E.creature_pool(t))


def test_adventure_rest_heals_the_army_every_night():
    s = _adventure("rest")
    st = s["army"][0]
    st["count"] = st["max_count"] // 2
    st["own"] = st["count"]
    s["fallen"] = {st["unit"]: st["max_count"] - st["count"]}
    before = st["count"]
    E.end_day(s)
    assert st["count"] == min(st["max_count"], before + max(1, st["max_count"] * E.SOLO_REST_PCT // 100))


def test_the_final_boss_is_faceless_alone_and_hypnotises():
    s = _adventure("boss")
    E._start_final(s)
    b = s["battle"]
    foes = [u for u in b["units"] if E._home(u) == "foe"]
    assert len(foes) == 1 and foes[0]["unit"] == E.BOSS and foes[0]["count"] == 1 and b["foe_name"] == "Безликий"
    hyp = [e for e in b["events"] if e["kind"] == "hypno"]
    assert hyp  # round 1: the strongest stack fights for him
    t = E.bunit(s, hyp[0]["target"])
    assert t.get("orig_side") == "me" and t["side"] == "foe"
    E.set_auto(s)
    # When the battle ends the hypnotised are back home and count as the player's.
    assert all("orig_side" not in u and u["id"].startswith("m") == (u["side"] == "me") for u in s["battle"]["units"])
    assert any(e["kind"] == "hypno_end" for e in s["battle"]["events"])


def test_the_hook_pulls_an_enemy_and_strikes_without_an_answer():
    s = _run("hook")
    foe = E.make_stack("e1", "lost_hook", 3)
    E._start_battle(s, "camp", [foe], obj_id=None, foe_name="T", foe_hero=None)
    b = s["battle"]
    b["rocks"] = []
    hook = E.bunit(s, "e1")
    me = next(u for u in b["units"] if u["side"] == "me")
    for u in b["units"]:
        if u is not me and u is not hook:
            u["x"], u["y"] = 0, 9 - int(u["id"][1:])
    hook["x"], hook["y"], me["x"], me["y"] = 6, 5, 3, 5
    hp = me["count"]
    b["turn_of"] = hook["id"]
    E._ai_turn(s, hook)
    assert E._dist(hook, me["x"], me["y"]) == 1 and me["count"] < hp
    assert any(e["kind"] == "hook" for e in b["events"]) and not any(e["kind"] == "retaliate" for e in b["events"][-3:])


def _walk_onto(s, obj):
    """Put the hero next to `obj` with plenty of moves and step onto it."""
    s["phase"], s["battle"], s["pending"] = "map", None, None
    s["seen"] = [(1 << s["map"]["w"]) - 1] * s["map"]["h"]
    stand = next((nx, ny) for nx, ny in ((obj["x"] + 1, obj["y"]), (obj["x"] - 1, obj["y"]), (obj["x"], obj["y"] + 1),
                                         (obj["x"], obj["y"] - 1))
                 if E.inside(s, nx, ny) and (nx, ny) not in E._blocked(s) and E._object_at(s, nx, ny) is None)
    s["hero"]["x"], s["hero"]["y"] = stand
    s["hero"]["moves"] = 20
    E.move_hero(s, obj["x"], obj["y"])


def test_adventure_has_all_five_buildings_and_tunnels_pair_up():
    s = _adventure("bld")
    objs = s["map"]["objects"]
    kinds = {k: [o for o in objs if o["kind"] == k] for k in ("training", "floodtower", "medic", "tunnel", "shrine")}
    assert {k: len(v) for k, v in kinds.items()} == {"training": 6, "floodtower": 6, "medic": 4, "tunnel": 4, "shrine": 4}
    by_id = {o["id"]: o for o in objs}
    for t in kinds["tunnel"]:
        assert by_id[t["to"]]["to"] == t["id"] and t["to"] != t["id"]


def test_training_floodtower_and_shrine_work_once():
    s = _adventure("bld2")
    objs = s["map"]["objects"]
    tr = next(o for o in objs if o["kind"] == "training")
    _walk_onto(s, tr)
    assert s["hero"]["perk_atk"] == E.TRAINING_PCT and tr["taken_by"] == "me"
    sh = next(o for o in objs if o["kind"] == "shrine")
    _walk_onto(s, sh)
    assert s["hero"]["ward"] == 1 and "В ближайшем логове" in s["notice"]["text"]
    ft = next(o for o in objs if o["kind"] == "floodtower")
    s["seen"] = [0] * s["map"]["h"]
    E.reveal(s, ft["x"] + 1, ft["y"], 1)
    s["seen"][ft["y"]] |= 1 << ft["x"]
    s["hero"]["x"], s["hero"]["y"], s["hero"]["moves"] = ft["x"] + 1, ft["y"], 5
    E.move_hero(s, ft["x"], ft["y"])
    far = (ft["x"], max(0, ft["y"] - E.FLOODTOWER_SIGHT + 2))
    assert E.is_seen(s, *far)


def test_the_medic_heals_everyone_then_rests_five_days():
    s = _adventure("medic")
    md = next(o for o in s["map"]["objects"] if o["kind"] == "medic")
    s["army"][0]["count"] = 1
    _walk_onto(s, md)
    assert s["army"][0]["count"] == s["army"][0]["max_count"]
    assert md["ready_day"] == s["day"] + E.MEDIC_EVERY and E._object_at(s, md["x"], md["y"]) is md
    s["army"][0]["count"] = 1
    _walk_onto(s, md)
    assert s["army"][0]["count"] == 1 and "отдыхают" in s["notice"]["text"]


def test_the_tunnel_takes_the_hero_to_its_other_end():
    s = _adventure("tunnel")
    t = next(o for o in s["map"]["objects"] if o["kind"] == "tunnel")
    other = next(o for o in s["map"]["objects"] if o["id"] == t["to"])
    _walk_onto(s, t)
    assert (s["hero"]["x"], s["hero"]["y"]) == (other["x"], other["y"])
    assert s["notice"]["kind"] == "tunnel"


def test_a_lost_lair_fights_on_its_own_pitch_and_the_shrine_ward_stops_hypnosis():
    s = _adventure("lairpitch")
    lair = next(o for o in s["map"]["objects"] if o.get("style") == "lost")
    E._start_camp(s, lair)
    assert s["battle"]["pitch"] == "lair"
    assert all(k in E.BATTLE_OBSTACLES + E.LAIR_OBSTACLES for _, _, k in s["battle"]["rocks"])
    s2 = _adventure("ward")
    s2["hero"]["ward"] = 1
    E._start_final(s2)
    b = s2["battle"]
    assert b["pitch"] == "lair"
    assert any(e["kind"] == "ward" for e in b["events"])
    first = [e["kind"] for e in b["events"] if e["kind"] in ("ward", "hypno")]
    assert first[0] == "ward" and s2["hero"]["ward"] == 0


def test_the_lost_are_of_different_levels_and_a_lair_shows_them():
    tiers = {c: E.UNITS[c]["tier"] for c in E.LOST_UNITS}
    assert sorted(set(tiers.values())) == [2, 3, 4] and E.UNITS[E.BOSS]["tier"] == 5
    s = _adventure()
    lair = next(o for o in s["map"]["objects"] if o.get("style") == "lost")
    assert lair["tiers"] == [tiers[c] for c in lair["lost"]]
    # The lair's power is split evenly: a low level comes in a bigger crowd.
    foes = E.camp_foes(s, lair)
    by_tier = sorted(foes, key=lambda f: E.UNITS[f["unit"]]["tier"])
    assert by_tier[0]["count"] >= by_tier[-1]["count"]
