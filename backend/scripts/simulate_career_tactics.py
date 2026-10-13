"""Balance simulation for «Карьера тренера» tactics (career_tactics_service):
DB-free career matches through the same phase-by-phase controller a season
uses (tournament_match_engine.simulate_match_controlled). Reports

  1. presets: the 5x5 win table at equal strength (flat 80 squads, 4-3-3,
     BALANCED), and the best answer to each preset vs the mirror
     (target ~ +8..12 p.p. win);
  2. interactions: each INTERACTIONS entry measured in isolation — the same
     matchup with that interaction's strength zeroed vs as configured; the
     sign must match the table (tests/test_career_tactics.py checks the
     stored result);
  3. all 108 axis combinations against the five presets: average win %,
     best / worst — no combination should dominate;
  4. win % by rating gap -> p.p. per rating point;
  5. familiarity + match plan, in rating points (target ~5-7, not 20).

--write stores 1, 2 and 4 in app/services/career_tactics_matchup.json with
the engine fingerprint. Coefficients come from GameConfig defaults
(career_tactics_tuning on top of DEFAULT_TUNING); --tuning '{"shift": {...}}'
overrides for experiments.

Usage (from backend/):
    python scripts/simulate_career_tactics.py --n 600
    python scripts/simulate_career_tactics.py --n 1500 --write
"""
import argparse
import copy
import itertools
import json
import random
import sys
import time
from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

from app.models.enums import Position, Rarity
from app.models.game_config import GameConfig
from app.services import career_tactics_service as tactics
from app.services import tournament_match_engine as engine
from app.services.club_formation_service import get_formation_slots

PRESETS = list(tactics.PRESETS)
BENCH_POSITIONS = (Position.GK, Position.CB, Position.LB, Position.CM, Position.CDM, Position.ST, Position.RW)
STANDARD_PLAN = {
    "rules": [
        {"score": "behind", "margin": 1, "from_minute": 60, "mentality": "ATTACKING", "tactic": {}},
        {"score": "ahead", "margin": 2, "from_minute": 75, "mentality": "DEFENSIVE", "tactic": {}},
    ],
    "subs": [
        {"minute": 60, "slot": None, "card_id": None, "min_fatigue": 60},
        {"minute": 70, "slot": None, "card_id": None, "min_fatigue": 60},
        {"minute": 80, "slot": None, "card_id": None, "min_fatigue": 55},
    ],
}


def default_config(**overrides) -> SimpleNamespace:
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


def _card(n: int, position: Position, rating: int) -> _Card:
    return _Card(id=n, player_id=n, player=SimpleNamespace(
        display_name=f"P{n}", position=position, rating=rating, rarity=Rarity.common, attack_rating=None,
        defense_rating=None, club=f"Club {n}", country=f"Country {n}",
    ))


def runner(label: str, rating: int, tactic: dict, config, *, familiarity: int = 0, plan=None,
           fatigue: int = 0, mentality: str = "BALANCED", formation: str = "4-3-3", offset: int = 0):
    on_pitch = [
        tactics.LivePlayer(card=_card(offset + i, slot.ideal_position, rating), base_rating=rating,
                           pre_fatigue=fatigue, slot=slot)
        for i, slot in enumerate(get_formation_slots(formation))
    ]
    bench = [
        tactics.LivePlayer(card=_card(offset + 50 + i, pos, rating - 3), base_rating=rating - 3, pre_fatigue=10)
        for i, pos in enumerate(BENCH_POSITIONS)
    ] if plan else []
    return tactics.CareerSideRunner(label, label, formation, mentality, tactic, on_pitch, bench, config,
                                    familiarity=familiarity, plan=plan)


def play(n: int, config, a_kwargs: dict, b_kwargs: dict, seed: int) -> dict:
    random.seed(seed)
    w = d = lose = 0
    for _ in range(n):
        a = runner("a", config=config, offset=0, **a_kwargs)
        b = runner("b", config=config, offset=1000, **b_kwargs)
        r = engine.simulate_match_controlled(tactics.CareerMatchController(a, b), config)
        if r.score_a > r.score_b:
            w += 1
        elif r.score_a < r.score_b:
            lose += 1
        else:
            d += 1
    return {"win": round(100 * w / n, 1), "draw": round(100 * d / n, 1), "loss": round(100 * lose / n, 1)}


