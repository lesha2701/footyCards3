"""Pure rules engine for «Футбольное Стратего» — no DB, no config lookups;
everything numeric comes in through the state dict (snapshotted from
GameConfig when a match is created, see stratego_service).

Board: N×N, canonical coordinates (row 0 = top). The match creator
("user" side) owns the two bottom rows, the other side ("opponent") the two
top rows. Each viewer gets the board rotated so their own pieces are at the
bottom (see to_viewer / from_viewer).

Pieces (one dict each in state["pieces"]):
  cup         — Кубок: immobile, capturing it wins the match.
  wall        — Стенка: immobile, kills any attacker except the tackler.
  tackler     — Подкатчик: removes walls.
  provocateur — Провокатор: beats the star when it is the one attacking.
  speedster   — Скорость: moves any distance in a straight line.
  star        — Звезда: the side's strongest card.
  regular     — Игрок: plain piece.
Mobile pieces carry `power` (the card's effective rating) and
`rarity_rank`; higher power wins, equal power falls back to rarity, a full
tie removes both pieces.

Layouts are expressed relative to their owner: row 0 = front row, row 1 =
back row, column 0 = owner's left.

Lakes (лужи): on boards of 8×8 and larger, two 2×2 impassable puddles sit
in the two middle rows (see default_lakes) — nobody can stand on or pass
through them, which funnels play into three lanes like classic Stratego.

Piece counts come in as a dict {"wall", "tackler", "speedster", "regular"};
star, provocateur and cup are always exactly one.
"""
from __future__ import annotations

import random
from typing import Optional

CARD_ROLES = ("star", "tackler", "provocateur", "speedster")
IMMOBILE_ROLES = frozenset({"cup", "wall"})
SIDES = ("user", "opponent")
HISTORY_KEEP = 60


class EngineError(ValueError):
    """An illegal move / layout. The service maps it to ConflictError."""


# ---------------------------------------------------------------------------
# Slots & layouts
# ---------------------------------------------------------------------------

def _numbered(role: str, count: int) -> list[str]:
    # A single tackler/speedster keeps the bare role name as its slot key.
    return [role] if count == 1 else [f"{role}_{i}" for i in range(1, count + 1)]


def card_slots(counts: dict) -> list[str]:
    return [
        "star",
        *_numbered("tackler", counts.get("tackler", 1)),
        "provocateur",
        *_numbered("speedster", counts.get("speedster", 1)),
        *(f"regular_{i}" for i in range(1, counts.get("regular", 0) + 1)),
    ]


def all_slots(counts: dict) -> list[str]:
    return ["cup", *(f"wall_{i}" for i in range(1, counts.get("wall", 0) + 1)), *card_slots(counts)]


def piece_total(counts: dict) -> int:
    return len(all_slots(counts))


