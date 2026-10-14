"""Compares team strength under the old flat club/country chemistry and the
new neighbour-link chemistry (services/chemistry_service.py) for EXISTING
lineups, so starting GameConfig values can be picked safely before
chemistry_enabled is switched on. Read-only: only SELECTs, nothing is
written, GameConfig is not read (candidate rules come from the grid below or
the command line).

Sources:
  * Card Arena lineups (lineups / lineup_cards, every template that is 11/11)
    — the exact strength formula players see (tactic, coach, stadium).
  * Player-tournament squads (personal_squads / personal_squad_cards) — the
    tournament engine has no single strength number, so the same
    calculate_base_strength formula (no tactic/coach/stadium) is used as a
    proxy for "how much do the match ratings move".
  * --synthetic N: N random valid 4-3-3 squads drawn from the active player
    pool (on-position where possible), as a stand-in for a real player base
    on a fresh/seed DB with only a handful of lineups.

Usage (from backend/, DATABASE_URL pointing at the DB to inspect):

    python -m scripts.compare_chemistry --synthetic 2000
    python -m scripts.compare_chemistry --rules "1,2,4;floor=1;per_point=1"
"""
import argparse
import asyncio
import os
import random
import statistics
from types import SimpleNamespace as NS

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.enums import Position, Rarity
from app.services.chemistry_service import ChemistryResult, ChemistryRules, compute_chemistry
from app.services.club_formation_service import CLUB_FORMATIONS
from app.services.lineup_service import CATEGORY_POSITIONS, calculate_base_strength

DEFAULT_GRID = [
    ChemistryRules(thresholds=(1, 2, 4), player_floor=0, rating_per_point=1),
    ChemistryRules(thresholds=(1, 2, 4), player_floor=1, rating_per_point=1),
    ChemistryRules(thresholds=(2, 3, 5), player_floor=1, rating_per_point=1),
    ChemistryRules(thresholds=(1, 2, 4), player_floor=1, rating_per_point=2),
    ChemistryRules(thresholds=(2, 4, 6), player_floor=0, rating_per_point=2),
]


def _parse_rules(spec: str) -> ChemistryRules:
    parts = spec.split(";")
    thresholds = tuple(int(x) for x in parts[0].split(","))
    kw = dict(p.split("=") for p in parts[1:])
    return ChemistryRules(
        thresholds=thresholds, player_floor=int(kw.get("floor", 0)), rating_per_point=int(kw.get("per_point", 1)),
        player_max=int(kw.get("max", 3)), off_position_penalty=int(kw.get("penalty", 0)),
        link_strong=int(kw.get("strong", 2)), link_medium=int(kw.get("medium", 1)),
    )


def _card(row) -> NS:
    return NS(
        diamond_rating_bonus=row.diamond_rating_bonus or 0,
        player=NS(club=row.club, country=row.country, position=Position(row.position), rating=row.rating,
                  rarity=Rarity(row.rarity), attack_rating=row.attack_rating, defense_rating=row.defense_rating),
    )


async def _load_arena(conn) -> list[dict]:
    rows = (await conn.execute(text("""
        SELECT l.id AS lineup_id, l.tactic, lc.slot_code, uc.diamond_rating_bonus,
               p.club, p.country, p.position, p.rating, p.rarity, p.attack_rating, p.defense_rating,
               c.rarity AS coach_rarity, s.boost_pct AS stadium_boost
        FROM lineups l
        JOIN lineup_cards lc ON lc.lineup_id = l.id
        JOIN user_cards uc ON uc.id = lc.user_card_id
        JOIN players p ON p.id = uc.player_id
        LEFT JOIN user_coach_cards ucc ON ucc.id = l.user_coach_card_id
        LEFT JOIN coaches c ON c.id = ucc.coach_id
        LEFT JOIN user_stadium_cards usc ON usc.id = l.user_stadium_card_id
        LEFT JOIN stadiums s ON s.id = usc.stadium_id
    """))).all()
    lineups: dict[int, dict] = {}
    slots = {s.code: s for s in CLUB_FORMATIONS["4-3-3"]}
    for r in rows:
        entry = lineups.setdefault(r.lineup_id, {
            "kind": "arena", "formation": "4-3-3", "tactic": r.tactic, "pairs": [],
            "coach": NS(rarity=Rarity(r.coach_rarity), boosts=[]) if r.coach_rarity else None,
            "stadium": 1.0 + float(r.stadium_boost) if r.stadium_boost is not None else 1.0,
        })
        if r.slot_code in slots:
            entry["pairs"].append((_card(r), slots[r.slot_code]))
    return [l for l in lineups.values() if len(l["pairs"]) == 11]


async def _load_squads(conn) -> list[dict]:
    rows = (await conn.execute(text("""
        SELECT ps.id AS squad_id, ps.formation, psc.slot_code, uc.diamond_rating_bonus,
               p.club, p.country, p.position, p.rating, p.rarity, p.attack_rating, p.defense_rating
        FROM personal_squads ps
        JOIN personal_squad_cards psc ON psc.squad_id = ps.id
        JOIN user_cards uc ON uc.id = psc.user_card_id AND uc.owner_id = ps.user_id
        JOIN players p ON p.id = uc.player_id
    """))).all()
    squads: dict[int, dict] = {}
    for r in rows:
        slots = {s.code: s for s in CLUB_FORMATIONS.get(r.formation, [])}
        entry = squads.setdefault(r.squad_id, {"kind": "tournament", "formation": r.formation, "tactic": None,
                                               "coach": None, "stadium": 1.0, "pairs": []})
        if r.slot_code in slots:
            entry["pairs"].append((_card(r), slots[r.slot_code]))
    return [s for s in squads.values() if len(s["pairs"]) == len(CLUB_FORMATIONS.get(s["formation"], []))]


