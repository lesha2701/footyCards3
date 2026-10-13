"""«Футбольный магнат» — pure rules engine (no DB, no clock).

A short economic board game for 4 seats on a 24-cell loop: clubs grouped
by country, stadiums, event cards («VAR», «Трансферное окно»), a federation
fine, «Дисквалификация» (jail) and a «Стартовый свисток» salary. Everything
lives in one JSON-serialisable `state` dict that magnate_service stores in
MagnateMatch.server_state.

Randomness: every dice roll / deck shuffle comes from
`random.Random(f"magnate:{seed}:{n}")` with a per-match seed and a counter
kept in the state, so a match is fully reproducible from its seed and the
sequence of actions (tests pass `dice=` to force a roll instead).

Economy numbers come in through `settings` (built from GameConfig by the
service) and the board/cards snapshot, so admin edits never change a match
that is already running.
"""
import copy
import random
from typing import Callable, Optional

BOARD_CELLS = 32  # default board; admin boards may use any multiple of 4 in 20–40
MIN_CELLS, MAX_CELLS = 20, 40
MAX_LEVEL = 4  # 1–3 = «Трибуны», 4 = «Арена»
LOG_KEEP = 60
PROPERTY_TYPES = frozenset({"club", "stadium"})
CELL_TYPES = frozenset({"start", "club", "stadium", "var", "transfer", "fine", "jail", "break", "go_to_jail"})
DECKS = ("var", "transfer")
CARD_KINDS = frozenset({
    "money", "move_to", "move_by", "nearest_stadium", "jail", "jail_card", "collect_each", "pay_each", "repairs",
})


class EngineError(Exception):
    pass


# ---------------------------------------------------------------------------
# Default board & cards (used while GameConfig.magnate_board / _cards is NULL)
# ---------------------------------------------------------------------------

def _club(
    name: str, group: int, price: int, rent: list[int], build_cost: int,
    short: Optional[str] = None, colors: Optional[list[str]] = None,
) -> dict:
    cell = {"type": "club", "name": name, "group": group, "price": price, "rent": rent, "build_cost": build_cost}
    if short:
        cell["short"] = short
    if colors:
        cell["colors"] = colors
    return cell


def _stadium(name: str, price: int = 200) -> dict:
    return {"type": "stadium", "name": name, "price": price}


# 32 cells on the perimeter of a 9×9 grid (8 per side): corners at 0 / 8 /
# 16 / 24, a stadium in the middle of every side, eight country groups from
# the Netherlands (cheapest) to Spain (Барселона, Реал — the most expensive).
DEFAULT_BOARD: dict = {
    "groups": [
        {"name": "Нидерланды", "color": "#f97316"},
        {"name": "Португалия", "color": "#16a34a"},
        {"name": "Франция", "color": "#2563eb"},
        {"name": "Италия", "color": "#0ea5e9"},
        {"name": "Германия", "color": "#eab308"},
        {"name": "Лондон", "color": "#dc2626"},
        {"name": "Манчестер", "color": "#a855f7"},
        {"name": "Испания", "color": "#f59e0b"},
    ],
    "cells": [
        {"type": "start", "name": "Стартовый свисток"},
        _club("Фейеноорд", 0, 60, [4, 20, 60, 180, 320], 50, "ФЕЙ", ["#e11d48", "#ffffff"]),
        {"type": "transfer", "name": "Трансферное окно"},
        _club("Аякс", 0, 70, [5, 25, 75, 210, 350], 50, "АЯК", ["#ffffff", "#dc2626"]),
        _stadium("Стадион «Север»"),
        _club("Порту", 1, 100, [6, 30, 90, 270, 450], 50, "ПОР", ["#1d4ed8", "#ffffff"]),
        {"type": "var", "name": "VAR"},
        _club("Бенфика", 1, 120, [8, 40, 100, 300, 500], 50, "БЕН", ["#dc2626", "#ffffff"]),
        {"type": "jail", "name": "Дисквалификация"},
        _club("Марсель", 2, 140, [10, 50, 150, 450, 700], 100, "МАР", ["#38bdf8", "#ffffff"]),
        {"type": "fine", "name": "Налог на зарплаты", "amount": 150},
        _club("ПСЖ", 2, 160, [12, 60, 180, 500, 800], 100, "ПСЖ", ["#1e3a8a", "#dc2626"]),
        _stadium("Стадион «Восток»"),
        _club("Ювентус", 3, 180, [14, 70, 200, 550, 900], 100, "ЮВЕ", ["#111827", "#ffffff"]),
        _club("Интер", 3, 180, [14, 70, 200, 550, 900], 100, "ИНТ", ["#1d4ed8", "#111827"]),
        _club("Милан", 3, 200, [16, 80, 220, 600, 1000], 100, "МИЛ", ["#dc2626", "#111827"]),
        {"type": "break", "name": "Перерыв"},
        _club("Боруссия", 4, 220, [18, 90, 250, 700, 1050], 150, "БВБ", ["#facc15", "#111827"]),
        {"type": "var", "name": "VAR"},
        _club("Бавария", 4, 240, [20, 100, 300, 750, 1100], 150, "БАВ", ["#dc2626", "#ffffff"]),
        _stadium("Стадион «Юг»"),
        _club("Челси", 5, 260, [22, 110, 330, 800, 1150], 150, "ЧЕЛ", ["#1d4ed8", "#ffffff"]),
        _club("Арсенал", 5, 260, [22, 110, 330, 800, 1150], 150, "АРС", ["#dc2626", "#ffffff"]),
        _club("Ливерпуль", 5, 280, [24, 120, 360, 850, 1200], 150, "ЛИВ", ["#b91c1c", "#facc15"]),
        {"type": "go_to_jail", "name": "Красная карточка"},
        _club("Ман Юнайтед", 6, 300, [26, 130, 390, 900, 1275], 200, "МЮ", ["#dc2626", "#facc15"]),
        _club("Ман Сити", 6, 320, [28, 150, 450, 1000, 1400], 200, "МС", ["#7dd3fc", "#ffffff"]),
        {"type": "transfer", "name": "Трансферное окно"},
        _stadium("Стадион «Запад»"),
        _club("Барселона", 7, 350, [35, 175, 500, 1100, 1500], 200, "БАР", ["#1e3a8a", "#b91c1c"]),
        {"type": "fine", "name": "Штраф федерации"},
        _club("Реал", 7, 400, [50, 200, 600, 1400, 2000], 200, "РЕА", ["#ffffff", "#a78bfa"]),
    ],
}

