"""Balance simulation for «Карьера тренера» tactics (career_tactics_service):
runs DB-free career matches through the same phase-by-phase controller the
season uses (tournament_match_engine.simulate_match_controlled) and reports

  1. the playstyle x playstyle win table at equal strength (flat squads,
     4-3-3, BALANCED) — written to app/services/career_style_matchup.json
     with --write (the scouting hint / adaptive bots read it, and
     tests/test_career_tactics.py checks it is current and agrees with
     career_tactics_service.COUNTERS);
  2. "counter gain": win % of a counter-style minus the mirror match, per
     countered style and on average (target ~ +8..12 p.p.);
  3. win % by rating gap -> p.p. per rating point;
  4. what familiarity and a match plan are worth, in rating points
     (target: the full plan ~ 5-7 points, nowhere near 20).

Every coefficient comes from GameConfig's column defaults; --counter and
--fam-max override the two main knobs for tuning, --before switches the
whole tactics layer off (no counters, familiarity or plan) for comparison.

Usage (from backend/):
    python scripts/simulate_career_tactics.py --n 1000
    python scripts/simulate_career_tactics.py --n 3000 --write
"""
import argparse
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
from app.services.club_tactical_matchup_service import PLAYSTYLES

STYLES = list(PLAYSTYLES)
BENCH_POSITIONS = (Position.GK, Position.CB, Position.CM, Position.ST, Position.RW)
STANDARD_PLAN = {
    "rules": [
        {"score": "behind", "margin": 1, "from_minute": 60, "mentality": "ATTACKING", "playstyle": None},
        {"score": "ahead", "margin": 2, "from_minute": 70, "mentality": "DEFENSIVE", "playstyle": None},
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
        display_name=f"P{n}", position=position, rating=rating, rarity=Rarity.common, attack_rating=None, defense_rating=None,
        club=f"Club {n}", country=f"Country {n}",
    ))


