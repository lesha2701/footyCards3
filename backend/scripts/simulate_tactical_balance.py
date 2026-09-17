"""Phase 3 balance simulation script (spec §14) for the club tactical match
engine. Runs thousands of DB-free simulated matches per scenario and prints a
report — this is the empirical methodology the Phase 1 whole-branch review
used to find STATUS problems 1-4 (mentality backwards, playstyle inert,
formation inert, duel bands unreachable), and is what any future tuning pass
must be re-run against before considering this mergeable.

HISTORICAL NOTE (2026-09-07): this script's mentality variants (fixed_v3/v4/v5)
were written against a first-pass fix that applied the mentality/HIGH_PRESS
defense bonus as a MULTIPLIER on the defender's effective rating
(MENTALITY_DEFENSE_SHIFT/HIGH_PRESS_DEFENSE_SHIFT). That mechanism was
replaced the same day with a bounded ADDITIVE ratio-shift
(MENTALITY_DEFENSE_SHIFT/HIGH_PRESS_DEFENSE_SHIFT, see
club_tactical_matchup_service.zone_ratio's docstring) after the multiplier
was found to let a 58-rated worst-possible defender beat a 99-rated
best-possible attacker purely from mentality. The mentality-related variant
values below are kept for their historical narrative (the iteration from
"pool-bias alone isn't enough" through "a multiplier works but is unsafe at
extremes") but the multiplier constants they reference no longer exist as a
code path — see scripts/simulate_tactical_matrix.py for the CURRENT,
maintained balance-testing tool, which exercises the live shift-based
mechanism directly rather than through variant overrides.

Usage (from backend/, inside the docker container):
    python scripts/simulate_tactical_balance.py                 # "fixed" variant, all scenarios
    python scripts/simulate_tactical_balance.py --variant baseline
    python scripts/simulate_tactical_balance.py --variant fixed --trials 2000
    python scripts/simulate_tactical_balance.py --compare        # baseline vs fixed, side by side

No DB/app import side effects beyond the tactical services themselves —
squads are built from lightweight fake cards (same fixture shape
tests/test_club_tactical_balance.py already uses), not real ORM rows.
"""
import argparse
import contextlib
import statistics
from dataclasses import dataclass

from app.models.enums import Position
from app.services import club_tactical_matchup_service as matchup
from app.services import tournament_match_engine as engine
from app.services.club_formation_service import get_formation_slots
from app.services.club_tactical_profile_service import compute_profile


# --- Fixtures (mirrors tests/test_club_tactical_balance.py's shape) --------


@dataclass
class _FakePlayer:
    position: Position
    rating: int
    display_name: str = "Test Player"
    rarity: str = "common"
    club: int = 1
    country: int = 1
    attack_rating: int | None = None
    defense_rating: int | None = None


@dataclass
class _FakeCard:
    id: int
    player_id: int
    player: _FakePlayer
    diamond_rating_bonus: int = 0


class _Config:
    club_tactical_phases_per_match_min = 40
    club_tactical_phases_per_match_max = 70
    club_tactical_promoted_chance_target_min = 15
    club_tactical_promoted_chance_target_max = 25
    match_shot_type_in_box_weight = 55
    match_shot_type_long_range_weight = 35
    match_shot_type_empty_net_weight = 10
    match_shot_miss_chance_min = 0.08
    match_shot_miss_chance_max = 0.30
    match_defender_block_chance_min = 0.10
    match_defender_block_chance_max = 0.35
    match_attack_shoot_miss_chance_min = 0.08
    match_attack_shoot_miss_chance_max = 0.32
    match_pass_fail_chance_min = 0.05
    match_pass_fail_chance_max = 0.28
    match_receiver_shot_miss_chance_min = 0.05
    match_receiver_shot_miss_chance_max = 0.22
    match_tackle_foul_chance_min = 0.06
    match_tackle_foul_chance_max = 0.30
    match_tackle_red_chance_min = 0.05
    match_tackle_red_chance_max = 0.22
    match_keeper_save_chance_min = 0.35
    match_keeper_save_chance_max = 0.75
    match_penalty_gk_rating_penalty = 6


