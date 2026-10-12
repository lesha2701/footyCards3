"""«Задача дня» for Футбольное Стратего: hand-made 8×8 positions where the
player must capture the opponent's Cup within a few moves against the
strong bot. Opponent pieces are shown (it's a puzzle, not a guessing game);
the player's own pieces stay hidden from the bot. The bot is seeded per
puzzle and ply (not per match), so every attempt at a puzzle plays out the
same way — and `solve` can prove each puzzle has a winning line (see
tests/test_stratego.py).

Coordinates are canonical (row 0 = the bot's back row, the player at the
bottom), lakes as on any 8×8 board.
"""
from __future__ import annotations

import copy
import random
from datetime import date
from typing import Optional

from app.services import stratego_engine as engine

BOARD = 8

# (side, role, power, row, col)
PUZZLES: list[dict] = [
    {
        "code": "flank_tackle",
        "title": "Подкат на фланге",
        "description": "Кубок в углу за стенкой. Пробейся по краю — стенку снесёт только Подкатчик.",
        "moves": 3,
        "pieces": [
            ("user", "tackler", 70, 3, 0),
            ("user", "regular", 60, 6, 3),
            ("user", "cup", 0, 7, 7),
            ("opponent", "cup", 0, 0, 0),
            ("opponent", "wall", 0, 1, 0),
            ("opponent", "wall", 0, 0, 1),
            ("opponent", "regular", 65, 1, 6),
            ("opponent", "star", 90, 0, 6),
        ],
    },
    {
        "code": "provocation",
        "title": "Провокация",
        "description": "Звезда соперника охраняет центр. Только Провокатор может выбить её атакой.",
        "moves": 3,
        "pieces": [
            ("user", "provocateur", 50, 3, 4),
            ("user", "regular", 70, 6, 0),
            ("user", "cup", 0, 7, 0),
            ("opponent", "cup", 0, 0, 4),
            ("opponent", "wall", 0, 0, 3),
            ("opponent", "wall", 0, 0, 5),
            ("opponent", "star", 95, 2, 4),
            ("opponent", "regular", 60, 0, 7),
        ],
    },
    {
        "code": "sprint",
        "title": "Рывок по центру",
        "description": "Скорость пробегает сколько угодно свободных клеток. Освободи ей коридор и добеги до Кубка.",
        "moves": 2,
        "pieces": [
            ("user", "speedster", 60, 6, 3),
            ("user", "regular", 55, 5, 3),
            ("user", "cup", 0, 7, 3),
            ("opponent", "cup", 0, 0, 3),
            ("opponent", "wall", 0, 0, 2),
            ("opponent", "wall", 0, 0, 4),
            ("opponent", "regular", 75, 1, 7),
            ("opponent", "regular", 45, 2, 0),
        ],
    },
]

_BY_CODE = {p["code"]: p for p in PUZZLES}


def daily_puzzle(today: date) -> dict:
    return PUZZLES[today.toordinal() % len(PUZZLES)]


def get(code: str) -> Optional[dict]:
    return _BY_CODE.get(code)


def build_state(puzzle: dict) -> dict:
    pieces = []
    for pid, (side, role, power, row, col) in enumerate(puzzle["pieces"], start=1):
        pieces.append({
            "id": pid, "side": side, "slot": role, "role": role, "power": power, "rarity_rank": 0,
            "card": None, "row": row, "col": col, "alive": True,
            "revealed": side == "opponent", "moved": False,
        })
    return {
        "board_size": BOARD, "lakes": engine.default_lakes(BOARD),
        "move_limit": puzzle["moves"] * 2, "pieces": pieces,
        "turn": "user", "ply": 0, "history": [],
        "difficulty": "hard", "seed_key": f"puzzle:{puzzle['code']}",
    }


def bot_rng(seed_key: str, ply: int) -> random.Random:
    return random.Random(f"stratego-bot:{seed_key}:{ply}")


def _play(state: dict, move) -> Optional[dict]:
    """User move + bot reply on a copy-free state; returns the outcome."""
    _, fr, fc, tr, tc = move
    outcome = engine.apply_move(state, "user", fr, fc, tr, tc)
    if outcome is not None:
        return outcome
    reply = engine.bot_choose_move(state, "opponent", bot_rng(state["seed_key"], state["ply"]), state["difficulty"])
    if reply is None:
        return {"winner": "user", "reason": "no_moves"}
    _, fr, fc, tr, tc = reply
    return engine.apply_move(state, "opponent", fr, fc, tr, tc)


def solve(puzzle: dict, max_user_moves: Optional[int] = None) -> Optional[list]:
    """Depth-first search for a line of user moves that captures the cup
    within the puzzle's move budget against the deterministic bot."""
    budget = max_user_moves if max_user_moves is not None else puzzle["moves"]

    def dfs(state: dict, left: int) -> Optional[list]:
        if left == 0:
            return None
        for move in engine.legal_moves(state, "user"):
            nxt = copy.deepcopy(state)
            outcome = _play(nxt, move)
            if outcome is not None:
                if outcome["winner"] == "user" and outcome["reason"] == "cup_captured":
                    return [move]
                continue
            rest = dfs(nxt, left - 1)
            if rest is not None:
                return [move, *rest]
        return None

    return dfs(build_state(puzzle), budget)