def runner(label: str, rating: int, playstyle: str, config, *, familiarity: int = 0, plan=None,
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
    return tactics.CareerSideRunner(label, label, formation, mentality, playstyle, on_pitch, bench, config,
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


def style_table(n, config, seed, rating=80):
    table = {}
    for i, a in enumerate(STYLES):
        table[a] = {}
        for j, b in enumerate(STYLES):
            table[a][b] = play(n, config, {"rating": rating, "playstyle": a}, {"rating": rating, "playstyle": b},
                               seed + i * 10 + j)
    return table


def counter_gain(table) -> tuple[float, dict]:
    per_style = {}
    gains = []
    for target in STYLES:
        mirror = table[target][target]["win"]
        row = {c: round(table[c][target]["win"] - mirror, 1) for c in tactics.counters_of(target)}
        per_style[target] = row
        gains.extend(row.values())
    return round(sum(gains) / len(gains), 1), per_style


def gap_sweep(n, config, seed, base=75, gaps=(0, 2, 4, 6, 8, 10, 20)):
    out = {}
    for g in gaps:
        out[g] = play(n, config, {"rating": base + g, "playstyle": "CENTRAL_PLAY"},
                      {"rating": base, "playstyle": "CENTRAL_PLAY"}, seed + g)
    slope = (out[10]["win"] - out[0]["win"]) / 10
    return out, round(slope, 2)


def plan_value(n, config, seed, slope, base=75, fatigue=40):
    fam = int(config.career_familiarity_max_tenths)
    scenarios = {
        "nothing": {},
        "familiarity": {"familiarity": fam},
        "plan": {"plan": STANDARD_PLAN},
        "full": {"familiarity": fam, "plan": STANDARD_PLAN},
    }
    out = {}
    for k, (name, extra) in enumerate(scenarios.items()):
        res = play(n, config, {"rating": base, "playstyle": "CENTRAL_PLAY", "fatigue": fatigue, **extra},
                   {"rating": base, "playstyle": "CENTRAL_PLAY", "fatigue": fatigue}, seed + 100 + k)
        out[name] = res
    for name in scenarios:
        gain = out[name]["win"] - out["nothing"]["win"]
        out[name]["gain_pp"] = round(gain, 1)
        out[name]["rating_points"] = round(gain / slope, 1) if slope else None
    # The full plan against a squad 20 points stronger: should still lose most.
    out["full_vs_plus20"] = play(n, config, {"rating": base, "playstyle": "CENTRAL_PLAY", "fatigue": fatigue,
                                             "familiarity": fam, "plan": STANDARD_PLAN},
                                 {"rating": base + 20, "playstyle": "CENTRAL_PLAY", "fatigue": fatigue}, seed + 200)
    out["nothing_vs_plus20"] = play(n, config, {"rating": base, "playstyle": "CENTRAL_PLAY", "fatigue": fatigue},
                                    {"rating": base + 20, "playstyle": "CENTRAL_PLAY", "fatigue": fatigue}, seed + 201)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261012)
    parser.add_argument("--counter", type=int, default=None, help="career_style_counter_permille override")
    parser.add_argument("--fam-max", type=int, default=None, help="career_familiarity_max_tenths override")
    parser.add_argument("--before", action="store_true", help="tactics layer off (no counters/familiarity/plan)")
    parser.add_argument("--skip-plan", action="store_true")
    parser.add_argument("--write", action="store_true", help="write app/services/career_style_matchup.json")
    parser.add_argument("--json", default=None, help="also dump the full report here")
    args = parser.parse_args()

    overrides = {}
    if args.counter is not None:
        overrides["career_style_counter_permille"] = args.counter
    if args.fam_max is not None:
        overrides["career_familiarity_max_tenths"] = args.fam_max
    if args.before:
        overrides.update(career_style_counter_permille=0, career_familiarity_max_tenths=0)
    config = default_config(**overrides)

    t0 = time.time()
    table = style_table(args.n, config, args.seed)
    gain, per_style = counter_gain(table)
    gaps, slope = gap_sweep(args.n, config, args.seed + 1000)
    report = {"counter_permille": config.career_style_counter_permille, "n": args.n, "table": table,
              "counter_gain_pp": gain, "counter_gain_by_style": per_style, "gaps": gaps, "pp_per_rating_point": slope}
    if not args.skip_plan and not args.before:
        report["plan"] = plan_value(args.n, config, args.seed + 2000, slope)

    print(f"counter_permille={config.career_style_counter_permille} familiarity_max={config.career_familiarity_max_tenths / 10}% "
          f"n={args.n} ({time.time() - t0:.0f}s)")
    print("Win/loss % (row vs column):")
    print(" " * 16 + "".join(f"{s[:12]:>14}" for s in STYLES))
    for a in STYLES:
        print(f"{a[:14]:16}" + "".join(f"{table[a][b]['win']:>7.1f}/{table[a][b]['loss']:<6.1f}" for b in STYLES))
    print(f"Counter gain vs mirror, avg: {gain:+.1f} p.p.")
    for target, row in per_style.items():
        print(f"  vs {target:15} " + ", ".join(f"{c} {v:+.1f}" for c, v in row.items()))
    print("Rating gap -> win/draw/loss %:")
    for g, r in gaps.items():
        print(f"  +{g:<3} {r['win']:5.1f} / {r['draw']:4.1f} / {r['loss']:5.1f}")
    print(f"  ≈ {slope} p.p. win per rating point (0..10)")
    if "plan" in report:
        print("Plan value (equal squads, pre-match fatigue 40):")
        for name, r in report["plan"].items():
            extra = f"  gain {r['gain_pp']:+.1f} p.p. ≈ {r['rating_points']} rating pts" if "gain_pp" in r else ""
            print(f"  {name:18} {r['win']:5.1f} / {r['draw']:4.1f} / {r['loss']:5.1f}{extra}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    if args.write:
        if args.before or args.counter is not None or args.fam_max is not None:
            sys.exit("--write only with the GameConfig defaults (no --before/--counter/--fam-max)")
        payload = {
            "generated": date.today().isoformat(),
            "generator": "scripts/simulate_career_tactics.py",
            "fingerprint": tactics.engine_fingerprint(config.career_style_counter_permille),
            "counter_permille": config.career_style_counter_permille,
            "n": args.n, "seed": args.seed, "rating": 80,
            "pp_per_rating_point": slope, "counter_gain_pp": gain,
            "table": table,
        }
        with open(tactics.MATRIX_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(f"Written {tactics.MATRIX_PATH}")


if __name__ == "__main__":
    main()