def squad(ratings: dict[Position, int], default: int = 75, formation: str = "4-3-3") -> list[tuple]:
    slots = get_formation_slots(formation)
    cards = []
    for i, slot in enumerate(slots):
        rating = ratings.get(slot.ideal_position, default)
        cards.append((_FakeCard(id=i, player_id=i, player=_FakePlayer(slot.ideal_position, rating)), slot))
    return cards


def lineup_dicts(cards_with_slots: list[tuple]) -> list[dict]:
    return [{"category": slot.category, "rating": card.player.rating} for card, slot in cards_with_slots]


def play_match(mentality_a, playstyle_a, ratings_a, mentality_b, playstyle_b, ratings_b, formation_a="4-3-3", formation_b="4-3-3", default_a=75, default_b=75):
    cards_a = squad(ratings_a, default=default_a, formation=formation_a)
    cards_b = squad(ratings_b, default=default_b, formation=formation_b)
    side_a = matchup.build_side(cards_a, mentality_a, playstyle_a)
    side_b = matchup.build_side(cards_b, mentality_b, playstyle_b)
    result = engine.simulate_match(side_a, side_b, lineup_dicts(cards_a), lineup_dicts(cards_b), _Config())
    return result


def chances_only(mentality_a, playstyle_a, ratings_a, mentality_b, playstyle_b, ratings_b, formation_a="4-3-3", formation_b="4-3-3", default_a=75, default_b=75):
    cards_a = squad(ratings_a, default=default_a, formation=formation_a)
    cards_b = squad(ratings_b, default=default_b, formation=formation_b)
    side_a = matchup.build_side(cards_a, mentality_a, playstyle_a)
    side_b = matchup.build_side(cards_b, mentality_b, playstyle_b)
    return matchup.simulate_match_phases(side_a, side_b, _Config())


# --- Variants ----------------------------------------------------------------