# The original 24-cell (7×7) board — still a valid admin-saved layout and
# the board the engine unit tests are written against.
BOARD_24: dict = {
    "groups": [
        {"name": "Нидерланды", "color": "#f97316"},
        {"name": "Португалия", "color": "#22c55e"},
        {"name": "Франция", "color": "#3b82f6"},
        {"name": "Германия", "color": "#eab308"},
        {"name": "Италия", "color": "#06b6d4"},
        {"name": "Англия", "color": "#ef4444"},
    ],
    "cells": [
        {"type": "start", "name": "Стартовый свисток"},
        _club("Амстердам", 0, 60, [4, 20, 60, 180, 320], 50),
        _club("Роттердам", 0, 70, [5, 25, 75, 210, 350], 50),
        _stadium("Стадион «Север»"),
        _club("Порту", 1, 100, [6, 30, 90, 270, 450], 50),
        _club("Лиссабон", 1, 120, [8, 40, 100, 300, 500], 50),
        {"type": "jail", "name": "Дисквалификация"},
        _club("Марсель", 2, 140, [10, 50, 150, 450, 700], 100),
        {"type": "var", "name": "VAR"},
        _club("Лион", 2, 140, [10, 50, 150, 450, 700], 100),
        _stadium("Стадион «Восток»"),
        _club("Париж", 2, 160, [12, 60, 180, 500, 800], 100),
        {"type": "break", "name": "Перерыв"},
        _club("Дортмунд", 3, 180, [14, 70, 200, 550, 900], 100),
        _club("Мюнхен", 3, 200, [16, 80, 220, 600, 1000], 100),
        {"type": "transfer", "name": "Трансферное окно"},
        _stadium("Стадион «Юг»"),
        _club("Турин", 4, 220, [18, 90, 250, 700, 1050], 150),
        {"type": "go_to_jail", "name": "Красная карточка"},
        _club("Милан", 4, 240, [20, 100, 300, 750, 1100], 150),
        {"type": "fine", "name": "Штраф федерации"},
        _club("Ливерпуль", 5, 300, [26, 130, 390, 900, 1275], 200),
        _stadium("Стадион «Запад»"),
        _club("Манчестер", 5, 350, [35, 175, 500, 1100, 1500], 200),
    ],
}