def preset_table(n, config, seed, rating=80):
    table = {}
    for i, a in enumerate(PRESETS):
        table[a] = {}
        for j, b in enumerate(PRESETS):
            table[a][b] = play(n, config, {"rating": rating, "tactic": tactics.PRESETS[a]},
                               {"rating": rating, "tactic": tactics.PRESETS[b]}, seed + i * 10 + j)
    return table


def best_answers(table) -> tuple[float, dict]:
    out = {}
    for target in PRESETS:
        mirror = table[target][target]["win"]
        best = max(PRESETS, key=lambda p: table[p][target]["win"])
        out[target] = {"best": best, "gain_pp": round(table[best][target]["win"] - mirror, 1)}
    avg = round(sum(v["gain_pp"] for v in out.values()) / len(out), 1)
    return avg, out


def interaction_effects(n, config, seed, rating=80):
    """Each interaction in isolation: attacker-condition side vs
    defender-condition side (both otherwise neutral, the zone forced by the
    attack direction where the interaction needs one); effect = win % of the
    favoured side with the interaction on minus with its strength at 0."""
    out = {}
    tuning = tactics.tuning_of(config)
    for k, ix in enumerate(tactics.INTERACTIONS):
        att = {**tactics.NEUTRAL_TACTIC, **ix["att"]}
        if ix.get("zone") == "wing_attack":
            att["direction"] = "wings"
        elif ix.get("zone") == "central_attack":
            att["direction"] = "center"
        dfn = {**tactics.NEUTRAL_TACTIC, **ix["def"]}
        off = copy.deepcopy(tuning)
        off["shift"][ix["id"]] = 0.0
        on_cfg = SimpleNamespace(**{**vars(config), "career_tactics_tuning": tuning})
        off_cfg = SimpleNamespace(**{**vars(config), "career_tactics_tuning": off})
        args = ({"rating": rating, "tactic": att}, {"rating": rating, "tactic": dfn})
        with_ix = play(n, on_cfg, *args, seed + 500 + k)
        without = play(n, off_cfg, *args, seed + 500 + k)
        delta = with_ix["win"] - without["win"]
        out[ix["id"]] = {"sign": ix["sign"], "attacker_win_delta_pp": round(delta, 1),
                         "favoured_delta_pp": round(delta * ix["sign"], 1)}
    return out


def combination_sweep(n, config, seed, rating=80):
    combos = [dict(zip(tactics.AXES, values)) for values in itertools.product(*tactics.AXES.values())]
    results = []
    for i, tactic in enumerate(combos):
        wins = [play(n, config, {"rating": rating, "tactic": tactic},
                     {"rating": rating, "tactic": tactics.PRESETS[p]}, seed + i * 7 + j)["win"]
                for j, p in enumerate(PRESETS)]
        results.append((round(sum(wins) / len(wins), 1), tactics.describe(tactic)))
    results.sort(reverse=True)
    avg = sum(r[0] for r in results) / len(results)
    return {"combinations": len(results), "average_win": round(avg, 1), "best": results[:5], "worst": results[-5:]}


def gap_sweep(n, config, seed, base=75, gaps=(0, 2, 4, 6, 8, 10, 20)):
    out = {}
    neutral = tactics.NEUTRAL_TACTIC
    for g in gaps:
        out[g] = play(n, config, {"rating": base + g, "tactic": neutral}, {"rating": base, "tactic": neutral}, seed + g)
    slope = (out[10]["win"] - out[0]["win"]) / 10
    return out, round(slope, 2)