# NOTE: HIGH_PRESS_DEFENSE_SHIFT/MENTALITY_DEFENSE_SHIFT below are on the
# CURRENT additive ratio-point scale (0.0 = no-op, ~0.05-0.2 = a real,
# bounded effect) — translated from this script's original multiplier-scale
# values (see the file's HISTORICAL NOTE); the translation is approximate,
# kept for the variants' historical narrative, not as a precise re-derivation.
BASELINE = {
    "RATIO_AMPLIFICATION": 1.0,          # no rescale (problem 4 present)
    "DEFENSIVE_POOL_STRATEGY": "uniform",  # no rating bias (problem 1 present)
    "POOL_APPLIES_TO_NORMAL_DEFENSE": False,
    "HIGH_PRESS_DEFENSE_SHIFT": 0.0,     # no-op (problem 2's HIGH_PRESS half present)
    "POSSESSION_RETRY_MAX": 0.0,         # no-op (problem 2's POSSESSION half present)
    "DEPTH_BONUS_SCALE": 0.0,            # no-op (problem 3 present)
}
# fixed_v1: the FIRST attempt — pool-bias applied only where spec §6.4
# literally scopes it (the counter-attack chain). Kept as a comparison point:
# simulation showed this alone does NOT flip problem 1 (PARK_THE_BUS still
# conceded more than ATTACKING, 6.96 vs 5.88 GA/match) because that sub-case
# only fires when the bus side's own rare attack breaks down.
FIXED_V1 = {
    "RATIO_AMPLIFICATION": 2.5,
    "DEFENSIVE_POOL_STRATEGY": "soft_bias",
    "POOL_APPLIES_TO_NORMAL_DEFENSE": False,
    "HIGH_PRESS_DEFENSE_SHIFT": 0.05,
    "POSSESSION_RETRY_MAX": 0.5,
    "DEPTH_BONUS_SCALE": 2.0,
}
# fixed_v2: same as v1, but the mentality-shaped pool also applies to the
# NORMAL Stage-1/Stage-2 defensive pick, not just transitions — a deliberate
# departure from spec §6.4's literal scoping (see
# club_tactical_matchup_service.POOL_APPLIES_TO_NORMAL_DEFENSE's docstring).
FIXED_V2 = {
    "RATIO_AMPLIFICATION": 2.5,
    "DEFENSIVE_POOL_STRATEGY": "soft_bias",
    "POOL_APPLIES_TO_NORMAL_DEFENSE": True,
    "HIGH_PRESS_DEFENSE_SHIFT": 0.05,
    "POSSESSION_RETRY_MAX": 0.5,
    "DEPTH_BONUS_SCALE": 2.0,
}
# fixed_v3: v2's pool-bias, but at maximum (deterministic hard_bias) —
# still could not flip problem 1's GA ordering (PARK_THE_BUS > ATTACKING),
# confirming the volume effect below needs its own direct lever, not a
# stronger version of the same one.
FIXED_V3 = {
    "RATIO_AMPLIFICATION": 2.5,
    "DEFENSIVE_POOL_STRATEGY": "hard_bias",
    "POOL_APPLIES_TO_NORMAL_DEFENSE": True,
    "MENTALITY_DEFENSE_SHIFT": {"PARK_THE_BUS": 0.0, "DEFENSIVE": 0.0, "BALANCED": 0.0, "ATTACKING": 0.0},
    "HIGH_PRESS_DEFENSE_SHIFT": 0.05,
    "POSSESSION_RETRY_MAX": 0.5,
    "DEPTH_BONUS_SCALE": 2.0,
}
# fixed_v4: v2's settings (soft_bias, everywhere) PLUS a direct, moderate
# per-phase defensive multiplier by mentality — the lever actually sized to
# offset the initiative-driven volume effect (see
# club_tactical_matchup_service.MENTALITY_DEFENSE_SHIFT's docstring).
FIXED_V4 = {
    "RATIO_AMPLIFICATION": 2.5,
    "DEFENSIVE_POOL_STRATEGY": "soft_bias",
    "POOL_APPLIES_TO_NORMAL_DEFENSE": True,
    "MENTALITY_DEFENSE_SHIFT": {"PARK_THE_BUS": 0.10, "DEFENSIVE": 0.05, "BALANCED": 0.0, "ATTACKING": -0.05},
    "HIGH_PRESS_DEFENSE_SHIFT": 0.05,
    "POSSESSION_RETRY_MAX": 0.5,
    "DEPTH_BONUS_SCALE": 2.0,
}
# fixed_v5: same as v4 with a stronger defensive multiplier, to see whether
# v4's moderate value is enough or whether more separation is needed.
FIXED_V5 = {
    "RATIO_AMPLIFICATION": 2.5,
    "DEFENSIVE_POOL_STRATEGY": "soft_bias",
    "POOL_APPLIES_TO_NORMAL_DEFENSE": True,
    "MENTALITY_DEFENSE_SHIFT": {"PARK_THE_BUS": 0.20, "DEFENSIVE": 0.10, "BALANCED": 0.0, "ATTACKING": -0.10},
    "HIGH_PRESS_DEFENSE_SHIFT": 0.05,
    "POSSESSION_RETRY_MAX": 0.5,
    "DEPTH_BONUS_SCALE": 2.0,
}
_NEUTRAL_MENTALITY_DEFENSE_SHIFT = {"PARK_THE_BUS": 0.0, "DEFENSIVE": 0.0, "BALANCED": 0.0, "ATTACKING": 0.0}
for _v in (BASELINE, FIXED_V1, FIXED_V2):
    _v.setdefault("MENTALITY_DEFENSE_SHIFT", _NEUTRAL_MENTALITY_DEFENSE_SHIFT)

VARIANTS = {
    "baseline": BASELINE, "fixed_v1": FIXED_V1, "fixed_v2": FIXED_V2, "fixed_v3": FIXED_V3,
    "fixed_v4": FIXED_V4, "fixed_v5": FIXED_V5,
}


