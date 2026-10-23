"""Balance simulation for Card Arena (match_service + arena_tactics): DB-free
matches through the real moment queue / resolution code, with the user's
choices picked at random (an average player).

Reports win/draw/loss by strength ratio (squads with flat line ratings
derived from the strength), the style matchup effect at equal strength,
and — with --legacy — the same table for the engine before the balance
rework (linear attack share, no rating edge).

--write stores the ratio table in app/services/arena_balance_table.json;
match_service reads it for the pre-match «шанс на победу» (≈).

Usage (from backend/):
    python scripts/simulate_arena_balance.py --n 2000
    python scripts/simulate_arena_balance.py --n 2000 --legacy
    python scripts/simulate_arena_balance.py --n 4000 --write
    python scripts/simulate_arena_balance.py --n 2000 --config '{"arena_share_exponent": 2.5}'
"""
import argparse
import json
import math
import random
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.enums import Position  # noqa: E402
from app.models.game_config import GameConfig  # noqa: E402
from app.services import arena_tactics, match_service  # noqa: E402

TABLE_PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "arena_balance_table.json"
RATIOS = [0.5, 0.6, 0.7, 0.77, 0.83, 0.87, 0.91, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.3, 1.43, 1.67, 2.0]

_SLOTS = [
    ("GK", Position.GK), ("DEF", Position.LB), ("DEF", Position.CB), ("DEF", Position.CB), ("DEF", Position.RB),
    ("MID", Position.CM), ("MID", Position.CDM), ("MID", Position.CM),
    ("FWD", Position.LW), ("FWD", Position.ST), ("FWD", Position.RW),
]


def default_config(**overrides) -> SimpleNamespace:
    values = {}
    for column in GameConfig.__table__.columns:
        default = column.default
        if default is None:
            continue
        arg = default.arg
        values[column.name] = arg(None) if callable(arg) else arg
    values.update(overrides)
    return SimpleNamespace(**values)


def rating_for(strength: int) -> int:
    return max(50, min(99, round(strength / 11 / 1.09)))


def stub_lineup(rating: int):
    slots = []
    for i, (category, position) in enumerate(_SLOTS):
        player = SimpleNamespace(id=i + 1, display_name=f"P{i + 1}", rating=rating, position=position)
        card = SimpleNamespace(id=i + 1, player=player)
        slots.append(SimpleNamespace(category=category, card=card, slot_code=f"S{i}"))
    return SimpleNamespace(slots=slots, chemistry=None)


def play(user_strength: int, opponent_strength: int, config, *, legacy: bool = False,
         user_style: str = "possession", opponent_style: str = "possession") -> tuple[int, int]:
    ur, orr = rating_for(user_strength), rating_for(opponent_strength)
    lineup = stub_lineup(ur)
    state = {
        "next_index": 0, "user_score": 0, "opponent_score": 0,
        "ratings": {"user_fwd": ur, "user_def": ur, "user_gk": ur,
                    "opponent_fwd": orr, "opponent_def": orr, "opponent_gk": orr},
        "cards": {}, "red_card_applied": False, "skills": None,
    }
    if legacy:
        us = match_service._with_jitter(user_strength)
        os_ = match_service._with_jitter(opponent_strength)
        ua, _ = arena_tactics.split(us, "possession")
        oa, _ = arena_tactics.split(os_, "possession")
        state["moments"] = match_service._generate_moment_queue(round(ua), round(oa), config, lineup, "B")
    else:
        balance = arena_tactics.compute_balance(user_strength, user_style, opponent_strength, opponent_style, config)
        state["balance"] = balance
        state["moments"] = match_service._generate_moment_queue(0, 0, config, lineup, "B", balance=balance)

    match_service._advance(state, config, "B")
    while state["next_index"] < len(state["moments"]):
        moment = state["moments"][state["next_index"]]
        action = random.choice(moment["actions"]) if moment["actions"] else "strike"
        _event, scored_by = match_service._resolve_action(moment, action, state, config, "B")
        if scored_by:
            state[f"{scored_by}_score"] += 1
        state["next_index"] += 1
        match_service._advance(state, config, "B")
    return state["user_score"], state["opponent_score"]


def measure(user_strength: int, opponent_strength: int, n: int, config, **kwargs) -> dict:
    w = d = l = goals = 0
    for _ in range(n):
        u, o = play(user_strength, opponent_strength, config, **kwargs)
        goals += u + o
        if u > o:
            w += 1
        elif u == o:
            d += 1
        else:
            l += 1
    return {"win": round(100 * w / n, 1), "draw": round(100 * d / n, 1), "loss": round(100 * l / n, 1),
            "goals": round(goals / n, 2)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=2000)
    parser.add_argument("--legacy", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--config", default="{}")
    parser.add_argument("--seed", type=int, default=20261015)
    args = parser.parse_args()
    random.seed(args.seed)
    config = default_config(**json.loads(args.config))

    base = 900
    print(f"{'ratio':>6} {'you':>5} {'opp':>5}   win  draw  loss  goals")
    table = []
    for ratio in RATIOS:
        user = round(base * math.sqrt(ratio))
        opp = round(base / math.sqrt(ratio))
        r = measure(user, opp, args.n, config, legacy=args.legacy)
        table.append({"ratio": ratio, **r})
        print(f"{ratio:>6} {user:>5} {opp:>5}  {r['win']:>5} {r['draw']:>5} {r['loss']:>5}  {r['goals']}")

    if not args.legacy:
        print("\nStyles at equal strength (900 vs 900), your win %:")
        for mine in arena_tactics.STYLES:
            row = []
            for theirs in arena_tactics.STYLES:
                r = measure(900, 900, max(200, args.n // 4), config, user_style=mine, opponent_style=theirs)
                row.append(f"{arena_tactics.STYLE_LABELS[theirs][:6]}={r['win']:>5}/{r['loss']:<5}")
            print(f"  {arena_tactics.STYLE_LABELS[mine]:<11}", "  ".join(row))

    if args.write and not args.legacy:
        TABLE_PATH.write_text(json.dumps({"n": args.n, "seed": args.seed, "table": table}, indent=1), encoding="utf-8")
        print(f"\nwritten {TABLE_PATH}")


if __name__ == "__main__":
    main()