DEFAULT_CARDS: dict = {
    "var": [
        {"text": "VAR засчитал гол! Беги на «Стартовый свисток»", "kind": "move_to", "cell": 0},
        {"text": "VAR отменил гол — назад на 3 клетки", "kind": "move_by", "steps": -3},
        {"text": "Красная по видеоповтору — в дисквалификацию", "kind": "jail"},
        {"text": "Апелляция удовлетворена: карточка выхода из дисквалификации", "kind": "jail_card"},
        {"text": "Назначен пенальти — вперёд на 3 клетки", "kind": "move_by", "steps": 3},
        {"text": "Выездной матч — на ближайший стадион", "kind": "nearest_stadium"},
        {"text": "Судья ошибся в твою пользу", "kind": "money", "amount": 100},
        {"text": "Штраф за симуляцию", "kind": "money", "amount": -50},
        {"text": "Эль Класико! Отправляйся на «Барселону»", "kind": "move_to", "cell": 29},
    ],
    "transfer": [
        {"text": "Продал запасного форварда", "kind": "money", "amount": 150},
        {"text": "Агент взял комиссию", "kind": "money", "amount": -100},
        {"text": "Бонус за плей-офф: каждый соперник платит тебе", "kind": "collect_each", "amount": 25},
        {"text": "Благотворительный матч: заплати каждому сопернику", "kind": "pay_each", "amount": 25},
        {"text": "Ремонт газона: за каждую Трибуну и Арену", "kind": "repairs", "per_tribune": 40, "per_arena": 115},
        {"text": "Продажа клубных маек", "kind": "money", "amount": 100},
        {"text": "Медкомиссия", "kind": "money", "amount": -50},
        {"text": "Призовые за кубок", "kind": "money", "amount": 200},
        {"text": "Новый спонсор на футболках", "kind": "money", "amount": 150},
    ],
}


# ---------------------------------------------------------------------------
# Validation of admin-edited board / cards
# ---------------------------------------------------------------------------

