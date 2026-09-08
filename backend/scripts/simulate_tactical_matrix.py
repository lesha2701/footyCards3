"""Large-scale matchup-matrix simulation for the club tactical match engine,
run on top of the production defaults set by the 2026-09-07 problem-1-4 fix
(see docs/superpowers/plans/2026-08-30-club-tactical-match-engine-phase1-STATUS.md).

Unlike simulate_tactical_balance.py (targeted diagnostic scenarios, one
metric per problem), this script runs full head-to-head match grids —
mentality x mentality, playstyle x playstyle, formation x formation — plus
strength-gap and tactical-alignment scenarios, each pairing repeated
hundreds of times (never a single match) so no conclusion rests on one
simulated result.

Usage (from backend/, inside the docker container):
    python scripts/simulate_tactical_matrix.py --out /tmp/matrix_results.json

Prints progress to stderr, writes the full structured results to --out as
JSON (used to build the report), and prints a short summary to stdout.
"""
import argparse
import json
import statistics
import sys
import time

from app.models.coach import Coach, CoachBoost
from app.models.enums import CoachBoostType, Position, Rarity
from scripts.simulate_tactical_balance import _Config, lineup_dicts, squad
from app.services import club_tactical_matchup_service as matchup
from app.services import tournament_match_engine as engine

MENTALITIES = matchup.MENTALITIES
PLAYSTYLES = matchup.PLAYSTYLES
FORMATIONS = ("4-3-3", "4-4-2", "3-5-2", "5-3-2")


def play_n_matches(
    mentality_a, playstyle_a, ratings_a, mentality_b, playstyle_b, ratings_b, n,
    formation_a="4-3-3", formation_b="4-3-3", default_a=80, default_b=80,
    coach_a=None, coach_b=None,
):
    wins_a = wins_b = draws = 0
    goals_a = []
    goals_b = []
    for _ in range(n):
        cards_a = squad(ratings_a, default=default_a, formation=formation_a)
        cards_b = squad(ratings_b, default=default_b, formation=formation_b)
        side_a = matchup.build_side(cards_a, mentality_a, playstyle_a, coach=coach_a)
        side_b = matchup.build_side(cards_b, mentality_b, playstyle_b, coach=coach_b)
        r = engine.simulate_match(side_a, side_b, lineup_dicts(cards_a), lineup_dicts(cards_b), _Config())
        goals_a.append(r.score_a)
        goals_b.append(r.score_b)
        if r.score_a > r.score_b:
            wins_a += 1
        elif r.score_b > r.score_a:
            wins_b += 1
        else:
            draws += 1
    gf_a = statistics.mean(goals_a)
    gf_b = statistics.mean(goals_b)
    return {
        "n": n,
        "win_a": round(wins_a / n, 4), "draw": round(draws / n, 4), "win_b": round(wins_b / n, 4),
        "gf_a": round(gf_a, 3), "gf_b": round(gf_b, 3), "gd_a": round(gf_a - gf_b, 3),
    }


def _progress(label, done, total, t0):
    elapsed = time.time() - t0
    print(f"  [{done}/{total}] {label} ({elapsed:.1f}s elapsed)", file=sys.stderr)


# --- 1. Mentality x Mentality (equal flat-80 squads, 4-3-3, CENTRAL_PLAY both) ---
def mentality_grid(n=250):
    ratings = {pos: 80 for pos in Position}
    out = {}
    pairs = [(a, b) for a in MENTALITIES for b in MENTALITIES]
    t0 = time.time()
    for i, (ma, mb) in enumerate(pairs, 1):
        out[f"{ma}__vs__{mb}"] = play_n_matches(ma, "CENTRAL_PLAY", ratings, mb, "CENTRAL_PLAY", ratings, n)
        _progress(f"mentality {ma} vs {mb}", i, len(pairs), t0)
    return out


# --- 1b. Mentality x Mentality across several DIFFERENT (formation, style)
# contexts, not just one fixed combo — averaged, so the verdict isn't an
# artifact of one specific formation/style pairing. ---
MENTALITY_TEST_CONTEXTS = [
    ("4-3-3", "CENTRAL_PLAY"), ("4-4-2", "WING_PLAY"), ("3-5-2", "POSSESSION"),
    ("5-3-2", "COUNTER_ATTACK"), ("4-3-3", "HIGH_PRESS"),
]