def default_lakes(board_size: int) -> list[list[int]]:
    """Two 2×2 puddles in the middle rows, mirrored so both sides face the
    same terrain. Only on boards of 8×8+ — smaller boards stay open."""
    if board_size < 8:
        return []
    rows = (board_size // 2 - 1, board_size // 2)
    cols = (1, 2, board_size - 3, board_size - 2)
    return [[r, c] for r in rows for c in cols]


def role_of(slot: str) -> str:
    return slot.split("_", 1)[0]


def other_side(side: str) -> str:
    return "opponent" if side == "user" else "user"


def _home_cells(board_size: int) -> list[tuple[int, int]]:
    return [(r, c) for r in (0, 1) for c in range(board_size)]


def auto_layout(
    slots: list[str], board_size: int, rng: random.Random, fixed: Optional[dict[str, list[int]]] = None,
) -> dict[str, list[int]]:
    """Places every slot not already in `fixed`: the cup on the back row
    (preferring a corner), walls hugging the cup, everything else in random
    free cells. Used for the «Авто» button's server-side twin, for bots, and
    to repair a saved layout that no longer fits the current config."""
    layout = {k: list(v) for k, v in (fixed or {}).items() if k in slots}
    taken = {tuple(v) for v in layout.values()}
    free = [cell for cell in _home_cells(board_size) if cell not in taken]
    if len(free) < len([s for s in slots if s not in layout]):
        raise EngineError("Not enough home cells for every piece")

    def take(cell: tuple[int, int], slot: str) -> None:
        free.remove(cell)
        layout[slot] = [cell[0], cell[1]]

    if "cup" not in layout:
        back = [cell for cell in free if cell[0] == 1]
        corners = [cell for cell in back if cell[1] in (0, board_size - 1)]
        pool = corners if corners and rng.random() < 0.7 else (back or free)
        take(rng.choice(sorted(pool)), "cup")
    cup = tuple(layout["cup"])
    for slot in [s for s in slots if role_of(s) == "wall" and s not in layout]:
        near = [cell for cell in free if abs(cell[0] - cup[0]) + abs(cell[1] - cup[1]) == 1]
        take(rng.choice(sorted(near or free)), slot)
    rest = [s for s in slots if s not in layout]
    rng.shuffle(rest)
    for slot in rest:
        take(rng.choice(sorted(free)), slot)
    return layout


def validate_layout(layout: dict, slots: list[str], board_size: int) -> dict[str, list[int]]:
    if set(layout) != set(slots):
        raise EngineError("Расставь все фишки")
    seen: set[tuple[int, int]] = set()
    clean: dict[str, list[int]] = {}
    for slot, cell in layout.items():
        if not isinstance(cell, (list, tuple)) or len(cell) != 2:
            raise EngineError("Некорректная клетка")
        r, c = int(cell[0]), int(cell[1])
        if r not in (0, 1) or not 0 <= c < board_size:
            raise EngineError("Фишки ставятся только в два своих ближних ряда")
        if (r, c) in seen:
            raise EngineError("Две фишки в одной клетке")
        seen.add((r, c))
        clean[slot] = [r, c]
    return clean


def repair_layout(saved: Optional[dict], slots: list[str], board_size: int, rng: random.Random) -> dict[str, list[int]]:
    """Keeps every still-valid, non-colliding entry of a saved layout and
    auto-places the rest (e.g. after an admin changed the wall count)."""
    fixed: dict[str, list[int]] = {}
    seen: set[tuple[int, int]] = set()
    for slot, cell in (saved or {}).items():
        if slot not in slots or not isinstance(cell, (list, tuple)) or len(cell) != 2:
            continue
        r, c = cell
        if not (isinstance(r, int) and isinstance(c, int)) or r not in (0, 1) or not 0 <= c < board_size:
            continue
        if (r, c) in seen:
            continue
        seen.add((r, c))
        fixed[slot] = [r, c]
    return auto_layout(slots, board_size, rng, fixed)


def to_canonical(side: str, rel_row: int, rel_col: int, board_size: int) -> tuple[int, int]:
    if side == "user":
        return board_size - 2 + rel_row, rel_col
    return 1 - rel_row, board_size - 1 - rel_col


def to_viewer(viewer: str, row: int, col: int, board_size: int) -> tuple[int, int]:
    if viewer == "user":
        return row, col
    return board_size - 1 - row, board_size - 1 - col


from_viewer = to_viewer  # a 180° rotation is its own inverse


def build_pieces(
    side: str, slots: list[str], cards: dict[str, dict], layout: dict[str, list[int]],
    board_size: int, ids: list[int],
) -> list[dict]:
    """`cards` maps every card slot to {"power", "rarity_rank", "card"} — the
    snapshot taken at match start. `ids` are opaque, pre-shuffled piece ids so
    an id never hints at a hidden piece's role."""
    pieces = []
    for slot, piece_id in zip(slots, ids):
        role = role_of(slot)
        info = cards.get(slot) if role not in IMMOBILE_ROLES else None
        row, col = to_canonical(side, layout[slot][0], layout[slot][1], board_size)
        pieces.append({
            "id": piece_id, "side": side, "slot": slot, "role": role,
            "power": info["power"] if info else 0,
            "rarity_rank": info["rarity_rank"] if info else 0,
            "card": info["card"] if info else None,
            "row": row, "col": col, "alive": True, "revealed": False, "moved": False,
        })
    return pieces


# ---------------------------------------------------------------------------
# Combat & moves
# ---------------------------------------------------------------------------

def resolve_combat(attacker: dict, defender: dict) -> str:
    """'attacker' | 'defender' | 'both' — who survives the attack."""
    if defender["role"] == "cup":
        return "attacker"
    if defender["role"] == "wall":
        return "attacker" if attacker["role"] == "tackler" else "defender"
    if attacker["role"] == "provocateur" and defender["role"] == "star":
        return "attacker"
    a = (attacker["power"], attacker["rarity_rank"])
    d = (defender["power"], defender["rarity_rank"])
    if a > d:
        return "attacker"
    if d > a:
        return "defender"
    return "both"


def piece_at(state: dict, row: int, col: int) -> Optional[dict]:
    for p in state["pieces"]:
        if p["alive"] and p["row"] == row and p["col"] == col:
            return p
    return None


def _occupancy(state: dict) -> dict[tuple[int, int], dict]:
    return {(p["row"], p["col"]): p for p in state["pieces"] if p["alive"]}


def legal_moves(state: dict, side: str) -> list[tuple[int, int, int, int, int]]:
    """(piece_id, from_row, from_col, to_row, to_col) for every legal move."""
    n = state["board_size"]
    occ = _occupancy(state)
    lakes = {(r, c) for r, c in state.get("lakes", [])}
    moves = []
    for p in sorted((p for p in state["pieces"] if p["alive"] and p["side"] == side), key=lambda p: p["id"]):
        if p["role"] in IMMOBILE_ROLES:
            continue
        max_steps = n if p["role"] == "speedster" else 1
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            r, c = p["row"], p["col"]
            for _ in range(max_steps):
                r, c = r + dr, c + dc
                if not (0 <= r < n and 0 <= c < n) or (r, c) in lakes:
                    break
                occupant = occ.get((r, c))
                if occupant is not None:
                    if occupant["side"] != side:
                        moves.append((p["id"], p["row"], p["col"], r, c))
                    break
                moves.append((p["id"], p["row"], p["col"], r, c))
    return moves


def strength(state: dict, side: str) -> int:
    return sum(p["power"] for p in state["pieces"] if p["alive"] and p["side"] == side and p["role"] not in IMMOBILE_ROLES)


def _public(p: dict) -> dict:
    return {k: p[k] for k in ("id", "side", "role", "power", "rarity_rank", "card")}


def _strength_outcome(state: dict, reason: str) -> dict:
    us, os_ = strength(state, "user"), strength(state, "opponent")
    winner = "user" if us > os_ else "opponent" if os_ > us else "draw"
    return {"winner": winner, "reason": reason}


def apply_move(state: dict, side: str, fr: int, fc: int, tr: int, tc: int, auto: bool = False) -> Optional[dict]:
    """Validates and applies one move for `side` (canonical coordinates),
    appends it to the history, passes the turn and returns the match outcome
    {"winner": "user"|"opponent"|"draw", "reason"} if this move ended it."""
    if state.get("turn") != side:
        raise EngineError("Сейчас ход соперника")
    if (fr, fc, tr, tc) not in {(m[1], m[2], m[3], m[4]) for m in legal_moves(state, side)}:
        raise EngineError("Так ходить нельзя")

    piece = piece_at(state, fr, fc)
    target = piece_at(state, tr, tc)
    entry: dict = {
        "ply": state["ply"] + 1, "side": side, "piece_id": piece["id"],
        "from": [fr, fc], "to": [tr, tc], "auto": auto, "combat": None,
    }
    if target is None:
        piece["row"], piece["col"] = tr, tc
    else:
        outcome = resolve_combat(piece, target)
        piece["revealed"] = target["revealed"] = True
        entry["combat"] = {"attacker": _public(piece), "defender": _public(target), "survivor": outcome}
        if outcome == "attacker":
            target["alive"] = False
            piece["row"], piece["col"] = tr, tc
        elif outcome == "defender":
            piece["alive"] = False
        else:
            piece["alive"] = target["alive"] = False
    piece["moved"] = True

    state["ply"] += 1
    state["turn"] = other_side(side)
    state["history"].append(entry)
    del state["history"][:-HISTORY_KEEP]

    if target is not None and target["role"] == "cup" and not target["alive"]:
        return {"winner": side, "reason": "cup_captured"}
    nxt = other_side(side)
    if not legal_moves(state, nxt):
        if not legal_moves(state, side):
            return _strength_outcome(state, "no_moves")
        return {"winner": side, "reason": "no_moves"}
    if state["ply"] >= state["move_limit"]:
        return _strength_outcome(state, "move_limit")
    return None


# ---------------------------------------------------------------------------
# Bot
# ---------------------------------------------------------------------------

def _forward(side: str, fr: int, tr: int) -> int:
    return fr - tr if side == "user" else tr - fr


def _known(p: dict) -> bool:
    return p["revealed"]


def _threatened(state: dict, piece: dict, row: int, col: int, ignore_id: Optional[int] = None) -> bool:
    """Whether a *revealed* enemy piece adjacent to (row, col) would beat
    `piece` if it attacked."""
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        enemy = piece_at(state, row + dr, col + dc)
        if (
            enemy is not None and enemy["id"] != ignore_id and enemy["side"] != piece["side"]
            and _known(enemy) and enemy["role"] not in IMMOBILE_ROLES
            and resolve_combat(enemy, piece) == "attacker"
        ):
            return True
    return False


def _score_move(state: dict, side: str, move: tuple[int, int, int, int, int]) -> float:
    pid, fr, fc, tr, tc = move
    piece = next(p for p in state["pieces"] if p["id"] == pid)
    target = piece_at(state, tr, tc)
    if target is not None:
        if _known(target):
            outcome = resolve_combat(piece, target)
            if target["role"] == "cup":
                return 1000
            if outcome == "attacker":
                return 200 + target["power"]
            if outcome == "both":
                return 40 + target["power"] - piece["power"]
            return -200
        # Hidden target — decide only from what a human could also see:
        # whether that piece has ever moved (immobile cup/walls never do).
        if not target["moved"]:
            if piece["role"] == "tackler":
                return 80
            if piece["role"] == "star":
                return -20
            return 30 - piece["power"] / 5
        return 45 - piece["power"] / 4 + (15 if piece["role"] == "star" else 0)

    score = 10.0 * _forward(side, fr, tr)
    if piece["role"] in ("star", "provocateur"):
        score -= 4
    if _threatened(state, piece, tr, tc, ignore_id=None):
        score -= 150
    if _threatened(state, piece, fr, fc):
        score += 100
    return score


def bot_choose_move(state: dict, side: str, rng: random.Random) -> Optional[tuple[int, int, int, int, int]]:
    """Greedy one-ply AI. Uses only information the bot's human opponent
    would have about *its* pieces: an enemy piece's role/power is consulted
    only once revealed (plus the public "has moved" flag), so the bot never
    cheats with the hidden layout. Ties are broken with `rng` over a sorted
    list, so a seeded rng makes it fully deterministic."""
    moves = legal_moves(state, side)
    if not moves:
        return None
    scored = sorted(((round(_score_move(state, side, m), 6), m) for m in moves), key=lambda x: (-x[0], x[1]))
    best = scored[0][0]
    return rng.choice([m for s, m in scored if s == best])