@contextlib.contextmanager
def apply_variant(name: str):
    overrides = VARIANTS[name]
    import app.services.club_tactical_profile_service as profile_mod

    saved = {
        "RATIO_AMPLIFICATION": matchup.RATIO_AMPLIFICATION,
        "DEFENSIVE_POOL_STRATEGY": matchup.DEFENSIVE_POOL_STRATEGY,
        "POOL_APPLIES_TO_NORMAL_DEFENSE": matchup.POOL_APPLIES_TO_NORMAL_DEFENSE,
        "MENTALITY_DEFENSE_SHIFT": matchup.MENTALITY_DEFENSE_SHIFT,
        "HIGH_PRESS_DEFENSE_SHIFT": matchup.HIGH_PRESS_DEFENSE_SHIFT,
        "POSSESSION_RETRY_MAX": matchup.POSSESSION_RETRY_MAX,
        "DEPTH_BONUS_SCALE": profile_mod.DEPTH_BONUS_SCALE,
    }
    matchup.RATIO_AMPLIFICATION = overrides["RATIO_AMPLIFICATION"]
    matchup.DEFENSIVE_POOL_STRATEGY = overrides["DEFENSIVE_POOL_STRATEGY"]
    matchup.POOL_APPLIES_TO_NORMAL_DEFENSE = overrides["POOL_APPLIES_TO_NORMAL_DEFENSE"]
    matchup.MENTALITY_DEFENSE_SHIFT = overrides["MENTALITY_DEFENSE_SHIFT"]
    matchup.HIGH_PRESS_DEFENSE_SHIFT = overrides["HIGH_PRESS_DEFENSE_SHIFT"]
    matchup.POSSESSION_RETRY_MAX = overrides["POSSESSION_RETRY_MAX"]
    profile_mod.DEPTH_BONUS_SCALE = overrides["DEPTH_BONUS_SCALE"]
    try:
        yield
    finally:
        matchup.RATIO_AMPLIFICATION = saved["RATIO_AMPLIFICATION"]
        matchup.DEFENSIVE_POOL_STRATEGY = saved["DEFENSIVE_POOL_STRATEGY"]
        matchup.POOL_APPLIES_TO_NORMAL_DEFENSE = saved["POOL_APPLIES_TO_NORMAL_DEFENSE"]
        matchup.MENTALITY_DEFENSE_SHIFT = saved["MENTALITY_DEFENSE_SHIFT"]
        matchup.HIGH_PRESS_DEFENSE_SHIFT = saved["HIGH_PRESS_DEFENSE_SHIFT"]
        matchup.POSSESSION_RETRY_MAX = saved["POSSESSION_RETRY_MAX"]
        profile_mod.DEPTH_BONUS_SCALE = saved["DEPTH_BONUS_SCALE"]


# --- Scenarios -----------------------------------------------------------


def scenario_mentality_ga(trials: int) -> dict:
    """Problem 1: does PARK_THE_BUS concede fewer goals than ATTACKING for
    the SAME weak-defender squad against the SAME elite attacker (spec §6.5
    worked example)? Reports average goals-against per mentality."""
    weak_def = {Position.CB: 64, Position.LB: 65, Position.RB: 66}
    elite_atk = {Position.ST: 95, Position.LW: 93, Position.RW: 94}
    out = {}
    for mentality in matchup.MENTALITIES:
        ga = []
        for _ in range(trials):
            r = play_match(mentality, "CENTRAL_PLAY", weak_def, "ATTACKING", "CENTRAL_PLAY", elite_atk)
            ga.append(r.score_b)
        out[mentality] = statistics.mean(ga)
    return out


def scenario_picked_defender_rating(trials: int) -> dict:
    """Problem 1, mechanism-level: average rating of the defender actually
    picked out of defensive_pool, per mentality — this is what STATUS said
    barely moved (only ~1.6 rating points across the whole axis) under the
    old uniform-sample pool."""
    ratings = {Position.CB: 60, Position.LB: 75, Position.RB: 90}  # deliberately spread so bias is visible
    cards = [c for c, _s in squad(ratings, default=75)]
    out = {}
    for mentality in matchup.MENTALITIES:
        picks = []
        for _ in range(trials):
            pool = matchup.defensive_pool(cards, mentality, "BALANCED")
            picked = matchup.weighted_pick(pool, "central_defence")
            picks.append(picked.player.rating)
        out[mentality] = statistics.mean(picks)
    return out