def mentality_grid_multi_context(n=250, contexts=MENTALITY_TEST_CONTEXTS):
    ratings = {pos: 80 for pos in Position}
    per_context = {}
    t0 = time.time()
    for ci, (formation, style) in enumerate(contexts, 1):
        grid = {}
        for ma in MENTALITIES:
            for mb in MENTALITIES:
                grid[f"{ma}__vs__{mb}"] = play_n_matches(
                    ma, style, ratings, mb, style, ratings, n, formation_a=formation, formation_b=formation,
                )
        per_context[f"{formation}_{style}"] = grid
        _progress(f"mentality context {formation}/{style}", ci, len(contexts), t0)

    averaged = {}
    for ma in MENTALITIES:
        for mb in MENTALITIES:
            key = f"{ma}__vs__{mb}"
            win_a = statistics.mean(per_context[c][key]["win_a"] for c in per_context)
            win_b = statistics.mean(per_context[c][key]["win_b"] for c in per_context)
            averaged[key] = {"win_a": round(win_a, 4), "win_b": round(win_b, 4)}
    return {"per_context": per_context, "averaged": averaged}


# --- 2. Playstyle x Playstyle (equal flat-80 squads, 4-3-3, BALANCED both) ---
def playstyle_grid(n=200):
    ratings = {pos: 80 for pos in Position}
    out = {}
    pairs = [(a, b) for a in PLAYSTYLES for b in PLAYSTYLES]
    t0 = time.time()
    for i, (pa, pb) in enumerate(pairs, 1):
        out[f"{pa}__vs__{pb}"] = play_n_matches("BALANCED", pa, ratings, "BALANCED", pb, ratings, n)
        _progress(f"playstyle {pa} vs {pb}", i, len(pairs), t0)
    return out


# --- 2b. Playstyle x Playstyle with squads ALIGNED to their own playstyle
# (each squad's rated positions match what that style actually uses) — a
# fairer rock-paper-scissors test than flat-rated squads playing arbitrary
# styles, per explicit user request ("test each style accounting for it
# actually suiting the squad"). ---
PLAYSTYLE_ARCHETYPES: dict[str, dict[Position, int]] = {
    "WING_PLAY": {Position.LW: 92, Position.RW: 92, Position.LB: 90, Position.RB: 90},
    "CENTRAL_PLAY": {Position.ST: 92, Position.CAM: 92, Position.CM: 90},
    "POSSESSION": {Position.CDM: 92, Position.CM: 93, Position.CAM: 91},
    "HIGH_PRESS": {Position.CDM: 90, Position.CM: 90, Position.LB: 91, Position.RB: 91},
    "COUNTER_ATTACK": {Position.ST: 93, Position.LW: 91, Position.RW: 91},
}


def playstyle_aligned_grid(n=350):
    out = {}
    pairs = [(a, b) for a in PLAYSTYLES for b in PLAYSTYLES]
    t0 = time.time()
    for i, (pa, pb) in enumerate(pairs, 1):
        out[f"{pa}__vs__{pb}"] = play_n_matches(
            "BALANCED", pa, PLAYSTYLE_ARCHETYPES[pa], "BALANCED", pb, PLAYSTYLE_ARCHETYPES[pb], n,
        )
        _progress(f"aligned playstyle {pa} vs {pb}", i, len(pairs), t0)
    return out


# --- 3. Formation x Formation (equal flat-80 squads, BALANCED/CENTRAL_PLAY both) ---
def formation_grid(n=200):
    ratings = {pos: 80 for pos in Position}
    out = {}
    pairs = [(a, b) for a in FORMATIONS for b in FORMATIONS]
    t0 = time.time()
    for i, (fa, fb) in enumerate(pairs, 1):
        out[f"{fa}__vs__{fb}"] = play_n_matches(
            "BALANCED", "CENTRAL_PLAY", ratings, "BALANCED", "CENTRAL_PLAY", ratings, n,
            formation_a=fa, formation_b=fb,
        )
        _progress(f"formation {fa} vs {fb}", i, len(pairs), t0)
    return out


