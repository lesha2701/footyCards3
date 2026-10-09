"""Balance check for the aerial_master card skill in the player-tournament
engine (tournament_match_engine + club_tactical_matchup_service).

Plays N seeded matches between two identical 75-rated 4-3-3 squads
(WING_PLAY vs BALANCED, so crosses actually happen) for each scenario and
reports goals per match, how often the aerial duel was involved and how
often the skill decided the episode. Usage (from backend/):

    python -m scripts.simulate_aerial_skill --matches 4000
"""
import argparse
import random
import statistics
from dataclasses import dataclass, field

from app.models.enums import Position
from app.services import club_tactical_matchup_service as matchup
from app.services import tournament_match_engine as engine
from app.services.club_formation_service import get_formation_slots
from scripts.simulate_tactical_balance import _Config as _BaseConfig, _FakePlayer


class _Config(_BaseConfig):
    # GameConfig defaults the older balance script's fixture predates.
    club_tactical_tackle_attempt_chance = 0.20
    club_tactical_injury_chance = 0.35


@dataclass
class _Card:
    id: int
    player_id: int
    player: _FakePlayer
    skill: dict | None = None
    diamond_rating_bonus: int = 0


def _effect(level: int) -> dict:
    bonus = {1: 2, 2: 4, 3: 6}[level]
    return {"code": "aerial_master", "level": level, "bonus_pp": bonus, "cap_pp": 8, "floor": 0.02, "ceiling": 0.95}


def _side(skill_positions: dict[Position, int], playstyle: str):
    cards = []
    for i, slot in enumerate(get_formation_slots("4-3-3")):
        level = skill_positions.get(slot.ideal_position)
        skill = _effect(level) if level else None
        player = _FakePlayer(slot.ideal_position, 75, display_name=f"{slot.ideal_position.value}{i}")
        cards.append((_Card(id=i, player_id=i, player=player, skill=skill), slot))
        if level:
            skill_positions = {k: v for k, v in skill_positions.items() if k != slot.ideal_position}  # one card only
    side = matchup.build_side(cards, "BALANCED", playstyle)
    lineup = [
        {"club_card_id": c.id, "name": c.player.display_name, "rating": c.player.rating,
         "position": c.player.position.value, "category": slot.category, **({"skill": c.skill} if c.skill else {})}
        for c, slot in cards
    ]
    return side, lineup


@dataclass
class _Stats:
    goals_a: list[int] = field(default_factory=list)
    goals_b: list[int] = field(default_factory=list)
    duels: int = 0
    decisive: int = 0


def run(name: str, skills_a: dict, skills_b: dict, matches: int, seed: int) -> _Stats:
    random.seed(seed)
    stats = _Stats()
    for _ in range(matches):
        side_a, lineup_a = _side(dict(skills_a), "WING_PLAY")
        side_b, lineup_b = _side(dict(skills_b), "WING_PLAY")
        result = engine.simulate_match(side_a, side_b, lineup_a, lineup_b, _Config())
        stats.goals_a.append(result.score_a)
        stats.goals_b.append(result.score_b)
        for event in result.event_log:
            payload = event.get("payload") or {}
            if payload.get("aerial_duel"):
                stats.duels += 1
            stats.decisive += sum(1 for n in payload.get("skills", []) if n["code"] == "aerial_master" and n["decisive"])
    print(
        f"{name:<44} goals A {statistics.mean(stats.goals_a):.3f}  B {statistics.mean(stats.goals_b):.3f}  "
        f"aerial duels/match {stats.duels / matches:.2f}  skill decisive/match {stats.decisive / matches:.3f}"
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matches", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=20261010)
    args = parser.parse_args()
    n, seed = args.matches, args.seed
    run("baseline (no skills)", {}, {}, n, seed)
    run("A: ST aerial III", {Position.ST: 3}, {}, n, seed)
    run("B: one CB aerial III", {}, {Position.CB: 3}, n, seed)
    run("A: ST III vs B: CB III", {Position.ST: 3}, {Position.CB: 3}, n, seed)
    run("A: ST I", {Position.ST: 1}, {}, n, seed)


if __name__ == "__main__":
    main()