def scenario_wing_vs_central(trials: int) -> tuple[float, float]:
    """Spec §14 item 2/3: flank-stacked squad's HIGH+VERY_HIGH chance share
    under WING_PLAY vs CENTRAL_PLAY."""
    strong_flanks = {Position.LW: 92, Position.RW: 92, Position.LB: 92, Position.RB: 92}
    opponent = {pos: 75 for pos in Position}

    def high_share(playstyle):
        high = total = 0
        for _ in range(trials):
            chances = chances_only("BALANCED", playstyle, strong_flanks, "BALANCED", "CENTRAL_PLAY", opponent, default_a=75)
            for c in chances:
                if c.attacking_side != "a":
                    continue
                total += 1
                if c.quality in ("HIGH", "VERY_HIGH"):
                    high += 1
        return high / total if total else 0.0

    return high_share("WING_PLAY"), high_share("CENTRAL_PLAY")


def scenario_counter_vs_mentality(trials: int) -> tuple[float, float]:
    """Spec §14 item 5: COUNTER_ATTACK's conversion (share of own chances
    that reach HIGH/VERY_HIGH) against an ATTACKING opponent vs a
    PARK_THE_BUS opponent — should be measurably higher vs ATTACKING (a
    thinner defensive pool to counter into)."""
    counter_squad = {pos: 82 for pos in Position}
    opponent = {pos: 82 for pos in Position}

    def conversion(opp_mentality):
        good = total = 0
        for _ in range(trials):
            chances = chances_only("BALANCED", "COUNTER_ATTACK", counter_squad, opp_mentality, "CENTRAL_PLAY", opponent)
            for c in chances:
                if c.attacking_side != "a":
                    continue
                total += 1
                if c.quality in ("HIGH", "VERY_HIGH"):
                    good += 1
        return good / total if total else 0.0

    return conversion("ATTACKING"), conversion("PARK_THE_BUS")


def scenario_high_press(trials: int) -> tuple[float, float]:
    """Spec §14 item 6: HIGH_PRESS's transition win rate (share of opponent
    Stage-1 duels that become a breakdown) against a POSSESSION opponent with
    mediocre midfield — should beat BALANCED's own breakdown-forcing rate."""
    press_squad = {pos: 80 for pos in Position}
    weak_mid_possession = {Position.CDM: 65, Position.CM: 66, Position.CAM: 65}

    def breakdown_rate(press_mentality_playstyle):
        mentality, playstyle = press_mentality_playstyle
        breakdowns = total = 0
        for _ in range(trials):
            cards_press = squad(press_squad, default=80)
            cards_poss = squad(weak_mid_possession, default=75)
            side_press = matchup.build_side(cards_press, mentality, playstyle)
            side_poss = matchup.build_side(cards_poss, "BALANCED", "POSSESSION")
            for _ in range(20):
                zone = matchup.pick_progression_zone(side_poss.playstyle)
                if zone is None:
                    continue
                if not matchup.possession_buildup_survives(side_poss.profile.midfield_control):
                    continue
                defence_zone = "wing_defence" if zone == "wing_attack" else "central_defence"
                atk_duelist = matchup.weighted_pick(side_poss.cards, zone)
                def_bonus = matchup.HIGH_PRESS_DEFENSE_SHIFT if side_press.playstyle == "HIGH_PRESS" else 0.0
                def_duelist = matchup.weighted_pick(side_press.cards, defence_zone)
                ratio = matchup.zone_ratio(atk_duelist, zone, def_duelist, defence_zone, def_bonus)
                outcome = matchup.resolve_stage1(ratio)
                total += 1
                if outcome == "breakdown":
                    breakdowns += 1
        return breakdowns / total if total else 0.0

    return breakdown_rate(("BALANCED", "HIGH_PRESS")), breakdown_rate(("BALANCED", "BALANCED"))