# --- 4. Strength-gap sweep (neutral BALANCED/CENTRAL_PLAY/4-3-3 both sides) ---
def strength_gap_sweep(n=400):
    gaps = [0, 5, 10, 15, 20, 25, 30]
    out = {}
    t0 = time.time()
    for i, gap in enumerate(gaps, 1):
        ratings_a = {pos: 90 for pos in Position}
        ratings_b = {pos: 90 - gap for pos in Position}
        out[f"gap_{gap}"] = play_n_matches(
            "BALANCED", "CENTRAL_PLAY", ratings_a, "BALANCED", "CENTRAL_PLAY", ratings_b, n,
        )
        _progress(f"strength gap {gap}", i, len(gaps), t0)
    return out


# --- 5. Tactically-aligned vs tactically-mismatched: SAME squad shape and
# SAME average rating, only the tactic choice differs --------------------
def tactical_alignment_scenarios(n=350):
    out = {}
    t0 = time.time()

    # Flank-stacked squad: strong on the wings, average everywhere else.
    # Aligned tactic = WING_PLAY (plays to its actual strength).
    # Mismatched tactic = CENTRAL_PLAY (its central positions are only
    # average — nothing about this squad's shape supports central play).
    flank_squad = {Position.LW: 90, Position.RW: 90, Position.LB: 88, Position.RB: 88}
    out["flank_squad__aligned_wing__vs__mismatched_central"] = play_n_matches(
        "BALANCED", "WING_PLAY", flank_squad, "BALANCED", "CENTRAL_PLAY", flank_squad, n,
    )

    # Defence-heavy squad: strong back line, average attack. Aligned tactic
    # = PARK_THE_BUS (plays to its real defensive strength, per spec §9's
    # mentality_fit — defence well above attack). Mismatched = ATTACKING
    # (commits an average attack forward while thinning its one real asset).
    defence_squad = {Position.CB: 90, Position.LB: 88, Position.RB: 88}
    out["defence_squad__aligned_bus__vs__mismatched_attacking"] = play_n_matches(
        "PARK_THE_BUS", "CENTRAL_PLAY", defence_squad, "ATTACKING", "CENTRAL_PLAY", defence_squad, n,
    )

    # Possession-shaped squad: elite midfield, average elsewhere. Aligned =
    # POSSESSION (its real strength is midfield_control). Mismatched =
    # COUNTER_ATTACK (barely uses its own possession at all by design).
    possession_squad = {Position.CDM: 92, Position.CM: 93, Position.CAM: 91}
    out["possession_squad__aligned_possession__vs__mismatched_counter"] = play_n_matches(
        "BALANCED", "POSSESSION", possession_squad, "BALANCED", "COUNTER_ATTACK", possession_squad, n,
    )
    _progress("tactical alignment scenarios", 3, 3, t0)
    return out


# --- 6. Strong-but-mistactic'd vs weak-but-well-tactic'd: does good
# tactics let an underdog compete without ever inverting the result? -----
def underdog_tactics_scenarios(n=400):
    """"Bad tactics" / "good tactics" are picked from the CURRENT mentality
    grid, not football intuition — under this engine's tuning, PARK_THE_BUS
    is the strongest mentality and ATTACKING the weakest at equal rating
    (see mentality_grid_multi_context's own results), the opposite of what a
    naive "defensive=passive=bad, attacking=aggressive=good" labeling would
    assume. Using the wrong labels here (as an earlier version of this
    script did) makes "bad tactics for the favorite" accidentally ALSO widen
    the gap instead of narrowing it."""
    out = {}
    t0 = time.time()
    gaps = [10, 20, 30]
    for i, gap in enumerate(gaps, 1):
        strong = {pos: 90 for pos in Position}
        weak = {pos: 90 - gap for pos in Position}
        # Strong side plays its actually-worst combo (ATTACKING); weak side
        # plays its actually-best (PARK_THE_BUS) — both CENTRAL_PLAY to
        # isolate mentality as the one varying tactical factor.
        out[f"strong_bad_tactics__vs__weak_good_tactics__gap_{gap}"] = play_n_matches(
            "ATTACKING", "CENTRAL_PLAY", strong, "PARK_THE_BUS", "CENTRAL_PLAY", weak, n,
        )
        # Control: both sides play the same neutral tactic at the same gap,
        # to isolate how much of any narrowing is the tactic choice itself
        # versus just the rating gap.
        out[f"strong_neutral__vs__weak_neutral__gap_{gap}"] = play_n_matches(
            "BALANCED", "CENTRAL_PLAY", strong, "BALANCED", "CENTRAL_PLAY", weak, n,
        )
        _progress(f"underdog tactics gap {gap}", i, len(gaps), t0)
    return out