def plan_value(n, config, seed, slope, base=75, fatigue=40):
    fam = int(config.career_familiarity_max_tenths)
    neutral = tactics.NEUTRAL_TACTIC
    scenarios = {"nothing": {}, "familiarity": {"familiarity": fam}, "plan": {"plan": STANDARD_PLAN},
                 "full": {"familiarity": fam, "plan": STANDARD_PLAN}}
    out = {}
    for k, (name, extra) in enumerate(scenarios.items()):
        out[name] = play(n, config, {"rating": base, "tactic": neutral, "fatigue": fatigue, **extra},
                         {"rating": base, "tactic": neutral, "fatigue": fatigue}, seed + 100 + k)
    for name in scenarios:
        gain = out[name]["win"] - out["nothing"]["win"]
        out[name]["gain_pp"] = round(gain, 1)
        out[name]["rating_points"] = round(gain / slope, 1) if slope else None
    out["full_vs_plus20"] = play(n, config, {"rating": base, "tactic": neutral, "fatigue": fatigue,
                                             "familiarity": fam, "plan": STANDARD_PLAN},
                                 {"rating": base + 20, "tactic": neutral, "fatigue": fatigue}, seed + 200)
    out["nothing_vs_plus20"] = play(n, config, {"rating": base, "tactic": neutral, "fatigue": fatigue},
                                    {"rating": base + 20, "tactic": neutral, "fatigue": fatigue}, seed + 201)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=600)
    parser.add_argument("--seed", type=int, default=20261013)
    parser.add_argument("--tuning", default=None, help="JSON overrides on top of the default tuning")
    parser.add_argument("--only", default="presets,interactions,combos,gaps,plan")
    parser.add_argument("--combo-n", type=int, default=None, help="matches per combination pairing (default n/4)")
    parser.add_argument("--write", action="store_true", help="write app/services/career_tactics_matchup.json")
    parser.add_argument("--json", default=None)
    args = parser.parse_args()
    only = set(args.only.split(","))

    overrides = {}
    if args.tuning:
        overrides["career_tactics_tuning"] = json.loads(args.tuning)
    config = default_config(**overrides)
    report: dict = {"n": args.n}
    t0 = time.time()

    if "presets" in only:
        table = preset_table(args.n, config, args.seed)
        gain, answers = best_answers(table)
        report.update(presets=table, best_answer_gain_pp=gain, best_answers=answers)
        print("Presets, win/loss % (row vs column):")
        print(" " * 16 + "".join(f"{p[:12]:>14}" for p in PRESETS))
        for a in PRESETS:
            print(f"{a[:14]:16}" + "".join(f"{table[a][b]['win']:>7.1f}/{table[a][b]['loss']:<6.1f}" for b in PRESETS))
        print(f"Best answer vs mirror, avg: {gain:+.1f} p.p.")
        for target, v in answers.items():
            print(f"  vs {target:15} {v['best']:15} {v['gain_pp']:+.1f}")
    if "interactions" in only:
        effects = interaction_effects(args.n, config, args.seed)
        report["interactions"] = effects
        print("Interactions in isolation (win % change for the favoured side):")
        for ix_id, e in effects.items():
            print(f"  {ix_id:24} {e['favoured_delta_pp']:+.1f}")
    if "combos" in only:
        sweep = combination_sweep(args.combo_n or max(50, args.n // 4), config, args.seed + 3000)
        report["combinations"] = sweep
        print(f"All {sweep['combinations']} axis combinations vs the presets: average {sweep['average_win']}% win")
        for label, rows in (("best", sweep["best"]), ("worst", sweep["worst"])):
            for win, desc in rows:
                print(f"  {label:5} {win:5.1f}  {desc}")
    if "gaps" in only:
        gaps, slope = gap_sweep(args.n, config, args.seed + 1000)
        report.update(gaps=gaps, pp_per_rating_point=slope)
        print("Rating gap -> win/draw/loss %:")
        for g, r in gaps.items():
            print(f"  +{g:<3} {r['win']:5.1f} / {r['draw']:4.1f} / {r['loss']:5.1f}")
        print(f"  ≈ {slope} p.p. win per rating point (0..10)")
        if "plan" in only:
            report["plan"] = plan_value(args.n, config, args.seed + 2000, slope)
            print("Plan value (equal squads, pre-match fatigue 40):")
            for name, r in report["plan"].items():
                extra = f"  gain {r['gain_pp']:+.1f} p.p. ≈ {r['rating_points']} rating pts" if "gain_pp" in r else ""
                print(f"  {name:18} {r['win']:5.1f} / {r['draw']:4.1f} / {r['loss']:5.1f}{extra}")
    print(f"({time.time() - t0:.0f}s)")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    if args.write:
        if args.tuning or not {"presets", "interactions", "gaps"} <= only:
            sys.exit("--write needs the defaults and presets,interactions,gaps")
        payload = {
            "generated": date.today().isoformat(), "generator": "scripts/simulate_career_tactics.py",
            "fingerprint": tactics.engine_fingerprint(), "n": args.n, "seed": args.seed, "rating": 80,
            "pp_per_rating_point": report["pp_per_rating_point"],
            "best_answer_gain_pp": report["best_answer_gain_pp"], "best_answers": report["best_answers"],
            "presets": report["presets"], "interactions": report["interactions"],
        }
        with open(tactics.MATRIX_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(f"Written {tactics.MATRIX_PATH}")


if __name__ == "__main__":
    main()
