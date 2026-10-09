"""Balance check for any card skill in the player-tournament engine.

Plays N seeded matches between two identical 75-rated 4-3-3 squads (WING_PLAY
vs WING_PLAY) where side A's card at one position carries a level-III skill,
and reports goals per match and how many episodes per match the skill
decided (vs the same draws without it). Usage (from backend/):

    python -m scripts.simulate_card_skills --matches 3000
"""
import argparse
import random
import statistics

from app.models.enums import Position
from app.services import club_tactical_matchup_service as matchup
from app.services import tournament_match_engine as engine
from app.services.club_formation_service import get_formation_slots
from scripts.simulate_aerial_skill import _Card, _Config
from scripts.simulate_tactical_balance import _FakePlayer

SCENARIOS = [
    ("sniper", Position.ST, "a"),
    ("dribbler", Position.LW, "a"),
    ("crosser", Position.LW, "a"),
    ("aerial_master", Position.ST, "a"),
    ("last_line", Position.CB, "a"),
    ("one_on_one", Position.GK, "a"),
    ("reflexes", Position.GK, "a"),
]


def _effect(code: str) -> dict:
    return {"code": code, "level": 3, "bonus_pp": 6, "cap_pp": 8, "floor": 0.02, "ceiling": 0.95}


def _side(skill: tuple[str, Position] | None):
    cards = []
    used = False
    for i, slot in enumerate(get_formation_slots("4-3-3")):
        effect = None
        if skill and not used and slot.ideal_position == skill[1]:
            effect, used = _effect(skill[0]), True
        player = _FakePlayer(slot.ideal_position, 75, display_name=f"{slot.ideal_position.value}{i}")
        cards.append((_Card(id=i, player_id=i, player=player, skill=effect), slot))
    side = matchup.build_side(cards, "BALANCED", "WING_PLAY")
    lineup = [
        {"club_card_id": c.id, "name": c.player.display_name, "rating": c.player.rating,
         "position": c.player.position.value, "category": slot.category, **({"skill": c.skill} if c.skill else {})}
        for c, slot in cards
    ]
    return side, lineup


def run(label: str, skill, matches: int, seed: int) -> None:
    random.seed(seed)
    goals_a, goals_b, decisive = [], [], 0
    for _ in range(matches):
        side_a, lineup_a = _side(skill)
        side_b, lineup_b = _side(None)
        result = engine.simulate_match(side_a, side_b, lineup_a, lineup_b, _Config())
        goals_a.append(result.score_a)
        goals_b.append(result.score_b)
        for event in result.event_log:
            decisive += sum(1 for n in (event.get("payload") or {}).get("skills", []) if n["decisive"])
    print(f"{label:<28} goals A {statistics.mean(goals_a):.3f}  B {statistics.mean(goals_b):.3f}  "
          f"decisive/match {decisive / matches:.3f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matches", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=20261010)
    args = parser.parse_args()
    run("baseline", None, args.matches, args.seed)
    for code, position, _side_label in SCENARIOS:
        run(f"A: {code} III ({position.value})", (code, position), args.matches, args.seed)


if __name__ == "__main__":
    main()