# --- 7. Coach-boost sweep: does a coach meaningfully narrow a rating gap
# without ever inverting it (backend/tests/test_coach_boost_balance.py's own
# regression test spot-checks one gap/loadout combo — this sweep is the
# reusable diagnostic tool for a future coach-balance pass, per plan §13
# Phase 4, covering the full gap x loadout grid instead of one point). The
# WEAK side gets each coach loadout in turn; the STRONG side never has a
# coach, isolating the coach's own effect from the underlying rating gap
# (same isolation strategy as underdog_tactics_scenarios's "control" row). ---
COACH_BOOST_LOADOUTS: dict[str, list[tuple]] = {
    "none": [],
    "single_attack_8": [(CoachBoostType.ATTACK_CENTRAL, 8.0)],
    "single_defence_8": [(CoachBoostType.DEFENCE_CENTRAL, 8.0)],
    # Same 3-boost/magnitude-8.0 loadout backend/tests/test_coach_boost_balance.py's
    # test_legendary_coach_does_not_flip_a_large_rating_gap_matchup uses.
    "legendary_triple_8": [
        (CoachBoostType.ATTACK_CENTRAL, 8.0),
        (CoachBoostType.DEFENCE_CENTRAL, 8.0),
        (CoachBoostType.GOALKEEPING, 8.0),
    ],
}


def _coach_from_loadout(name: str, boosts: list[tuple]) -> "Coach | None":
    """None (not an empty Coach) for the "none" loadout — build_side's own
    coach=None fast path (resolve_active_boosts returns an empty
    ActiveCoachBoosts) rather than a Coach with zero CoachBoost rows, so this
    sweep exercises the exact same no-coach code path the rest of this
    script's functions already use."""
    if not boosts:
        return None
    coach = Coach(display_name=f"Sweep Coach ({name})", rarity=Rarity.legendary)
    coach.boosts = [CoachBoost(boost_type=bt, magnitude=mag) for bt, mag in boosts]
    return coach