def scenario_possession_extends(trials: int) -> tuple[float, float]:
    """Problem 2, POSSESSION half: average promoted-chance count for a
    strong-midfield POSSESSION squad vs a weak-midfield POSSESSION squad,
    same opponent — strong midfield should produce more attempts."""
    strong_mid = {Position.CDM: 95, Position.CM: 96, Position.CAM: 94}
    weak_mid = {Position.CDM: 60, Position.CM: 61, Position.CAM: 60}
    opponent = {pos: 78 for pos in Position}

    def avg_chances(mid_ratings):
        counts = []
        for _ in range(trials):
            chances = chances_only("BALANCED", "POSSESSION", mid_ratings, "BALANCED", "CENTRAL_PLAY", opponent)
            counts.append(sum(1 for c in chances if c.attacking_side == "a"))
        return statistics.mean(counts)

    return avg_chances(strong_mid), avg_chances(weak_mid)


def scenario_formation_depth(trials: int) -> dict:
    """Problem 3: midfield_control for a FLAT-rated squad (every position
    the same rating) across all 4 formations — the exact reproduction case
    STATUS used ("a flat-rated squad produces byte-identical zone values
    across all 4 formations")."""
    flat = {pos: 78 for pos in Position}
    out = {}
    for formation in ("4-3-3", "4-4-2", "3-5-2", "5-3-2"):
        cards = squad(flat, default=78, formation=formation)
        out[formation] = compute_profile(cards).midfield_control
    return out


def scenario_duel_band_reachability(trials: int) -> dict:
    """Problem 4: for a range of rating gaps, what share of resolved Stage-1
    duels land in each band? Confirms ">0.75" (breakdown 10%/stall 25%/
    advance 65%) is actually reachable for a real large gap."""
    gaps = [(60, 60), (70, 60), (80, 60), (95, 60), (99, 58)]
    out = {}
    for atk, dfn in gaps:
        atk_card = _FakeCard(id=1, player_id=1, player=_FakePlayer(Position.ST, atk))
        def_card = _FakeCard(id=2, player_id=2, player=_FakePlayer(Position.CB, dfn))
        ratios = [matchup.zone_ratio(atk_card, "central_attack", def_card, "central_defence") for _ in range(trials)]
        band_counts = {">0.75": 0, "0.60-0.75": 0, "0.40-0.60": 0, "<0.40": 0}
        for r in ratios:
            if r > 0.75:
                band_counts[">0.75"] += 1
            elif r > 0.60:
                band_counts["0.60-0.75"] += 1
            elif r > 0.40:
                band_counts["0.40-0.60"] += 1
            else:
                band_counts["<0.40"] += 1
        out[f"{atk}v{dfn}"] = {k: v / trials for k, v in band_counts.items()}
    return out


def scenario_large_gap_holds(trials: int) -> tuple[int, int]:
    """Spec §14 item 7: a 70-rated squad does not out-chance a 95-rated one
    even with an optimal tactical matchup."""
    weak = {pos: 70 for pos in Position}
    strong = {pos: 95 for pos in Position}
    weak_total = strong_total = 0
    for _ in range(trials):
        chances = chances_only("ATTACKING", "COUNTER_ATTACK", weak, "PARK_THE_BUS", "CENTRAL_PLAY", strong)
        for c in chances:
            if c.attacking_side == "a":
                weak_total += 1
            else:
                strong_total += 1
    return weak_total, strong_total


def scenario_identical_squads(trials: int) -> tuple[int, int]:
    """Spec §14 item 8: two identical squads on identical settings ~50/50."""
    ratings = {pos: 78 for pos in Position}
    a_total = b_total = 0
    for _ in range(trials):
        chances = chances_only("BALANCED", "CENTRAL_PLAY", ratings, "BALANCED", "CENTRAL_PLAY", ratings)
        for c in chances:
            if c.attacking_side == "a":
                a_total += 1
            else:
                b_total += 1
    return a_total, b_total