async def _synthetic(conn, n: int, seed: int) -> list[dict]:
    rows = (await conn.execute(text("""
        SELECT 0 AS diamond_rating_bonus, club, country, position, rating, rarity, attack_rating, defense_rating
        FROM players WHERE is_active
    """))).all()
    by_position: dict[str, list] = {}
    for r in rows:
        by_position.setdefault(r.position, []).append(r)
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        pairs, used = [], set()
        for slot in CLUB_FORMATIONS["4-3-3"]:
            pool = [r for r in by_position.get(slot.ideal_position.value, []) if id(r) not in used]
            if not pool:
                pool = [r for pos in CATEGORY_POSITIONS[slot.category] for r in by_position.get(pos.value, [])
                        if id(r) not in used]
            pick = rng.choice(pool)
            used.add(id(pick))
            pairs.append((_card(pick), slot))
        out.append({"kind": "synthetic", "formation": "4-3-3", "tactic": "balanced", "coach": None, "stadium": 1.0,
                    "pairs": pairs})
    return out


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def _report(label: str, lineups: list[dict], grid: list[ChemistryRules]) -> None:
    print(f"\n== {label}: {len(lineups)} complete lineups ==")
    if not lineups:
        return
    old = []
    for l in lineups:
        old.append(calculate_base_strength(l["pairs"], coach=l["coach"], tactic=l["tactic"], stadium_multiplier=l["stadium"]))
    zero = [
        calculate_base_strength(l["pairs"], coach=l["coach"], tactic=l["tactic"], stadium_multiplier=l["stadium"],
                                chemistry=ChemistryResult(formation=l["formation"]))
        for l in lineups
    ]
    flat = [o - z for o, z in zip(old, zero)]
    print(f"old strength: mean {statistics.mean(old):.0f}, min {min(old)}, max {max(old)}; "
          f"old flat chemistry bonus in it: mean {statistics.mean(flat):.1f}, max {max(flat)}")
    header = f"{'rules':<38} {'chem avg':>8} {'Δ mean':>7} {'Δ med':>6} {'Δ p10':>6} {'Δ p90':>6} {'Δ min':>6} {'Δ max':>6} {'Δ% mean':>8} {'Δ% max':>7} {'rank flips':>10}"
    print(header)
    for rules in grid:
        deltas, pcts, chems, new = [], [], [], []
        for l, o in zip(lineups, old):
            result = compute_chemistry(l["pairs"], l["formation"], rules, slot_count=len(l["pairs"]))
            n = calculate_base_strength(l["pairs"], coach=l["coach"], tactic=l["tactic"], stadium_multiplier=l["stadium"],
                                        chemistry=result)
            new.append(n)
            deltas.append(n - o)
            pcts.append(100.0 * (n - o) / o if o else 0.0)
            chems.append(result.team)
        # Pairs whose order flips between the formulas (how much the new
        # chemistry reshuffles who is stronger), sampled for big inputs.
        idx = list(range(len(lineups)))
        sample = idx if len(idx) <= 400 else random.Random(1).sample(idx, 400)
        flips = total = 0
        for i_pos, i in enumerate(sample):
            for j in sample[i_pos + 1:]:
                if old[i] == old[j]:
                    continue
                total += 1
                if (old[i] - old[j]) * (new[i] - new[j]) < 0:
                    flips += 1
        name = f"thr={rules.thresholds} floor={rules.player_floor} pp={rules.rating_per_point}"
        print(f"{name:<38} {statistics.mean(chems):>8.1f} {statistics.mean(deltas):>7.1f} {statistics.median(deltas):>6.1f} "
              f"{_pct(deltas, .1):>6.1f} {_pct(deltas, .9):>6.1f} {min(deltas):>6} {max(deltas):>6} "
              f"{statistics.mean(pcts):>7.2f}% {max(pcts):>6.2f}% {100.0 * flips / total if total else 0:>9.1f}%")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--synthetic", type=int, default=0, help="also test N random 4-3-3 squads from the player pool")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--rules", action="append", help='e.g. "1,2,4;floor=1;per_point=1" (repeatable)')
    args = parser.parse_args()
    grid = [_parse_rules(r) for r in args.rules] if args.rules else DEFAULT_GRID

    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.connect() as conn:
        arena = await _load_arena(conn)
        squads = await _load_squads(conn)
        synthetic = await _synthetic(conn, args.synthetic, args.seed) if args.synthetic else []
    await engine.dispose()

    _report("Card Arena lineups", arena, grid)
    _report("Player-tournament squads (strength proxy)", squads, grid)
    if synthetic:
        _report(f"Synthetic random 4-3-3 squads (seed {args.seed})", synthetic, grid)


if __name__ == "__main__":
    asyncio.run(main())