def coach_boost_sweep(n=300):
    gaps = [0, 10, 20, 30]
    out = {}
    t0 = time.time()
    total = len(gaps) * len(COACH_BOOST_LOADOUTS)
    i = 0
    for gap in gaps:
        ratings_strong = {pos: 90 for pos in Position}
        ratings_weak = {pos: 90 - gap for pos in Position}
        for name, boosts in COACH_BOOST_LOADOUTS.items():
            i += 1
            coach_b = _coach_from_loadout(name, boosts)
            out[f"gap_{gap}__{name}"] = play_n_matches(
                "BALANCED", "CENTRAL_PLAY", ratings_strong, "BALANCED", "CENTRAL_PLAY", ratings_weak, n,
                coach_a=None, coach_b=coach_b,
            )
            _progress(f"coach sweep gap={gap} loadout={name}", i, total, t0)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/tmp/matrix_results.json")
    parser.add_argument("--mentality-n", type=int, default=250)
    parser.add_argument("--playstyle-n", type=int, default=200)
    parser.add_argument("--formation-n", type=int, default=200)
    parser.add_argument("--gap-n", type=int, default=400)
    parser.add_argument("--alignment-n", type=int, default=350)
    parser.add_argument("--underdog-n", type=int, default=400)
    parser.add_argument("--coach-n", type=int, default=300)
    args = parser.parse_args()

    t0 = time.time()
    results = {}
    total_matches = 0

    print("== mentality grid ==", file=sys.stderr)
    results["mentality_grid"] = mentality_grid(args.mentality_n)
    total_matches += len(results["mentality_grid"]) * args.mentality_n

    print("== mentality grid, multi-context ==", file=sys.stderr)
    mgm = mentality_grid_multi_context(args.mentality_n)
    results["mentality_grid_multi_context"] = mgm
    total_matches += sum(len(g) for g in mgm["per_context"].values()) * args.mentality_n

    print("== playstyle grid ==", file=sys.stderr)
    results["playstyle_grid"] = playstyle_grid(args.playstyle_n)
    total_matches += len(results["playstyle_grid"]) * args.playstyle_n

    print("== playstyle grid, aligned squads ==", file=sys.stderr)
    results["playstyle_aligned_grid"] = playstyle_aligned_grid(args.playstyle_n)
    total_matches += len(results["playstyle_aligned_grid"]) * args.playstyle_n

    print("== formation grid ==", file=sys.stderr)
    results["formation_grid"] = formation_grid(args.formation_n)
    total_matches += len(results["formation_grid"]) * args.formation_n

    print("== strength gap sweep ==", file=sys.stderr)
    results["strength_gap"] = strength_gap_sweep(args.gap_n)
    total_matches += len(results["strength_gap"]) * args.gap_n

    print("== tactical alignment ==", file=sys.stderr)
    results["tactical_alignment"] = tactical_alignment_scenarios(args.alignment_n)
    total_matches += len(results["tactical_alignment"]) * args.alignment_n

    print("== underdog tactics ==", file=sys.stderr)
    results["underdog_tactics"] = underdog_tactics_scenarios(args.underdog_n)
    total_matches += len(results["underdog_tactics"]) * args.underdog_n

    print("== coach boost sweep ==", file=sys.stderr)
    results["coach_boost_sweep"] = coach_boost_sweep(args.coach_n)
    total_matches += len(results["coach_boost_sweep"]) * args.coach_n

    elapsed = time.time() - t0
    results["_meta"] = {
        "total_matches": total_matches,
        "elapsed_seconds": round(elapsed, 1),
        "mentality_n": args.mentality_n, "playstyle_n": args.playstyle_n,
        "formation_n": args.formation_n, "gap_n": args.gap_n,
        "alignment_n": args.alignment_n, "underdog_n": args.underdog_n,
        "coach_n": args.coach_n,
    }

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nTotal matches simulated: {total_matches}", file=sys.stderr)
    print(f"Elapsed: {elapsed:.1f}s", file=sys.stderr)
    print(f"Written to {args.out}", file=sys.stderr)

    # Short stdout summary: mentality grid win% for A, formatted as a table.
    print("\nMentality grid — win% for row mentality (column = opponent):")
    header = "".join(f"{m[:4]:>8s}" for m in MENTALITIES)
    print(f"{'':14s}{header}")
    for ma in MENTALITIES:
        row = "".join(f"{results['mentality_grid'][f'{ma}__vs__{mb}']['win_a']*100:7.1f}%" for mb in MENTALITIES)
        print(f"{ma:14s}{row}")

    # Coach boost sweep — win% for the WEAK side (row = loadout, column = gap),
    # so a working coach shows up as loadout rows creeping up from left (gap
    # 0, no rating disadvantage to offset) toward the right without ever
    # approaching/crossing 50% at the larger gaps (that would mean the coach
    # inverted the matchup — see test_coach_boost_balance.py's own regression
    # test for the exact threshold this guards).
    gaps = [0, 10, 20, 30]
    print("\nCoach boost sweep — weak side's win% by rating gap (column) and coach loadout (row):")
    header = "".join(f"{('gap ' + str(g)):>10s}" for g in gaps)
    print(f"{'':20s}{header}")
    for name in COACH_BOOST_LOADOUTS:
        row = "".join(f"{results['coach_boost_sweep'][f'gap_{g}__{name}']['win_b']*100:9.1f}%" for g in gaps)
        print(f"{name:20s}{row}")


if __name__ == "__main__":
    main()