def scenario_event_volume(trials: int) -> float:
    ratings = {pos: 78 for pos in Position}
    counts = []
    for _ in range(trials):
        r = play_match("BALANCED", "CENTRAL_PLAY", ratings, "BALANCED", "CENTRAL_PLAY", ratings)
        counts.append(len(r.event_log))
    return statistics.mean(counts)


def run_all(trials: int) -> dict:
    return {
        "mentality_ga": scenario_mentality_ga(trials),
        "picked_defender_rating": scenario_picked_defender_rating(trials * 5),
        "wing_vs_central": scenario_wing_vs_central(trials),
        "counter_vs_mentality": scenario_counter_vs_mentality(trials),
        "high_press": scenario_high_press(trials // 4 or 1),
        "possession_extends": scenario_possession_extends(trials),
        "formation_depth": scenario_formation_depth(trials),
        "duel_band_reachability": scenario_duel_band_reachability(trials * 10),
        "large_gap_holds": scenario_large_gap_holds(trials),
        "identical_squads": scenario_identical_squads(trials * 2),
        "event_volume": scenario_event_volume(min(trials, 300)),
    }


def print_report(label: str, results: dict) -> None:
    print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")

    print("\n-- Problem 1: mentality vs goals conceded (weak defence vs elite attack) --")
    for m, ga in results["mentality_ga"].items():
        print(f"  {m:14s} GA/match = {ga:.2f}")

    print("\n-- Problem 1: avg rating of the defender actually picked, by mentality --")
    for m, r in results["picked_defender_rating"].items():
        print(f"  {m:14s} avg picked rating = {r:.1f}")

    wing, central = results["wing_vs_central"]
    print(f"\n-- Problem 2: flank-stacked squad HIGH+VERY_HIGH share: WING_PLAY={wing:.1%} CENTRAL_PLAY={central:.1%} --")

    counter_atk, counter_bus = results["counter_vs_mentality"]
    print(f"-- Problem 2: COUNTER_ATTACK conversion vs ATTACKING={counter_atk:.1%} vs PARK_THE_BUS={counter_bus:.1%} --")

    press_rate, balanced_rate = results["high_press"]
    print(f"-- Problem 2: opponent breakdown rate forced: HIGH_PRESS={press_rate:.1%} BALANCED={balanced_rate:.1%} --")

    strong_mid_chances, weak_mid_chances = results["possession_extends"]
    print(f"-- Problem 2: POSSESSION chances/match: strong midfield={strong_mid_chances:.2f} weak midfield={weak_mid_chances:.2f} --")

    print("\n-- Problem 3: midfield_control for a flat-78-rated squad, by formation --")
    for formation, value in results["formation_depth"].items():
        print(f"  {formation:6s} midfield_control = {value:.1f}")

    print("\n-- Problem 4: Stage-1 band distribution by rating gap --")
    for gap, bands in results["duel_band_reachability"].items():
        band_str = "  ".join(f"{k}={v:.1%}" for k, v in bands.items())
        print(f"  {gap:8s} {band_str}")

    weak_total, strong_total = results["large_gap_holds"]
    print(f"\n-- Regression, item 7: 70-rated (optimal tactics) chances={weak_total} vs 95-rated chances={strong_total} --")

    a_total, b_total = results["identical_squads"]
    total = a_total + b_total
    share = a_total / total if total else 0
    print(f"-- Regression, item 8: identical squads split {share:.1%} / {1 - share:.1%} --")

    print(f"\n-- Side effect: avg promoted events/match = {results['event_volume']:.1f} (target range 15-25) --")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=list(VARIANTS.keys()), default="fixed_v2")
    parser.add_argument("--trials", type=int, default=400)
    parser.add_argument("--compare", action="store_true")
    args = parser.parse_args()

    if args.compare:
        for name in VARIANTS:
            with apply_variant(name):
                print_report(f"VARIANT: {name}", run_all(args.trials))
    else:
        with apply_variant(args.variant):
            print_report(f"VARIANT: {args.variant}", run_all(args.trials))


if __name__ == "__main__":
    main()