def _non_negative_int(value, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise EngineError(f"{what}: нужно целое число ≥ 0")
    return value


def validate_board(board: dict) -> dict:
    """Returns a cleaned copy or raises EngineError with a readable reason."""
    if not isinstance(board, dict):
        raise EngineError("Поле должно быть объектом с groups и cells")
    groups, cells = board.get("groups"), board.get("cells")
    if not isinstance(groups, list) or not groups:
        raise EngineError("Нужна хотя бы одна группа клубов")
    if not isinstance(cells, list) or not MIN_CELLS <= len(cells) <= MAX_CELLS or len(cells) % 4:
        raise EngineError(f"Клеток на поле должно быть кратно 4, от {MIN_CELLS} до {MAX_CELLS}")
    clean_groups = []
    for i, g in enumerate(groups):
        if not isinstance(g, dict) or not str(g.get("name", "")).strip():
            raise EngineError(f"Группа {i + 1}: нужно название")
        clean_groups.append({"name": str(g["name"]).strip()[:32], "color": str(g.get("color") or "#64748b")[:16]})
    clean_cells = []
    for i, c in enumerate(cells):
        if not isinstance(c, dict) or c.get("type") not in CELL_TYPES:
            raise EngineError(f"Клетка {i}: неизвестный тип")
        name = str(c.get("name", "")).strip()
        if not name:
            raise EngineError(f"Клетка {i}: нужно название")
        out = {"type": c["type"], "name": name[:32]}
        if c.get("short"):
            out["short"] = str(c["short"]).strip()[:4]
        if isinstance(c.get("colors"), list) and c["colors"]:
            out["colors"] = [str(x)[:16] for x in c["colors"][:2]]
        if c["type"] == "fine" and c.get("amount") is not None:
            out["amount"] = _non_negative_int(c.get("amount"), f"Клетка {i} «{name}», сумма")
        if c["type"] in PROPERTY_TYPES:
            out["price"] = _non_negative_int(c.get("price"), f"Клетка {i} «{name}», цена")
            if out["price"] <= 0:
                raise EngineError(f"Клетка {i} «{name}»: цена должна быть больше 0")
        if c["type"] == "club":
            group = c.get("group")
            if not isinstance(group, int) or not 0 <= group < len(clean_groups):
                raise EngineError(f"Клетка {i} «{name}»: неверная группа")
            rent = c.get("rent")
            if not isinstance(rent, list) or len(rent) != MAX_LEVEL + 1:
                raise EngineError(f"Клетка {i} «{name}»: аренда — {MAX_LEVEL + 1} чисел (база, 1–3 трибуны, арена)")
            out["group"] = group
            out["rent"] = [_non_negative_int(r, f"Клетка {i} «{name}», аренда") for r in rent]
            out["build_cost"] = _non_negative_int(c.get("build_cost"), f"Клетка {i} «{name}», стоимость стройки")
        clean_cells.append(out)
    types = [c["type"] for c in clean_cells]
    if clean_cells[0]["type"] != "start" or types.count("start") != 1:
        raise EngineError("«Стартовый свисток» должен быть одной клеткой с индексом 0")
    if types.count("jail") != 1:
        raise EngineError("На поле должна быть ровно одна клетка «Дисквалификация»")
    for gi, g in enumerate(clean_groups):
        if not any(c["type"] == "club" and c["group"] == gi for c in clean_cells):
            raise EngineError(f"В группе «{g['name']}» нет ни одного клуба")
    return {"groups": clean_groups, "cells": clean_cells}


def validate_cards(cards: dict) -> dict:
    if not isinstance(cards, dict):
        raise EngineError("Карточки должны быть объектом с колодами var и transfer")
    out = {}
    for deck in DECKS:
        items = cards.get(deck)
        if not isinstance(items, list) or not items:
            raise EngineError(f"Колода «{deck}» пуста")
        clean = []
        for i, card in enumerate(items):
            if not isinstance(card, dict) or card.get("kind") not in CARD_KINDS:
                raise EngineError(f"Колода «{deck}», карточка {i + 1}: неизвестный тип")
            text = str(card.get("text", "")).strip()
            if not text:
                raise EngineError(f"Колода «{deck}», карточка {i + 1}: нужен текст")
            c = {"kind": card["kind"], "text": text[:120]}
            kind = card["kind"]
            if kind == "money":
                if not isinstance(card.get("amount"), int) or isinstance(card.get("amount"), bool):
                    raise EngineError(f"Колода «{deck}», карточка {i + 1}: amount — целое число")
                c["amount"] = card["amount"]
            elif kind == "move_to":
                cell = card.get("cell")
                if not isinstance(cell, int) or not 0 <= cell < MAX_CELLS:
                    raise EngineError(f"Колода «{deck}», карточка {i + 1}: cell — номер клетки")
                c["cell"] = cell
            elif kind == "move_by":
                steps = card.get("steps")
                if not isinstance(steps, int) or steps == 0 or abs(steps) >= MIN_CELLS:
                    raise EngineError(f"Колода «{deck}», карточка {i + 1}: steps — ненулевое число клеток")
                c["steps"] = steps
            elif kind in ("collect_each", "pay_each"):
                c["amount"] = _non_negative_int(card.get("amount"), f"Колода «{deck}», карточка {i + 1}")
            elif kind == "repairs":
                c["per_tribune"] = _non_negative_int(card.get("per_tribune"), f"Колода «{deck}», карточка {i + 1}")
                c["per_arena"] = _non_negative_int(card.get("per_arena"), f"Колода «{deck}», карточка {i + 1}")
            clean.append(c)
        out[deck] = clean
    return out


# ---------------------------------------------------------------------------
# State construction
# ---------------------------------------------------------------------------

def _rng(state: dict) -> random.Random:
    rng = random.Random(f"magnate:{state['seed']}:{state['rng_n']}")
    state["rng_n"] += 1
    return rng


def new_state(board: dict, cards: dict, settings: dict, players: list[dict], seed: str) -> dict:
    """`players`: [{"name", "is_bot", "user_id"}] in seat order (seat = index).
    `settings` keys: start_money, pass_start_bonus, jail_fine, max_jail_turns,
    fine_amount, building_sell_pct, max_rounds, stadium_rents,
    bot_buy_reserve, bot_build_reserve."""
    if not 2 <= len(players) <= 4:
        raise EngineError("В партии должно быть от 2 до 4 игроков")
    cells = copy.deepcopy(board["cells"])
    state = {
        "cells": cells, "groups": copy.deepcopy(board["groups"]), "settings": dict(settings),
        "cards": copy.deepcopy(cards), "seed": seed, "rng_n": 0,
        "players": [
            {
                "seat": i, "name": p["name"], "is_bot": bool(p.get("is_bot")), "user_id": p.get("user_id"),
                "cash": settings["start_money"], "pos": 0, "in_jail": False, "jail_turns": 0, "jail_cards": 0,
                "bankrupt": False, "bankrupt_order": None, "missed": 0, "left": False,
            }
            for i, p in enumerate(players)
        ],
        "owner": [None] * len(cells), "level": [0] * len(cells),
        "decks": {}, "deck_pos": {d: 0 for d in DECKS},
        "turn": 0, "first_seat": 0, "phase": "roll", "doubles": 0, "extra_turn": False, "pending": None,
        "round": 1, "turn_n": 1, "roll_n": 0, "last_roll": None, "log": [], "log_n": 0,
        "finished": False, "finish_reason": None,
    }
    for deck in DECKS:
        order = list(range(len(state["cards"][deck])))
        _rng(state).shuffle(order)
        state["decks"][deck] = order
    first = _rng(state).randrange(len(players))
    state["turn"] = state["first_seat"] = first
    log(state, None, f"Партия началась. Первым ходит {state['players'][first]['name']}", "info")
    return state


def log(state: dict, seat: Optional[int], text: str, kind: str = "info") -> None:
    state["log_n"] += 1
    state["log"].append({"n": state["log_n"], "seat": seat, "text": text, "kind": kind})
    if len(state["log"]) > LOG_KEEP:
        del state["log"][: len(state["log"]) - LOG_KEEP]


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def group_cells(state: dict, group: int) -> list[int]:
    return [i for i, c in enumerate(state["cells"]) if c["type"] == "club" and c["group"] == group]


def owns_group(state: dict, seat: int, group: int) -> bool:
    return all(state["owner"][i] == seat for i in group_cells(state, group))


def rent_for(state: dict, cell: int) -> int:
    c = state["cells"][cell]
    owner = state["owner"][cell]
    if owner is None:
        return 0
    if c["type"] == "stadium":
        owned = sum(1 for i, x in enumerate(state["cells"]) if x["type"] == "stadium" and state["owner"][i] == owner)
        rents = state["settings"]["stadium_rents"]
        return rents[min(owned, len(rents)) - 1] if owned and rents else 0
    level = state["level"][cell]
    if level == 0:
        return c["rent"][0] * (2 if owns_group(state, owner, c["group"]) else 1)
    return c["rent"][level]


def build_options(state: dict, seat: int) -> list[int]:
    """Clubs `seat` may add a «Трибуна»/«Арена» to right now: the whole
    group owned, not maxed out, affordable. No even-building rule (v1)."""
    cash = state["players"][seat]["cash"]
    return [
        i for i, c in enumerate(state["cells"])
        if c["type"] == "club" and state["owner"][i] == seat and state["level"][i] < MAX_LEVEL
        and owns_group(state, seat, c["group"]) and cash >= c["build_cost"]
    ]


def capital(state: dict, seat: int) -> int:
    """Cash + purchase price of everything owned + what was spent on buildings."""
    total = state["players"][seat]["cash"]
    for i, c in enumerate(state["cells"]):
        if state["owner"][i] == seat:
            total += c["price"] + state["level"][i] * c.get("build_cost", 0)
    return total


def alive_seats(state: dict) -> list[int]:
    return [p["seat"] for p in state["players"] if not p["bankrupt"]]


def standings(state: dict) -> list[int]:
    """Seats from 1st place down: survivors by capital (then cash, then
    seat), then the bankrupt — the later someone went bust, the higher."""
    alive = sorted(alive_seats(state), key=lambda s: (-capital(state, s), -state["players"][s]["cash"], s))
    busted = sorted(
        (p for p in state["players"] if p["bankrupt"]), key=lambda p: (-(p["bankrupt_order"] or 0), p["seat"])
    )
    return alive + [p["seat"] for p in busted]


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------

def _liquidate(state: dict, seat: int, need: int) -> None:
    """Sells buildings back to the bank (building_sell_pct of the cost),
    biggest first, until `seat` has `need` cash or nothing is left to sell."""
    p = state["players"][seat]
    pct = state["settings"].get("building_sell_pct", 50)
    while p["cash"] < need:
        built = [i for i in range(len(state["cells"])) if state["owner"][i] == seat and state["level"][i] > 0]
        if not built:
            return
        cell = max(built, key=lambda i: (state["level"][i], state["cells"][i]["build_cost"], i))
        state["level"][cell] -= 1
        refund = state["cells"][cell]["build_cost"] * pct // 100
        p["cash"] += refund
        what = "Арену" if state["level"][cell] == MAX_LEVEL - 1 else "Трибуну"
        log(state, seat, f"{p['name']} продаёт {what} в «{state['cells'][cell]['name']}» за {refund}", "build")


def _bankrupt(state: dict, seat: int, creditor: Optional[int]) -> None:
    p = state["players"][seat]
    p["bankrupt"] = True
    p["bankrupt_order"] = sum(1 for x in state["players"] if x["bankrupt"])
    p["in_jail"] = False
    for i in range(len(state["cells"])):
        if state["owner"][i] == seat:
            state["owner"][i] = None
            state["level"][i] = 0
    to = f" — всё оставшееся уходит к {state['players'][creditor]['name']}" if creditor is not None else ""
    log(state, seat, f"{p['name']} банкрот и выбывает{to}. Его клубы возвращаются в банк", "bankrupt")


def pay(state: dict, seat: int, amount: int, to: Optional[int] = None, reason: str = "") -> bool:
    """`seat` pays `amount` to `to` (None = bank). Sells buildings if short;
    if still short, hands over everything and goes bankrupt (returns False)."""
    if amount <= 0:
        return True
    p = state["players"][seat]
    if p["cash"] < amount:
        _liquidate(state, seat, amount)
    receiver = state["players"][to] if to is not None else None
    if p["cash"] >= amount:
        p["cash"] -= amount
        if receiver is not None:
            receiver["cash"] += amount
        target = f" игроку {receiver['name']}" if receiver is not None else ""
        log(state, seat, f"{p['name']} платит {amount}{target}{f' — {reason}' if reason else ''}", "pay")
        return True
    if receiver is not None:
        receiver["cash"] += p["cash"]
    p["cash"] = 0
    _bankrupt(state, seat, to)
    return False


def _receive(state: dict, seat: int, amount: int, reason: str) -> None:
    p = state["players"][seat]
    p["cash"] += amount
    log(state, seat, f"{p['name']} получает {amount} — {reason}", "income")


# ---------------------------------------------------------------------------
# Movement & landing
# ---------------------------------------------------------------------------

def _pass_start(state: dict, seat: int) -> None:
    _receive(state, seat, state["settings"]["pass_start_bonus"], "круг через «Стартовый свисток»")


def _send_to_jail(state: dict, seat: int) -> None:
    p = state["players"][seat]
    p["pos"] = next(i for i, c in enumerate(state["cells"]) if c["type"] == "jail")
    p["in_jail"] = True
    p["jail_turns"] = 0
    state["extra_turn"] = False
    state["doubles"] = 0
    log(state, seat, f"{p['name']} дисквалифицирован", "jail")


def _move_by(state: dict, seat: int, steps: int, depth: int = 0) -> None:
    p = state["players"][seat]
    n = len(state["cells"])
    old = p["pos"]
    p["pos"] = (old + steps) % n
    if steps > 0 and old + steps >= n:
        _pass_start(state, seat)
    _land(state, seat, depth)


def _move_to(state: dict, seat: int, target: int, depth: int = 0) -> None:
    p = state["players"][seat]
    if target <= p["pos"]:
        _pass_start(state, seat)
    p["pos"] = target
    _land(state, seat, depth)


def _land(state: dict, seat: int, depth: int = 0) -> None:
    p = state["players"][seat]
    cell = state["cells"][p["pos"]]
    t = cell["type"]
    log(state, seat, f"{p['name']} на клетке «{cell['name']}»", "move")
    if t in PROPERTY_TYPES:
        owner = state["owner"][p["pos"]]
        if owner is None:
            if p["cash"] >= cell["price"]:
                state["phase"] = "buy"
                state["pending"] = {"cell": p["pos"]}
            else:
                log(state, seat, f"Не хватает денег на «{cell['name']}» ({cell['price']})", "info")
        elif owner != seat:
            pay(state, seat, rent_for(state, p["pos"]), owner, f"аренда «{cell['name']}»")
    elif t in DECKS:
        if depth < 3:
            _draw_card(state, seat, t, depth)
    elif t == "fine":
        pay(state, seat, cell.get("amount", state["settings"]["fine_amount"]), None, cell["name"].lower())
    elif t == "go_to_jail":
        _send_to_jail(state, seat)


def _draw_card(state: dict, seat: int, deck: str, depth: int) -> None:
    order = state["decks"][deck]
    idx = order[state["deck_pos"][deck] % len(order)]
    state["deck_pos"][deck] += 1
    card = state["cards"][deck][idx]
    p = state["players"][seat]
    title = "VAR" if deck == "var" else "Трансферное окно"
    log(state, seat, f"{title}: {card['text']}", "card")
    kind = card["kind"]
    if kind == "money":
        if card["amount"] >= 0:
            _receive(state, seat, card["amount"], title)
        else:
            pay(state, seat, -card["amount"], None, title)
    elif kind == "move_to":
        _move_to(state, seat, card["cell"] % len(state["cells"]), depth + 1)
    elif kind == "move_by":
        _move_by(state, seat, card["steps"], depth + 1)
    elif kind == "nearest_stadium":
        n = len(state["cells"])
        for step in range(1, n + 1):
            target = (p["pos"] + step) % n
            if state["cells"][target]["type"] == "stadium":
                _move_to(state, seat, target, depth + 1)
                break
    elif kind == "jail":
        _send_to_jail(state, seat)
    elif kind == "jail_card":
        p["jail_cards"] += 1
    elif kind == "collect_each":
        for other in alive_seats(state):
            if other != seat:
                pay(state, other, card["amount"], seat, title)
    elif kind == "pay_each":
        for other in alive_seats(state):
            if other != seat and not p["bankrupt"]:
                pay(state, seat, card["amount"], other, title)
    elif kind == "repairs":
        tribunes = sum(min(lv, MAX_LEVEL - 1) for i, lv in enumerate(state["level"]) if state["owner"][i] == seat and lv < MAX_LEVEL)
        arenas = sum(1 for i, lv in enumerate(state["level"]) if state["owner"][i] == seat and lv == MAX_LEVEL)
        pay(state, seat, tribunes * card["per_tribune"] + arenas * card["per_arena"], None, title)


# ---------------------------------------------------------------------------
# Turn flow
# ---------------------------------------------------------------------------

def finish(state: dict, reason: str) -> None:
    if state["finished"]:
        return
    state["finished"] = True
    state["finish_reason"] = reason
    state["phase"] = "finished"
    state["pending"] = None
    labels = {
        "last_standing": "остался последний не обанкротившийся",
        "rounds": "сыграны все круги",
        "time": "вышло время партии",
        "abandoned": "все игроки покинули партию",
    }
    winner = state["players"][standings(state)[0]]["name"]
    log(state, None, f"Партия окончена: {labels.get(reason, reason)}. Победитель — {winner}", "finish")


def _next_turn(state: dict) -> None:
    state["pending"] = None
    state["doubles"] = 0
    state["extra_turn"] = False
    if len(alive_seats(state)) <= 1:
        finish(state, "last_standing")
        return
    n = len(state["players"])
    cur = state["turn"]
    nxt = cur
    for _ in range(n):
        nxt = (nxt + 1) % n
        if not state["players"][nxt]["bankrupt"]:
            break
    first = state["first_seat"]
    if (nxt - first) % n <= (cur - first) % n:
        state["round"] += 1
        if state["round"] > state["settings"]["max_rounds"]:
            state["round"] = state["settings"]["max_rounds"]
            finish(state, "rounds")
            return
    state["turn"] = nxt
    state["phase"] = "roll"
    state["turn_n"] += 1


def _continue(state: dict, seat: int) -> None:
    """After a landing (or a buy decision) is fully resolved."""
    if state["finished"]:
        return
    if len(alive_seats(state)) <= 1:
        finish(state, "last_standing")
        return
    if state["phase"] == "buy":
        return  # waiting for the buy decision
    p = state["players"][seat]
    if p["bankrupt"] or p["in_jail"]:
        _next_turn(state)
    elif state["extra_turn"]:
        state["phase"] = "roll"
    elif build_options(state, seat):
        state["phase"] = "end"
    else:
        _next_turn(state)


def _roll_dice(state: dict) -> list[int]:
    rng = _rng(state)
    return [rng.randint(1, 6), rng.randint(1, 6)]


def _do_roll(state: dict, seat: int, dice: Optional[list[int]]) -> None:
    p = state["players"][seat]
    d = list(dice) if dice else _roll_dice(state)
    total, is_double = d[0] + d[1], d[0] == d[1]
    state["roll_n"] += 1
    state["last_roll"] = {"seat": seat, "dice": d, "n": state["roll_n"]}
    state["phase"] = "moving"
    log(state, seat, f"{p['name']} бросает {d[0]} и {d[1]}{' — дубль!' if is_double else ''}", "roll")
    s = state["settings"]
    if p["in_jail"]:
        state["extra_turn"] = False
        if is_double:
            p["in_jail"] = False
            p["jail_turns"] = 0
            log(state, seat, f"Дубль — {p['name']} снова в игре", "jail")
            _move_by(state, seat, total)
            _continue(state, seat)
            return
        p["jail_turns"] += 1
        if p["jail_turns"] < s["max_jail_turns"]:
            log(state, seat, f"{p['name']} пропускает ход в дисквалификации", "jail")
            _next_turn(state)
            return
        if not pay(state, seat, s["jail_fine"], None, "штраф за выход из дисквалификации"):
            _next_turn(state)
            return
        p["in_jail"] = False
        p["jail_turns"] = 0
        _move_by(state, seat, total)
        _continue(state, seat)
        return
    if is_double:
        state["doubles"] += 1
        if state["doubles"] >= 3:
            log(state, seat, "Третий дубль подряд!", "jail")
            _send_to_jail(state, seat)
            _next_turn(state)
            return
    state["extra_turn"] = is_double
    _move_by(state, seat, total)
    _continue(state, seat)


def apply_action(
    state: dict, seat: int, action: str, cell: Optional[int] = None, dice: Optional[list[int]] = None,
) -> None:
    """The only way a match moves forward. Raises EngineError on anything
    out of turn / out of phase / against the rules; `dice` is for tests."""
    if state["finished"]:
        raise EngineError("Партия уже завершена")
    if state["turn"] != seat:
        raise EngineError("Сейчас ходит другой игрок")
    p = state["players"][seat]
    phase = state["phase"]
    if action == "roll":
        if phase != "roll":
            raise EngineError("Сейчас нельзя бросать кубики")
        _do_roll(state, seat, dice)
    elif action in ("buy", "skip"):
        if phase != "buy" or not state.get("pending"):
            raise EngineError("Сейчас нечего покупать")
        target = state["pending"]["cell"]
        c = state["cells"][target]
        state["pending"] = None
        state["phase"] = "moving"
        if action == "buy":
            if p["cash"] < c["price"]:
                raise EngineError("Не хватает денег")
            p["cash"] -= c["price"]
            state["owner"][target] = seat
            log(state, seat, f"{p['name']} покупает «{c['name']}» за {c['price']}", "buy")
        else:
            log(state, seat, f"{p['name']} не покупает «{c['name']}»", "info")
        _continue(state, seat)
    elif action == "build":
        if phase not in ("roll", "end"):
            raise EngineError("Строить можно до броска или в конце хода")
        if cell is None or cell not in build_options(state, seat):
            raise EngineError("Здесь сейчас нельзя строить")
        c = state["cells"][cell]
        p["cash"] -= c["build_cost"]
        state["level"][cell] += 1
        what = "Арену" if state["level"][cell] == MAX_LEVEL else f"Трибуну №{state['level'][cell]}"
        log(state, seat, f"{p['name']} строит {what} в «{c['name']}» за {c['build_cost']}", "build")
    elif action == "end":
        if phase != "end":
            raise EngineError("Сначала сделай ход")
        _next_turn(state)
    elif action in ("pay_bail", "use_card"):
        if phase != "roll" or not p["in_jail"]:
            raise EngineError("Ты не в дисквалификации")
        if action == "use_card":
            if p["jail_cards"] <= 0:
                raise EngineError("Нет карточки выхода")
            p["jail_cards"] -= 1
            log(state, seat, f"{p['name']} использует карточку апелляции", "jail")
        else:
            if p["cash"] < state["settings"]["jail_fine"]:
                raise EngineError("Не хватает денег на штраф")
            pay(state, seat, state["settings"]["jail_fine"], None, "штраф за выход из дисквалификации")
        p["in_jail"] = False
        p["jail_turns"] = 0
    else:
        raise EngineError("Неизвестное действие")


# ---------------------------------------------------------------------------
# Bot — deterministic, uses only public state (it never peeks at the dice
# or the deck order: those are rolled/drawn only when it acts).
# ---------------------------------------------------------------------------

def bot_action(state: dict, seat: int) -> tuple[str, Optional[int]]:
    s = state["settings"]
    p = state["players"][seat]
    phase = state["phase"]
    if phase == "buy":
        price = state["cells"][state["pending"]["cell"]]["price"]
        return ("buy", None) if p["cash"] - price >= s["bot_buy_reserve"] else ("skip", None)
    options = build_options(state, seat)
    if options:
        cell = min(options, key=lambda i: (state["level"][i], -state["cells"][i]["build_cost"], i))
        if p["cash"] - state["cells"][cell]["build_cost"] >= s["bot_build_reserve"]:
            return "build", cell
    if phase == "end":
        return "end", None
    if p["in_jail"]:
        if p["jail_cards"] > 0:
            return "use_card", None
        if p["cash"] - s["jail_fine"] >= s["bot_buy_reserve"]:
            return "pay_bail", None
    return "roll", None


def play_turn_for(state: dict, seat: int, max_steps: int = 80, dice_fn: Optional[Callable[[], list[int]]] = None) -> int:
    """Plays the rest of `seat`'s turn with the bot policy (used for bot
    seats and for a human whose timer ran out). Returns actions applied."""
    steps = 0
    while not state["finished"] and state["turn"] == seat and steps < max_steps:
        action, cell = bot_action(state, seat)
        dice = dice_fn() if (dice_fn and action == "roll") else None
        apply_action(state, seat, action, cell, dice)
        steps += 1
    return steps


def run_bots(state: dict, max_turns: int = 400) -> None:
    """Advances the match while the seat to move is a bot (or a human that
    was replaced by one)."""
    turns = 0
    while not state["finished"] and state["players"][state["turn"]]["is_bot"] and turns < max_turns:
        play_turn_for(state, state["turn"])
        turns += 1
