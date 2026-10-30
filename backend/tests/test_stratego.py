import random
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

import app.core.rate_limit as rate_limit_module
from app.models.enums import CardSource, MatchResult, Position, Rarity, StrategoMatchStatus, TransactionType
from app.models.game_config import GameConfig
from app.models.stratego import StrategoMatch
from app.models.transaction import CoinTransaction
from app.services import stratego_engine as engine
from app.services import stratego_service
from app.services.card_creation import create_user_card
from tests.factories import create_player, get_user_by_telegram_id
from tests.test_admin_packs import _admin_auth
from tests.utils import telegram_headers

API = "/api/v1/stratego"


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


@pytest.fixture
def user_moves_first(monkeypatch):
    """Bot matches pick who starts at random, and a bot that starts can take
    a piece on its very first move (a speedster runs the whole column) —
    tests that count or look for the player's pieces start with the user."""
    start = stratego_service._start_play

    def _user_first(state, *args, **kwargs):
        start(state, *args, **kwargs)
        state["turn"] = "user"

    monkeypatch.setattr(stratego_service, "_start_play", _user_first)


SMALL_COUNTS = {"wall": 2, "tackler": 1, "speedster": 1, "regular": 1}


@pytest.fixture(autouse=True)
async def _small_board(request, db_session):
    """Most scenarios below are written for a compact 6×6 board with 8
    pieces (coordinates in the tests assume it); the shipped 8×8 default is
    covered by the tests whose name contains "default_8x8"."""
    if "default_8x8" not in request.node.name:
        config = await db_session.get(GameConfig, 1)
        if config is None:
            config = GameConfig(id=1)
            db_session.add(config)
        config.stratego_board_size = 6
        config.stratego_wall_count = 2
        config.stratego_tackler_count = 1
        config.stratego_speedster_count = 1
        config.stratego_regular_count = 1
        config.stratego_move_limit = 40
        # Rarity rules have their own tests; the factory makes common cards.
        config.stratego_min_rare_cards = 0
        config.stratego_min_common_cards = 0
        await db_session.commit()
    yield


# ---------------------------------------------------------------------------
# Engine helpers
# ---------------------------------------------------------------------------

def _piece(pid, side, role, row, col, power=0, rarity_rank=0, revealed=False, moved=False):
    return {
        "id": pid, "side": side, "slot": role, "role": role, "power": power, "rarity_rank": rarity_rank,
        "card": None, "row": row, "col": col, "alive": True, "revealed": revealed, "moved": moved,
    }


def _state(pieces, turn="user", move_limit=40, ply=0, board_size=6):
    return {"board_size": board_size, "move_limit": move_limit, "pieces": pieces, "turn": turn, "ply": ply, "history": []}


def _by_id(state, pid):
    return next(p for p in state["pieces"] if p["id"] == pid)


# Keep each side owning at least one mobile piece far away so a single
# capture doesn't also end the match via "no moves left".
def _filler():
    return [_piece(90, "user", "regular", 5, 5, power=10), _piece(91, "opponent", "regular", 0, 5, power=10)]


# ---------------------------------------------------------------------------
# Combat rules
# ---------------------------------------------------------------------------

def test_higher_power_attacker_wins_and_moves_in():
    s = _state([_piece(1, "user", "regular", 3, 0, power=80), _piece(2, "opponent", "regular", 2, 0, power=70), *_filler()])
    assert engine.apply_move(s, "user", 3, 0, 2, 0) is None
    assert _by_id(s, 2)["alive"] is False
    attacker = _by_id(s, 1)
    assert (attacker["row"], attacker["col"]) == (2, 0) and attacker["revealed"]
    assert s["history"][-1]["combat"]["survivor"] == "attacker"


def test_weaker_attacker_dies_and_defender_is_revealed():
    s = _state([_piece(1, "user", "regular", 3, 0, power=60), _piece(2, "opponent", "regular", 2, 0, power=70), *_filler()])
    engine.apply_move(s, "user", 3, 0, 2, 0)
    assert _by_id(s, 1)["alive"] is False
    defender = _by_id(s, 2)
    assert defender["alive"] and defender["revealed"] and (defender["row"], defender["col"]) == (2, 0)


def test_equal_power_rarity_breaks_tie():
    s = _state([
        _piece(1, "user", "regular", 3, 0, power=75, rarity_rank=1),
        _piece(2, "opponent", "regular", 2, 0, power=75, rarity_rank=3), *_filler(),
    ])
    engine.apply_move(s, "user", 3, 0, 2, 0)
    assert _by_id(s, 1)["alive"] is False and _by_id(s, 2)["alive"] is True


def test_full_tie_removes_both():
    s = _state([_piece(1, "user", "regular", 3, 0, power=75), _piece(2, "opponent", "regular", 2, 0, power=75), *_filler()])
    engine.apply_move(s, "user", 3, 0, 2, 0)
    assert _by_id(s, 1)["alive"] is False and _by_id(s, 2)["alive"] is False
    assert s["history"][-1]["combat"]["survivor"] == "both"


def test_wall_kills_any_attacker_except_tackler():
    star = _piece(1, "user", "star", 3, 0, power=99)
    wall = _piece(2, "opponent", "wall", 2, 0)
    assert engine.resolve_combat(star, wall) == "defender"
    tackler = _piece(3, "user", "tackler", 3, 0, power=50)
    assert engine.resolve_combat(tackler, wall) == "attacker"

    s = _state([tackler, wall, *_filler()])
    engine.apply_move(s, "user", 3, 0, 2, 0)
    assert _by_id(s, 2)["alive"] is False and (_by_id(s, 3)["row"], _by_id(s, 3)["col"]) == (2, 0)


def test_provocateur_beats_star_only_when_attacking():
    spy = _piece(1, "user", "provocateur", 3, 0, power=55)
    star = _piece(2, "opponent", "star", 2, 0, power=95)
    assert engine.resolve_combat(spy, star) == "attacker"
    assert engine.resolve_combat(star, spy) == "attacker"  # the star attacking wins on power


def test_capturing_the_cup_wins():
    s = _state([_piece(1, "user", "regular", 3, 2, power=50), _piece(2, "opponent", "cup", 2, 2), *_filler()])
    outcome = engine.apply_move(s, "user", 3, 2, 2, 2)
    assert outcome == {"winner": "user", "reason": "cup_captured"}


def test_cup_and_walls_cannot_move():
    s = _state([_piece(1, "user", "cup", 5, 0), _piece(2, "user", "wall", 5, 1), *_filler()])
    movers = {m[0] for m in engine.legal_moves(s, "user")}
    assert 1 not in movers and 2 not in movers
    with pytest.raises(engine.EngineError):
        engine.apply_move(s, "user", 5, 0, 4, 0)


def test_speedster_moves_any_distance_until_blocked():
    s = _state([
        _piece(1, "user", "speedster", 5, 0, power=60), _piece(2, "opponent", "regular", 1, 0, power=50), *_filler(),
    ])
    targets = {(m[3], m[4]) for m in engine.legal_moves(s, "user") if m[0] == 1}
    assert {(4, 0), (3, 0), (2, 0), (1, 0)} <= targets  # can attack at the end of the run
    assert (0, 0) not in targets  # cannot jump over the enemy piece
    engine.apply_move(s, "user", 5, 0, 1, 0)
    assert _by_id(s, 2)["alive"] is False


def test_regular_piece_moves_one_step_orthogonally():
    s = _state([_piece(1, "user", "regular", 4, 2, power=60), *_filler()])
    for bad in ((2, 2), (3, 3), (4, 2)):
        with pytest.raises(engine.EngineError):
            engine.apply_move(_state([_piece(1, "user", "regular", 4, 2, power=60), *_filler()]), "user", 4, 2, *bad)
    engine.apply_move(s, "user", 4, 2, 3, 2)
    assert s["turn"] == "opponent" and s["ply"] == 1


def test_cannot_attack_own_piece_or_move_out_of_turn():
    s = _state([_piece(1, "user", "regular", 4, 2, power=60), _piece(2, "user", "regular", 3, 2, power=60), *_filler()])
    with pytest.raises(engine.EngineError):
        engine.apply_move(s, "user", 4, 2, 3, 2)
    with pytest.raises(engine.EngineError):
        engine.apply_move(s, "opponent", 0, 5, 1, 5)


def test_move_limit_decides_by_remaining_strength():
    s = _state([
        _piece(1, "user", "regular", 4, 0, power=80), _piece(2, "opponent", "regular", 0, 3, power=60),
        _piece(3, "opponent", "wall", 0, 0),
    ], move_limit=1)
    assert engine.apply_move(s, "user", 4, 0, 3, 0) == {"winner": "user", "reason": "move_limit"}

    s = _state([_piece(1, "user", "regular", 4, 0, power=70), _piece(2, "opponent", "regular", 0, 3, power=70)], move_limit=1)
    assert engine.apply_move(s, "user", 4, 0, 3, 0) == {"winner": "draw", "reason": "move_limit"}


def test_side_left_without_moves_loses():
    s = _state([
        _piece(1, "user", "regular", 3, 0, power=80), _piece(2, "opponent", "regular", 2, 0, power=60),
        _piece(3, "opponent", "cup", 0, 5), _piece(4, "user", "cup", 5, 5),
    ])
    assert engine.apply_move(s, "user", 3, 0, 2, 0) == {"winner": "user", "reason": "no_moves"}


# ---------------------------------------------------------------------------
# Layouts & coordinates
# ---------------------------------------------------------------------------

def test_auto_layout_fills_home_rows_with_cup_on_back_row():
    slots = engine.all_slots(SMALL_COUNTS)
    for seed in range(30):
        layout = engine.auto_layout(slots, 6, random.Random(seed))
        assert set(layout) == set(slots)
        cells = [tuple(v) for v in layout.values()]
        assert len(set(cells)) == len(cells)
        assert all(r in (0, 1) and 0 <= c < 6 for r, c in cells)
        assert layout["cup"][0] == 1
        engine.validate_layout(layout, slots, 6)


def test_validate_layout_rejects_bad_placements():
    slots = engine.all_slots(SMALL_COUNTS)
    good = engine.auto_layout(slots, 6, random.Random(1))
    with pytest.raises(engine.EngineError):
        engine.validate_layout({**good, "cup": [2, 0]}, slots, 6)
    with pytest.raises(engine.EngineError):
        engine.validate_layout({**good, "cup": good["star"]}, slots, 6)
    with pytest.raises(engine.EngineError):
        engine.validate_layout({k: v for k, v in good.items() if k != "cup"}, slots, 6)


def test_sides_get_mirrored_home_rows_and_viewer_rotation():
    assert engine.to_canonical("user", 0, 0, 6) == (4, 0)
    assert engine.to_canonical("user", 1, 5, 6) == (5, 5)
    assert engine.to_canonical("opponent", 0, 0, 6) == (1, 5)
    assert engine.to_canonical("opponent", 1, 0, 6) == (0, 5)
    # The opponent viewer sees their own front row as row 4, like the user does.
    assert engine.to_viewer("opponent", *engine.to_canonical("opponent", 0, 0, 6), 6) == (4, 0)


# ---------------------------------------------------------------------------
# Bot
# ---------------------------------------------------------------------------

def test_bot_captures_revealed_cup():
    s = _state([
        _piece(1, "opponent", "regular", 2, 2, power=50), _piece(2, "user", "cup", 3, 2, revealed=True),
        _piece(3, "user", "regular", 3, 0, power=99, revealed=True), _piece(4, "opponent", "regular", 0, 5, power=40),
    ], turn="opponent")
    assert engine.bot_choose_move(s, "opponent", random.Random(0))[3:] == (3, 2)


def test_bot_captures_known_weaker_piece_and_avoids_known_stronger():
    s = _state([
        _piece(1, "opponent", "regular", 2, 2, power=70),
        _piece(2, "user", "regular", 3, 2, power=60, revealed=True),
        _piece(3, "user", "regular", 2, 1, power=90, revealed=True),
        _piece(4, "user", "cup", 5, 5),
    ], turn="opponent")
    assert engine.bot_choose_move(s, "opponent", random.Random(0))[3:] == (3, 2)

    s["pieces"][1]["alive"] = False
    move = engine.bot_choose_move(s, "opponent", random.Random(0))
    assert move[3:] != (2, 1)  # never walks into a known stronger piece


def test_bot_does_not_use_hidden_information():
    def scenario(hidden_role):
        return _state([
            _piece(1, "opponent", "regular", 2, 2, power=70),
            _piece(2, "user", hidden_role, 3, 2, power=0 if hidden_role in ("cup", "wall") else 99),
            _piece(3, "user", "regular", 5, 5, power=10),
        ], turn="opponent")

    moves = {}
    for role in ("cup", "wall", "regular"):
        s = scenario(role)
        scores = {m: engine._score_move(s, "opponent", m) for m in engine.legal_moves(s, "opponent")}
        moves[role] = scores
    assert moves["cup"] == moves["wall"] == moves["regular"]


def test_bot_is_deterministic_for_a_seed():
    slots = engine.all_slots(SMALL_COUNTS)
    cards = {s: {"power": 60 + i, "rarity_rank": 0, "card": None} for i, s in enumerate(engine.card_slots(SMALL_COUNTS))}
    state = _state([], turn="opponent")
    state["pieces"] = (
        engine.build_pieces("user", slots, cards, engine.auto_layout(slots, 6, random.Random(1)), 6, list(range(1, 9)))
        + engine.build_pieces("opponent", slots, cards, engine.auto_layout(slots, 6, random.Random(2)), 6, list(range(9, 17)))
    )
    a = engine.bot_choose_move(state, "opponent", random.Random("x"))
    b = engine.bot_choose_move(state, "opponent", random.Random("x"))
    assert a == b and a is not None


def test_auto_assign_puts_strongest_card_on_star_and_respects_positions():
    def info(pid, power, position):
        return {"power": power, "rarity_rank": 0, "card": {
            "user_card_id": pid, "player_id": pid, "display_name": f"P{pid}", "position": position,
            "image_path": None, "rarity": "common", "rating": power,
        }}

    infos = [info(1, 90, "CB"), info(2, 70, "CB"), info(3, 65, "LW"), info(4, 60, "CM"), info(5, 50, "GK")]
    chosen = stratego_service._auto_assign(infos, engine.card_slots(SMALL_COUNTS))
    assert chosen["star"]["card"]["user_card_id"] == 1
    assert chosen["tackler"]["card"]["user_card_id"] == 2
    assert chosen["speedster"]["card"]["user_card_id"] == 3
    assert chosen["provocateur"]["card"]["user_card_id"] == 4
    assert chosen["regular_1"]["card"]["user_card_id"] == 5


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

async def _register(client, bot_token, telegram_id: int) -> dict:
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    return headers


SQUAD_SPEC = [(90, Position.ST), (70, Position.CB), (65, Position.LW), (60, Position.CM), (55, Position.GK)]


async def _give_cards(db_session, user_id: int, spec=SQUAD_SPEC, prefix="Card") -> list[int]:
    ids = []
    for rating, position, *rest in spec:
        rarity = rest[0] if rest else Rarity.common
        player = await create_player(
            db_session, rating=rating, position=position, rarity=rarity,
            display_name=f"{prefix} {position.value} {rating}",
        )
        card = await create_user_card(db_session, user_id, player.id, CardSource.seed)
        await db_session.commit()
        ids.append(card.id)
    return ids


async def _player(client, db_session, bot_token, telegram_id: int, prefix="Card"):
    headers = await _register(client, bot_token, telegram_id)
    user = await get_user_by_telegram_id(db_session, telegram_id)
    card_ids = await _give_cards(db_session, user.id, prefix=prefix)
    return headers, user, card_ids


async def _set_config(db_session, **overrides) -> None:
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
    for key, value in overrides.items():
        setattr(config, key, value)
    await db_session.commit()


async def _load_match(db_session, match_id: int) -> StrategoMatch:
    db_session.expire_all()
    return await db_session.get(StrategoMatch, match_id)


async def _rewrite_state(db_session, match_id: int, mutate) -> None:
    match = await _load_match(db_session, match_id)
    state = dict(match.server_state)
    mutate(state)
    match.server_state = state
    flag_modified(match, "server_state")
    await db_session.commit()


def _assert_no_leak(body: dict, match: StrategoMatch, viewer: str) -> None:
    """Every unrevealed enemy piece must reach the client as a bare token."""
    enemy = "opponent" if viewer == "user" else "user"
    hidden_enemy = [p for p in match.server_state["pieces"] if p["side"] == enemy and p["alive"] and not p["revealed"]]
    out_by_id = {p["id"]: p for p in body["pieces"]}
    for p in hidden_enemy:
        out = out_by_id[p["id"]]
        assert out["hidden"] is True and out["mine"] is False
        assert out["role"] is None and out["power"] is None and out["card"] is None
    raw = str(body)
    # Bot squads can borrow the same Player as one of the viewer's own cards,
    # so only names that no visible piece legitimately carries must be absent.
    visible_names = {
        p["card"]["display_name"] for p in match.server_state["pieces"]
        if p["card"] and (p["side"] == viewer or p["revealed"])
    }
    for p in hidden_enemy:
        if p["card"] and p["card"]["display_name"] not in visible_names:
            assert p["card"]["display_name"] not in raw
    assert body["my_strength"] is None and body["opponent_strength"] is None


# ---------------------------------------------------------------------------
# Squad & layout (prepared before any match)
# ---------------------------------------------------------------------------

async def test_squad_auto_fills_from_collection(client, db_session, bot_token):
    headers, _, card_ids = await _player(client, db_session, bot_token, 970001)
    body = (await client.get(f"{API}/squad", headers=headers)).json()
    assert body["is_complete"] is True
    slots = {s["slot"]: s["card"]["user_card_id"] for s in body["card_slots"]}
    assert slots["star"] == card_ids[0]
    assert slots["tackler"] == card_ids[1]
    assert slots["speedster"] == card_ids[2]
    assert slots["provocateur"] == card_ids[3]
    assert set(body["layout"]) == set(body["slots"])


async def test_squad_incomplete_without_enough_cards_blocks_play(client, db_session, bot_token):
    headers = await _register(client, bot_token, 970002)
    user = await get_user_by_telegram_id(db_session, 970002)
    await _give_cards(db_session, user.id, spec=SQUAD_SPEC[:3])
    assert (await client.get(f"{API}/squad", headers=headers)).json()["is_complete"] is False
    assert (await client.post(f"{API}/matches/bot", headers=headers)).status_code == 409


async def test_set_squad_validates_roles_star_and_layout(client, db_session, bot_token):
    headers, _, ids = await _player(client, db_session, bot_token, 970003)
    squad = (await client.get(f"{API}/squad", headers=headers)).json()
    layout = squad["layout"]
    cards = {"star": ids[0], "tackler": ids[1], "speedster": ids[2], "provocateur": ids[3], "regular_1": ids[4]}

    bad_role = {**cards, "tackler": ids[4], "regular_1": ids[1]}  # GK as tackler while a CB is owned
    assert (await client.put(f"{API}/squad", headers=headers, json={"cards": bad_role, "layout": layout})).status_code == 409
    weak_star = {**cards, "star": ids[4], "regular_1": ids[0]}
    assert (await client.put(f"{API}/squad", headers=headers, json={"cards": weak_star, "layout": layout})).status_code == 409
    bad_layout = {**layout, "cup": [3, 0]}
    assert (await client.put(f"{API}/squad", headers=headers, json={"cards": cards, "layout": bad_layout})).status_code == 409

    my_layout = {**layout}
    my_layout["cup"], my_layout["star"] = layout["star"], layout["cup"]
    resp = await client.put(f"{API}/squad", headers=headers, json={"cards": cards, "layout": my_layout})
    assert resp.status_code == 200
    assert resp.json()["layout"] == my_layout


async def test_set_squad_rejects_foreign_cards(client, db_session, bot_token):
    _, _, other_ids = await _player(client, db_session, bot_token, 970004)
    headers, _, ids = await _player(client, db_session, bot_token, 970005)
    squad = (await client.get(f"{API}/squad", headers=headers)).json()
    cards = {"star": other_ids[0], "tackler": ids[1], "speedster": ids[2], "provocateur": ids[3], "regular_1": ids[4]}
    resp = await client.put(f"{API}/squad", headers=headers, json={"cards": cards, "layout": squad["layout"]})
    assert resp.status_code == 403


async def test_saved_layout_is_used_when_match_starts(client, db_session, bot_token):
    headers, _, ids = await _player(client, db_session, bot_token, 970006)
    squad = (await client.get(f"{API}/squad", headers=headers)).json()
    cards = {s["slot"]: s["card"]["user_card_id"] for s in squad["card_slots"]}
    layout = {"cup": [1, 0], "wall_1": [1, 1], "wall_2": [0, 0], "star": [0, 5], "tackler": [0, 1],
              "speedster": [0, 2], "provocateur": [0, 3], "regular_1": [1, 5]}
    assert (await client.put(f"{API}/squad", headers=headers, json={"cards": cards, "layout": layout})).status_code == 200

    body = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    mine = {p["role"]: (p["row"], p["col"]) for p in body["pieces"] if p["mine"]}
    # A match starts straight in play — no in-match placement phase.
    assert body["status"] == "in_progress"
    assert mine["cup"] == (5, 0) and mine["star"] == (4, 5) and mine["regular"] == (5, 5)


# ---------------------------------------------------------------------------
# Bot matches, hidden information, moves
# ---------------------------------------------------------------------------

async def test_bot_match_hides_opponent_pieces(client, db_session, bot_token):
    headers, user, _ = await _player(client, db_session, bot_token, 970010)
    for i in range(8):
        await create_player(db_session, rating=70 + i, position=Position.CB, display_name=f"Secret Bot {i}")
    resp = await client.post(f"{API}/matches/bot", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["my_turn"] is True
    match = await _load_match(db_session, body["id"])
    _assert_no_leak(body, match, "user")
    if body["ply"] == 0:  # the bot may have opened (even with a long speedster run)
        assert all(p["row"] in (4, 5) for p in body["pieces"] if p["mine"])
        assert all(p["row"] in (0, 1) for p in body["pieces"] if not p["mine"])

    again = (await client.get(f"{API}/matches/{body['id']}", headers=headers)).json()
    _assert_no_leak(again, match, "user")


async def test_move_via_api_and_bot_replies(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 970011)
    body = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    ply = body["ply"]
    mover = next(p for p in body["pieces"] if p["mine"] and p["row"] == 4 and p["role"] not in ("cup", "wall", "speedster"))
    resp = await client.post(f"{API}/matches/{body['id']}/move", headers=headers, json={
        "from_row": 4, "from_col": mover["col"], "to_row": 3, "to_col": mover["col"],
    })
    assert resp.status_code == 200, resp.text
    after = resp.json()
    assert after["ply"] == ply + 2 and after["my_turn"] is True
    assert after["history"][-2]["mine"] is True and after["history"][-1]["mine"] is False
    match = await _load_match(db_session, body["id"])
    _assert_no_leak(after, match, "user")

    illegal = await client.post(f"{API}/matches/{body['id']}/move", headers=headers, json={
        "from_row": 3, "from_col": mover["col"], "to_row": 1, "to_col": mover["col"],
    })
    assert illegal.status_code == 409


async def _cup_capture_setup(db_session, match_id: int):
    """Puts the user's star right in front of the opponent's cup."""
    def mutate(state):
        pieces = [dict(p) for p in state["pieces"]]
        cup = next(p for p in pieces if p["side"] == "opponent" and p["role"] == "cup")
        star = next(p for p in pieces if p["side"] == "user" and p["role"] == "star")
        cup["row"], cup["col"] = 2, 0
        star["row"], star["col"] = 3, 0
        for p in pieces:
            if p is not cup and p is not star and (p["row"], p["col"]) in ((2, 0), (3, 0)):
                p["alive"] = False
        state["pieces"] = pieces
        state["turn"] = "user"
    await _rewrite_state(db_session, match_id, mutate)


async def test_capturing_cup_wins_and_pays_reward(client, db_session, bot_token):
    await _set_config(db_session, stratego_reward_win=77)
    headers, user, _ = await _player(client, db_session, bot_token, 970012)
    balance_before = user.balance
    body = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    await _cup_capture_setup(db_session, body["id"])
    resp = await client.post(f"{API}/matches/{body['id']}/move", headers=headers, json={
        "from_row": 3, "from_col": 0, "to_row": 2, "to_col": 0,
    })
    end = resp.json()
    assert end["status"] == "finished" and end["result"] == "win" and end["win_reason"] == "cup_captured"
    assert end["reward_coins"] == 77
    assert end["my_strength"] is not None
    assert all(not p["hidden"] for p in end["pieces"])  # everything revealed after the final whistle
    db_session.expire_all()
    user = await get_user_by_telegram_id(db_session, 970012)
    assert user.balance == balance_before + 77
    assert user.stratego_rewarded_attempts_today == 1
    tx = (await db_session.execute(select(CoinTransaction).where(CoinTransaction.type == TransactionType.stratego_reward))).scalars().all()
    assert len(tx) == 1


async def test_daily_reward_cap_and_blocked_rewards(client, db_session, bot_token):
    await _set_config(db_session, stratego_daily_limit=1, stratego_reward_win=50)
    headers, user, _ = await _player(client, db_session, bot_token, 970013)
    rewards = []
    for _ in range(2):
        body = (await client.post(f"{API}/matches/bot", headers=headers)).json()
        await _cup_capture_setup(db_session, body["id"])
        end = (await client.post(f"{API}/matches/{body['id']}/move", headers=headers, json={
            "from_row": 3, "from_col": 0, "to_row": 2, "to_col": 0,
        })).json()
        rewards.append(end["reward_coins"])
    assert rewards == [50, 0]

    headers2, user2, _ = await _player(client, db_session, bot_token, 970014, prefix="B")
    user2.game_rewards_blocked = True
    await db_session.commit()
    body = (await client.post(f"{API}/matches/bot", headers=headers2)).json()
    await _cup_capture_setup(db_session, body["id"])
    end = (await client.post(f"{API}/matches/{body['id']}/move", headers=headers2, json={
        "from_row": 3, "from_col": 0, "to_row": 2, "to_col": 0,
    })).json()
    assert end["result"] == "win" and end["reward_coins"] == 0


async def test_forfeit_is_a_loss_without_consolation(client, db_session, bot_token):
    await _set_config(db_session, stratego_reward_loss=5)
    headers, _, _ = await _player(client, db_session, bot_token, 970015)
    body = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    end = (await client.post(f"{API}/matches/{body['id']}/forfeit", headers=headers)).json()
    assert end["result"] == "loss" and end["win_reason"] == "forfeit" and end["reward_coins"] == 0


async def test_one_active_match_and_hourly_limit(client, db_session, bot_token):
    await _set_config(db_session, hourly_game_limit=2)
    headers, _, _ = await _player(client, db_session, bot_token, 970016)
    first = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    assert (await client.post(f"{API}/matches/bot", headers=headers)).status_code == 409  # already playing
    await client.post(f"{API}/matches/{first['id']}/forfeit", headers=headers)
    second = await client.post(f"{API}/matches/bot", headers=headers)
    assert second.status_code == 200
    await client.post(f"{API}/matches/{second.json()['id']}/forfeit", headers=headers)
    third = await client.post(f"{API}/matches/bot", headers=headers)
    assert third.status_code == 409
    assert third.json()["error"]["details"]["hourly_limit"] == 2

    limits = (await client.get("/api/v1/games/limits", headers=headers)).json()
    assert limits["stratego"] == 0


async def test_bot_match_abandoned_past_timeout_is_lost(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 970017)
    body = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    await _rewrite_state(db_session, body["id"], lambda s: s.update(last_activity_at=old))
    after = (await client.get(f"{API}/matches/{body['id']}", headers=headers)).json()
    assert after["status"] == "finished" and after["result"] == "loss" and after["win_reason"] == "timeout"


# ---------------------------------------------------------------------------
# Friend challenges, async deadlines, sweep
# ---------------------------------------------------------------------------

async def _friend_match(client, db_session, bot_token, a=970020, b=970021):
    headers_a, user_a, _ = await _player(client, db_session, bot_token, a, prefix="Alpha")
    headers_b, user_b, _ = await _player(client, db_session, bot_token, b, prefix="Bravo")
    created = await client.post(f"{API}/matches/challenge", headers=headers_a, json={"receiver_id": user_b.id})
    assert created.status_code == 200
    return headers_a, headers_b, user_a, user_b, created.json()


async def test_friend_challenge_flow_and_hidden_info_for_both(client, db_session, bot_token):
    headers_a, headers_b, _, _, created = await _friend_match(client, db_session, bot_token)
    assert created["status"] == "pending_accept"

    pending_b = (await client.get(f"{API}/matches/{created['id']}", headers=headers_b)).json()
    assert pending_b["pieces"] == []  # the invitee sees nothing of the challenger's layout

    accepted = (await client.post(f"{API}/matches/{created['id']}/accept", headers=headers_b)).json()
    assert accepted["status"] == "in_progress" and accepted["deadline"] is not None
    match = await _load_match(db_session, created["id"])
    for headers, viewer in ((headers_a, "user"), (headers_b, "opponent")):
        body = (await client.get(f"{API}/matches/{created['id']}", headers=headers)).json()
        _assert_no_leak(body, match, viewer)
        assert all(p["row"] in (4, 5) for p in body["pieces"] if p["mine"])
        assert all(p["row"] in (0, 1) for p in body["pieces"] if not p["mine"])
        assert "Alpha" not in str([p for p in body["pieces"] if not p["mine"]])


async def test_friend_turns_are_enforced_and_coordinates_rotate(client, db_session, bot_token):
    headers_a, headers_b, _, _, created = await _friend_match(client, db_session, bot_token, 970022, 970023)
    await client.post(f"{API}/matches/{created['id']}/accept", headers=headers_b)
    await _rewrite_state(db_session, created["id"], lambda s: s.update(turn="opponent"))

    body_b = (await client.get(f"{API}/matches/{created['id']}", headers=headers_b)).json()
    assert body_b["my_turn"] is True
    mover = next(p for p in body_b["pieces"] if p["mine"] and p["row"] == 4 and p["role"] not in ("cup", "wall"))
    move = {"from_row": 4, "from_col": mover["col"], "to_row": 3, "to_col": mover["col"]}
    assert (await client.post(f"{API}/matches/{created['id']}/move", headers=headers_a, json=move)).status_code == 409
    assert (await client.post(f"{API}/matches/{created['id']}/move", headers=headers_b, json=move)).status_code == 200

    body_a = (await client.get(f"{API}/matches/{created['id']}", headers=headers_a)).json()
    moved = next(p for p in body_a["pieces"] if p["id"] == mover["id"])
    assert (moved["row"], moved["col"]) == (2, 5 - mover["col"]) and moved["hidden"] is True and moved["moved"] is True
    assert body_a["my_turn"] is True and body_a["history"][-1]["mine"] is False


async def test_overdue_move_is_auto_played_then_forfeited(client, db_session, bot_token):
    await _set_config(db_session, stratego_max_auto_moves=1)
    headers_a, headers_b, _, _, created = await _friend_match(client, db_session, bot_token, 970024, 970025)
    await client.post(f"{API}/matches/{created['id']}/accept", headers=headers_b)
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    await _rewrite_state(db_session, created["id"], lambda s: s.update(turn="user", deadline=past))

    body = (await client.get(f"{API}/matches/{created['id']}", headers=headers_b)).json()
    assert body["ply"] == 1 and body["history"][-1]["auto"] is True and body["my_turn"] is True

    # B now times out too: one auto move is allowed for B, then A times out
    # again — A already used their single allowed auto move and forfeits.
    await _rewrite_state(db_session, created["id"], lambda s: s.update(deadline=past))
    await client.get(f"{API}/matches/{created['id']}", headers=headers_a)
    await _rewrite_state(db_session, created["id"], lambda s: s.update(deadline=past))
    final = (await client.get(f"{API}/matches/{created['id']}", headers=headers_a)).json()
    assert final["status"] == "finished" and final["win_reason"] == "timeout" and final["result"] == "loss"


async def test_pvp_finish_pays_both_sides_within_their_caps(client, db_session, bot_token):
    await _set_config(db_session, stratego_reward_win=40, stratego_reward_loss=6)
    headers_a, headers_b, _, _, created = await _friend_match(client, db_session, bot_token, 970026, 970027)
    await client.post(f"{API}/matches/{created['id']}/accept", headers=headers_b)
    await _cup_capture_setup(db_session, created["id"])
    end_a = (await client.post(f"{API}/matches/{created['id']}/move", headers=headers_a, json={
        "from_row": 3, "from_col": 0, "to_row": 2, "to_col": 0,
    })).json()
    assert end_a["result"] == "win" and end_a["reward_coins"] == 40
    end_b = (await client.get(f"{API}/matches/{created['id']}", headers=headers_b)).json()
    assert end_b["result"] == "loss" and end_b["reward_coins"] == 6


async def test_challenge_decline_cancel_and_expiry(client, db_session, bot_token):
    headers_a, headers_b, _, _, created = await _friend_match(client, db_session, bot_token, 970028, 970029)
    assert (await client.post(f"{API}/matches/{created['id']}/accept", headers=headers_a)).status_code == 403
    assert (await client.post(f"{API}/matches/{created['id']}/decline", headers=headers_b)).json()["status"] == "declined"

    user_b_id = (await get_user_by_telegram_id(db_session, 970029)).id
    second = (await client.post(f"{API}/matches/challenge", headers=headers_a, json={"receiver_id": user_b_id})).json()
    match = await _load_match(db_session, second["id"])
    match.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()
    db_session.expire_all()
    listed = (await client.get(f"{API}/matches", headers=headers_a)).json()
    assert next(m for m in listed if m["id"] == second["id"])["status"] == "expired"

    third = (await client.post(f"{API}/matches/challenge", headers=headers_a, json={"receiver_id": user_b_id})).json()
    assert (await client.post(f"{API}/matches/{third['id']}/cancel", headers=headers_a)).json()["status"] == "cancelled"


async def test_outsider_cannot_view_or_move(client, db_session, bot_token):
    headers_a, headers_b, _, _, created = await _friend_match(client, db_session, bot_token, 970030, 970031)
    headers_c = await _register(client, bot_token, 970032)
    assert (await client.get(f"{API}/matches/{created['id']}", headers=headers_c)).status_code == 403
    resp = await client.post(f"{API}/matches/{created['id']}/move", headers=headers_c, json={
        "from_row": 4, "from_col": 0, "to_row": 3, "to_col": 0,
    })
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Matchmaking & admin
# ---------------------------------------------------------------------------

async def test_matchmaking_pairs_two_searchers(client, db_session, bot_token):
    headers_a, _, _ = await _player(client, db_session, bot_token, 970040, prefix="A")
    headers_b, _, _ = await _player(client, db_session, bot_token, 970041, prefix="B")
    assert (await client.post(f"{API}/matchmaking/search", headers=headers_a)).status_code == 200
    assert (await client.post(f"{API}/matchmaking/search", headers=headers_b)).status_code == 200
    status_b = (await client.get(f"{API}/matchmaking/status", headers=headers_b)).json()
    assert status_b["status"] == "matched"
    status_a = (await client.get(f"{API}/matchmaking/status", headers=headers_a)).json()
    assert status_a == {**status_a, "status": "matched", "match_id": status_b["match_id"]}
    match = (await client.get(f"{API}/matches/{status_b['match_id']}", headers=headers_a)).json()
    assert match["opponent_type"] == "online" and match["status"] == "in_progress"


async def test_matchmaking_timeout_falls_back_to_bot(client, db_session, bot_token):
    headers, user, _ = await _player(client, db_session, bot_token, 970042)
    await client.post(f"{API}/matchmaking/search", headers=headers)
    from app.models.stratego import StrategoQueueEntry
    entry = (await db_session.execute(select(StrategoQueueEntry))).scalar_one()
    entry.created_at = datetime.now(timezone.utc) - timedelta(seconds=120)
    await db_session.commit()
    status = (await client.get(f"{API}/matchmaking/status", headers=headers)).json()
    assert status["status"] == "matched"
    match = (await client.get(f"{API}/matches/{status['match_id']}", headers=headers)).json()
    assert match["opponent_type"] == "bot"


async def test_admin_can_edit_stratego_config(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    body = (await client.get("/api/v1/admin/games/config", headers=auth)).json()
    assert body["stratego_board_size"] == 6 and body["stratego_tackler_count"] == 1
    resp = await client.put("/api/v1/admin/games/config", headers=auth, json={"stratego_move_limit": 60})
    assert resp.status_code == 200 and resp.json()["stratego_move_limit"] == 60
    too_many = await client.put("/api/v1/admin/games/config", headers=auth, json={"stratego_wall_count": 4, "stratego_regular_count": 4, "stratego_board_size": 5, "stratego_speedster_count": 2})
    assert too_many.status_code == 409


async def test_info_endpoint_reports_config(client, db_session, bot_token):
    await _set_config(db_session, stratego_reward_win=99)
    headers, _, _ = await _player(client, db_session, bot_token, 970043)
    info = (await client.get(f"{API}/info", headers=headers)).json()
    assert info["reward_win"] == 99 and info["board_size"] == 6 and info["rewarded_today"] == 0


# ---------------------------------------------------------------------------
# Rating
# ---------------------------------------------------------------------------

async def _win_by_cup(client, db_session, headers, match_id):
    await _cup_capture_setup(db_session, match_id)
    return (await client.post(f"{API}/matches/{match_id}/move", headers=headers, json={
        "from_row": 3, "from_col": 0, "to_row": 2, "to_col": 0,
    })).json()


async def test_bot_matches_move_stratego_rating(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 970050)
    body = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    end = await _win_by_cup(client, db_session, headers, body["id"])
    assert end["rating_delta"] == 3
    second = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    lost = (await client.post(f"{API}/matches/{second['id']}/forfeit", headers=headers)).json()
    assert lost["rating_delta"] == -1
    stats = (await client.get(f"{API}/stats", headers=headers)).json()
    assert stats["stratego_rating"] == 2 and stats["stratego_rank"] == 1
    ranking = (await client.get("/api/v1/leaderboard/ranking?metric=stratego_rating", headers=headers))
    assert ranking.status_code == 200 and ranking.json()["top"][0]["value"] == 2


async def test_friend_matches_do_not_move_rating(client, db_session, bot_token):
    headers_a, headers_b, _, _, created = await _friend_match(client, db_session, bot_token, 970051, 970052)
    await client.post(f"{API}/matches/{created['id']}/accept", headers=headers_b)
    end = await _win_by_cup(client, db_session, headers_a, created["id"])
    assert end["result"] == "win" and end["rating_delta"] == 0
    assert (await client.get(f"{API}/stats", headers=headers_a)).json()["stratego_rating"] == 0


# ---------------------------------------------------------------------------
# Open (chat-link) challenges with stakes
# ---------------------------------------------------------------------------

async def test_open_challenge_with_stake_pays_the_pot(client, db_session, bot_token):
    await _set_config(db_session, stratego_reward_win=10, stratego_reward_loss=0)
    headers_a, user_a, _ = await _player(client, db_session, bot_token, 970060, prefix="Open A")
    headers_b, user_b, _ = await _player(client, db_session, bot_token, 970061, prefix="Open B")
    start_a, start_b = user_a.balance, user_b.balance

    created = await client.post(f"{API}/matches/open-challenge", headers=headers_a, json={"stake_coins": 100})
    assert created.status_code == 200
    match = created.json()
    assert match["opponent_type"] == "chat" and match["stake_coins"] == 100 and match["status"] == "pending_accept"

    preview = (await client.get(f"{API}/matches/open/{match['id']}", headers=headers_b)).json()
    assert preview["stake_coins"] == 100 and preview["is_own_challenge"] is False and preview["status"] == "pending_accept"
    assert (await client.post(f"{API}/matches/open/{match['id']}/accept", headers=headers_a)).status_code == 409

    accepted = await client.post(f"{API}/matches/open/{match['id']}/accept", headers=headers_b)
    assert accepted.status_code == 200 and accepted.json()["status"] == "in_progress"
    db_session.expire_all()
    assert (await get_user_by_telegram_id(db_session, 970060)).balance == start_a - 100
    assert (await get_user_by_telegram_id(db_session, 970061)).balance == start_b - 100

    headers_c, _, _ = await _player(client, db_session, bot_token, 970062, prefix="Open C")
    assert (await client.post(f"{API}/matches/open/{match['id']}/accept", headers=headers_c)).status_code == 409

    end = await _win_by_cup(client, db_session, headers_a, match["id"])
    assert end["result"] == "win" and end["reward_coins"] == 10 + 200 and end["rating_delta"] == 3
    db_session.expire_all()
    assert (await get_user_by_telegram_id(db_session, 970060)).balance == start_a - 100 + 200 + 10
    assert (await get_user_by_telegram_id(db_session, 970061)).balance == start_b - 100
    loser_view = (await client.get(f"{API}/matches/{match['id']}", headers=headers_b)).json()
    assert loser_view["result"] == "loss" and loser_view["rating_delta"] == -1


async def test_open_challenge_rejects_unaffordable_stake_and_can_be_cancelled(client, db_session, bot_token):
    headers, user, _ = await _player(client, db_session, bot_token, 970063)
    too_much = await client.post(f"{API}/matches/open-challenge", headers=headers, json={"stake_coins": user.balance + 1})
    assert too_much.status_code == 409
    created = (await client.post(f"{API}/matches/open-challenge", headers=headers, json={"stake_coins": 0})).json()
    assert (await client.post(f"{API}/matches/{created['id']}/cancel", headers=headers)).json()["status"] == "cancelled"
    preview = (await client.get(f"{API}/matches/open/{created['id']}", headers=headers)).json()
    assert preview["status"] == "cancelled" and preview["is_own_challenge"] is True


async def test_open_challenge_hides_creator_layout_until_and_after_accept(client, db_session, bot_token):
    headers_a, _, _ = await _player(client, db_session, bot_token, 970064, prefix="Hide A")
    headers_b, _, _ = await _player(client, db_session, bot_token, 970065, prefix="Hide B")
    created = (await client.post(f"{API}/matches/open-challenge", headers=headers_a, json={"stake_coins": 0})).json()
    preview = (await client.get(f"{API}/matches/open/{created['id']}", headers=headers_b)).text
    assert "Hide A" not in preview
    await client.post(f"{API}/matches/open/{created['id']}/accept", headers=headers_b)
    body = (await client.get(f"{API}/matches/{created['id']}", headers=headers_b)).json()
    match = await _load_match(db_session, created["id"])
    _assert_no_leak(body, match, "opponent")


# ---------------------------------------------------------------------------
# Shipped default: 8×8 board, two lakes, 16 pieces a side
# ---------------------------------------------------------------------------

def test_default_8x8_lakes_block_movement_and_speedster_runs():
    lakes = engine.default_lakes(8)
    assert sorted(map(tuple, lakes)) == [(3, 2), (3, 5), (4, 2), (4, 5)]  # lanes: cols 0-1, 3-4, 6-7
    assert engine.default_lakes(6) == []
    s = _state([
        _piece(1, "user", "regular", 5, 5, power=60), _piece(2, "user", "speedster", 6, 2, power=60),
        _piece(3, "user", "speedster", 7, 0, power=60), _piece(9, "opponent", "regular", 0, 7, power=10),
    ], board_size=8)
    s["lakes"] = lakes
    targets = {(m[0], m[3], m[4]) for m in engine.legal_moves(s, "user")}
    assert (1, 4, 5) not in targets  # cannot step into a puddle
    assert (2, 5, 2) in targets and (2, 4, 2) not in targets and (2, 2, 2) not in targets  # run stops at the lake
    assert (3, 0, 0) in targets  # open lane along the edge
    with pytest.raises(engine.EngineError):
        engine.apply_move(s, "user", 5, 5, 4, 5)


def test_default_8x8_slots_and_auto_layout_fill_both_home_rows():
    counts = {"wall": 2, "tackler": 3, "speedster": 2, "regular": 6}
    slots = engine.all_slots(counts)
    assert len(slots) == 16 and slots.count("cup") == 1
    assert sum(engine.role_of(x) == "wall" for x in slots) == 2
    assert {"tackler_1", "tackler_2", "tackler_3", "speedster_1", "speedster_2", "star", "provocateur"} <= set(slots)
    for seed in range(10):
        layout = engine.auto_layout(slots, 8, random.Random(seed))
        assert len({tuple(v) for v in layout.values()}) == 16


R = Rarity
EIGHT_SPEC = [
    (95, Position.ST, R.diamond), (80, Position.CB, R.epic), (79, Position.LB, R.epic),
    (78, Position.LW, R.legendary), (77, Position.RW, R.legendary), (76, Position.CM, R.epic),
    (70, Position.GK, R.rare), (69, Position.RB, R.rare), (68, Position.CDM, R.rare), (67, Position.CAM, R.rare),
    (66, Position.LM), (65, Position.RM), (64, Position.ST),
]


async def test_default_8x8_bot_match_has_16_pieces_and_lakes(client, db_session, bot_token, user_moves_first):
    headers = await _register(client, bot_token, 970070)
    user = await get_user_by_telegram_id(db_session, 970070)
    await _give_cards(db_session, user.id, spec=EIGHT_SPEC)
    squad = (await client.get(f"{API}/squad", headers=headers)).json()
    assert squad["board_size"] == 8 and squad["is_complete"] and squad["cards_needed"] == 13
    assert len(squad["slots"]) == 16 and len(squad["layout"]) == 16
    roles = {s["slot"]: s["card"]["position"] for s in squad["card_slots"]}
    assert all(roles[f"tackler_{i}"] in ("CB", "LB", "RB", "CDM") for i in (1, 2, 3))
    assert roles["speedster_1"] in ("LW", "RW", "LM", "RM")

    body = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    assert body["board_size"] == 8 and body["move_limit"] == 300 and len(body["lakes"]) == 4
    mine = [p for p in body["pieces"] if p["mine"]]
    assert len(mine) == 16
    if body["ply"] == 0:
        assert all(p["row"] in (6, 7) for p in mine)
        assert sum(1 for p in body["pieces"] if not p["mine"]) == 16
    match = await _load_match(db_session, body["id"])
    _assert_no_leak(body, match, "user")


async def test_default_8x8_requires_13_cards(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 970071)  # only 5 cards
    squad = (await client.get(f"{API}/squad", headers=headers)).json()
    assert squad["is_complete"] is False and squad["cards_needed"] == 13
    resp = await client.post(f"{API}/matches/bot", headers=headers)
    assert resp.status_code == 409 and "13" in resp.json()["error"]["message"]


# ---------------------------------------------------------------------------
# Rarity rules: max 3 legendary, max 1 diamond, min 4 rare, min 2 common
# ---------------------------------------------------------------------------

DEFAULT_RULES = {"max": {"legendary": 3, "diamond": 1}, "min": {"rare": 4, "common": 2}}


def _info(pid, power, position, rarity):
    return {"power": power, "rarity_rank": 0, "card": {
        "user_card_id": pid, "player_id": pid, "display_name": f"P{pid}", "position": position,
        "image_path": None, "rarity": rarity, "rating": power,
    }}


def test_default_8x8_auto_assign_respects_rarity_rules():
    infos = (
        [_info(i, 95 - i, "CB" if i % 2 else "ST", "legendary") for i in range(1, 8)]
        + [_info(10 + i, 97 - i, "LW", "diamond") for i in range(3)]
        + [_info(20 + i, 70 - i, "CM", "rare") for i in range(6)]
        + [_info(30 + i, 60 - i, "GK", "common") for i in range(4)]
        + [_info(40 + i, 75 - i, "RB", "epic") for i in range(4)]
    )
    slots = engine.card_slots({"tackler": 3, "speedster": 2, "regular": 6})
    chosen = stratego_service._auto_assign(infos, slots, rules=DEFAULT_RULES)
    assert len(chosen) == 13
    rarities = [c["card"]["rarity"] for c in chosen.values()]
    assert rarities.count("legendary") <= 3 and rarities.count("diamond") <= 1
    assert rarities.count("rare") >= 4 and rarities.count("common") >= 2
    assert stratego_service.rarity_violations(list(chosen.values()), DEFAULT_RULES) == []
    assert chosen["star"]["card"]["rarity"] == "diamond"  # still the strongest card


def test_default_8x8_rarity_violations_messages():
    picked = [_info(i, 80, "ST", "legendary") for i in range(4)] + [_info(9, 90, "ST", "diamond")] * 2
    problems = stratego_service.rarity_violations(picked, DEFAULT_RULES)
    assert any("легендарных" in p for p in problems) and any("диамантовых" in p for p in problems)
    assert any("редких" in p for p in problems) and any("обычных" in p for p in problems)


async def test_set_squad_enforces_rarity_rules(client, db_session, bot_token):
    await _set_config(db_session, stratego_max_legendary_cards=1, stratego_min_rare_cards=1, stratego_min_common_cards=1)
    headers = await _register(client, bot_token, 970080)
    user = await get_user_by_telegram_id(db_session, 970080)
    ids = await _give_cards(db_session, user.id, spec=[
        (90, Position.ST, Rarity.legendary), (70, Position.CB, Rarity.legendary), (65, Position.LW, Rarity.rare),
        (60, Position.CM), (55, Position.GK),
    ])
    squad = (await client.get(f"{API}/squad", headers=headers)).json()
    # Only five cards and two are legendary: the cap can't be met.
    assert squad["is_complete"] is False and any("легендарных" in v for v in squad["violations"])
    assert squad["rarity_limits"] == {"max_legendary": 1, "max_diamond": 1, "max_path": 1, "min_rare": 1, "min_common": 1}
    cards = {"star": ids[0], "tackler": ids[1], "speedster": ids[2], "provocateur": ids[3], "regular_1": ids[4]}
    resp = await client.put(f"{API}/squad", headers=headers, json={"cards": cards, "layout": squad["layout"]})
    assert resp.status_code == 409 and "легендарных" in resp.json()["error"]["message"]
    assert (await client.post(f"{API}/matches/bot", headers=headers)).status_code == 409

    # A sixth, non-legendary defender makes a legal squad possible.
    extra = await _give_cards(db_session, user.id, spec=[(68, Position.RB, Rarity.epic)], prefix="Extra")
    squad = (await client.get(f"{API}/squad", headers=headers)).json()
    assert squad["is_complete"] is True and squad["violations"] == []
    picked = {s["card"]["user_card_id"] for s in squad["card_slots"]}
    assert extra[0] in picked and len(picked & {ids[0], ids[1]}) == 1
    assert (await client.post(f"{API}/matches/bot", headers=headers)).status_code == 200


async def test_default_8x8_bot_squad_follows_rarity_rules(client, db_session, bot_token):
    headers = await _register(client, bot_token, 970081)
    user = await get_user_by_telegram_id(db_session, 970081)
    await _give_cards(db_session, user.id, spec=EIGHT_SPEC)
    for i in range(6):  # extra rare/common players the bot can draw from
        await create_player(db_session, rating=70, position=Position.CM, rarity=Rarity.rare, display_name=f"BR{i}")
        await create_player(db_session, rating=60, position=Position.CB, rarity=Rarity.common, display_name=f"BC{i}")
    body = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    match = await _load_match(db_session, body["id"])
    bot = [p["card"]["rarity"] for p in match.server_state["pieces"] if p["side"] == "opponent" and p["card"]]
    assert len(bot) == 13
    assert bot.count("legendary") <= 3 and bot.count("diamond") <= 1
    assert bot.count("rare") >= 4 and bot.count("common") >= 2


async def test_admin_rejects_impossible_rarity_minimums(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    resp = await client.put("/api/v1/admin/games/config", headers=auth, json={"stratego_min_rare_cards": 4, "stratego_min_common_cards": 3})
    assert resp.status_code == 409  # small test board has only 5 card pieces


# ---------------------------------------------------------------------------
# «Мой игрок» in Stratego
# ---------------------------------------------------------------------------

MY_LOOK = {"skin": 1, "hair": 2, "hair_color": 3, "beard": 0, "eye_color": 1, "kit": 4, "kit_pattern": 1}


async def _with_my_player(client, db_session, bot_token, telegram_id):
    headers, user, ids = await _player(client, db_session, bot_token, telegram_id)
    created = await client.post("/api/v1/my-player", headers=headers, json={
        "name": "Виктор Ж.", "number": 9, "position": "ST", "appearance": MY_LOOK,
    })
    assert created.status_code == 200, created.text
    return headers, user, ids


async def test_my_player_can_take_a_role_and_earns_xp(client, db_session, bot_token, user_moves_first):
    from app.services.my_player_service import card_id_for

    await _set_config(db_session, stratego_my_player_xp=15)
    headers, user, ids = await _with_my_player(client, db_session, bot_token, 970090)
    mine_id = card_id_for(user.id)
    squad = (await client.get(f"{API}/squad", headers=headers)).json()
    option = next(o for o in squad["options"] if o["is_my_player"])
    assert option["user_card_id"] == mine_id and option["rarity"] == "common"  # bronze frame

    cards = {"star": ids[0], "tackler": ids[1], "speedster": ids[2], "provocateur": ids[3], "regular_1": mine_id}
    saved = await client.put(f"{API}/squad", headers=headers, json={"cards": cards, "layout": squad["layout"]})
    assert saved.status_code == 200, saved.text
    assert next(s for s in saved.json()["card_slots"] if s["slot"] == "regular_1")["card"]["is_my_player"] is True

    xp_before = (await get_user_by_telegram_id(db_session, 970090)).my_player_xp or 0
    body = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    assert any(p["mine"] and p["card"] and p["card"].get("is_my_player") for p in body["pieces"])
    end = await _win_by_cup(client, db_session, headers, body["id"])
    assert end["result"] == "win" and end["my_player_xp"] == 15
    db_session.expire_all()
    xp_after = (await get_user_by_telegram_id(db_session, 970090)).my_player_xp
    assert xp_after >= xp_before + 15  # + the usual per-reward XP for the coin reward

    view = (await client.get("/api/v1/my-player", headers=headers)).json()
    assert view["xp_stratego_match"] == 15


async def test_my_player_gets_no_xp_when_owner_forfeits_or_not_fielded(client, db_session, bot_token, user_moves_first):
    headers, user, ids = await _with_my_player(client, db_session, bot_token, 970091)
    user_id = user.id
    # Auto squad: five stronger cards fill the five slots, the 52-rated
    # bronze player stays on the bench.
    body = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    assert not any(p["mine"] and p["card"] and p["card"].get("is_my_player") for p in body["pieces"])
    end = await _win_by_cup(client, db_session, headers, body["id"])
    assert end["my_player_xp"] == 0

    from app.services.my_player_service import card_id_for
    squad = (await client.get(f"{API}/squad", headers=headers)).json()
    cards = {"star": ids[0], "tackler": ids[1], "speedster": ids[2], "provocateur": ids[3], "regular_1": card_id_for(user_id)}
    await client.put(f"{API}/squad", headers=headers, json={"cards": cards, "layout": squad["layout"]})
    second = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    quit_ = (await client.post(f"{API}/matches/{second['id']}/forfeit", headers=headers)).json()
    assert quit_["my_player_xp"] == 0


async def test_my_player_hidden_from_opponent_like_any_piece(client, db_session, bot_token):
    headers_a, user_a, ids_a = await _with_my_player(client, db_session, bot_token, 970092)
    from app.services.my_player_service import card_id_for
    squad = (await client.get(f"{API}/squad", headers=headers_a)).json()
    cards = {"star": ids_a[0], "tackler": ids_a[1], "speedster": ids_a[2], "provocateur": ids_a[3], "regular_1": card_id_for(user_a.id)}
    await client.put(f"{API}/squad", headers=headers_a, json={"cards": cards, "layout": squad["layout"]})
    headers_b, user_b, _ = await _player(client, db_session, bot_token, 970093, prefix="Bravo")
    created = (await client.post(f"{API}/matches/challenge", headers=headers_a, json={"receiver_id": user_b.id})).json()
    await client.post(f"{API}/matches/{created['id']}/accept", headers=headers_b)
    body_b = (await client.get(f"{API}/matches/{created['id']}", headers=headers_b)).text
    assert "Виктор" not in body_b and "is_my_player\":true" not in body_b.replace(" ", "")


async def test_saved_squad_breaking_new_rarity_rules_is_repicked(client, db_session, bot_token):
    headers = await _register(client, bot_token, 970095)
    user = await get_user_by_telegram_id(db_session, 970095)
    ids = await _give_cards(db_session, user.id, spec=[
        (90, Position.ST, Rarity.epic), (70, Position.CB, Rarity.epic), (65, Position.LW, Rarity.epic),
        (60, Position.CM, Rarity.epic), (55, Position.GK, Rarity.epic),
        (50, Position.RB, Rarity.rare), (49, Position.ST, Rarity.common),
    ])
    squad = (await client.get(f"{API}/squad", headers=headers)).json()
    cards = {"star": ids[0], "tackler": ids[1], "speedster": ids[2], "provocateur": ids[3], "regular_1": ids[4]}
    assert (await client.put(f"{API}/squad", headers=headers, json={"cards": cards, "layout": squad["layout"]})).status_code == 200
    # The admin now demands a rare and a common card: the saved all-epic squad
    # is re-picked instead of leaving the player stuck.
    await _set_config(db_session, stratego_min_rare_cards=1, stratego_min_common_cards=1)
    squad = (await client.get(f"{API}/squad", headers=headers)).json()
    assert squad["is_complete"] is True and squad["violations"] == []
    picked = {s["card"]["user_card_id"] for s in squad["card_slots"]}
    assert ids[5] in picked and ids[6] in picked



# ---------------------------------------------------------------------------
# Подкатчик: at most epic (GameConfig.stratego_tackler_max_rarity)
# ---------------------------------------------------------------------------

def test_default_8x8_auto_assign_never_puts_rare_cards_above_cap_on_tackler():
    rules = {**DEFAULT_RULES, "role_max": {"tackler": "epic"}}
    infos = (
        [_info(i, 90 - i, "CB", "legendary") for i in range(1, 4)]  # best defenders are all legendary
        + [_info(10 + i, 70 - i, "RB", "rare") for i in range(4)]
        + [_info(20 + i, 60 - i, "GK", "common") for i in range(3)]
        + [_info(30 + i, 75 - i, "LW", "epic") for i in range(4)]
    )
    slots = engine.card_slots({"tackler": 3, "speedster": 2, "regular": 6})
    chosen = stratego_service._auto_assign(infos, slots, rules=rules)
    assert len(chosen) == 13
    for slot, info in chosen.items():
        if engine.role_of(slot) == "tackler":
            assert info["card"]["rarity"] in ("common", "rare", "epic")
    assert stratego_service.squad_violations(chosen, rules) == []


async def test_legendary_tackler_is_rejected(client, db_session, bot_token):
    headers = await _register(client, bot_token, 970100)
    user = await get_user_by_telegram_id(db_session, 970100)
    ids = await _give_cards(db_session, user.id, spec=[
        (90, Position.ST), (80, Position.CB, Rarity.legendary), (65, Position.LW), (60, Position.CM), (55, Position.GK),
        (50, Position.RB),
    ])
    squad = (await client.get(f"{API}/squad", headers=headers)).json()
    assert squad["tackler_max_rarity"] == "epic"
    tackler = next(s for s in squad["card_slots"] if s["slot"] == "tackler")
    assert tackler["card"]["user_card_id"] == ids[5]  # the common RB, not the legendary CB
    cards = {"star": ids[0], "tackler": ids[1], "speedster": ids[2], "provocateur": ids[3], "regular_1": ids[4]}
    resp = await client.put(f"{API}/squad", headers=headers, json={"cards": cards, "layout": squad["layout"]})
    assert resp.status_code == 409 and "Подкатчик" in resp.json()["error"]["message"]


async def test_admin_sets_tackler_max_rarity(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    ok = await client.put("/api/v1/admin/games/config", headers=auth, json={"stratego_tackler_max_rarity": "legendary"})
    assert ok.status_code == 200 and ok.json()["stratego_tackler_max_rarity"] == "legendary"
    bad = await client.put("/api/v1/admin/games/config", headers=auth, json={"stratego_tackler_max_rarity": "mythic"})
    assert bad.status_code == 422


# ---------------------------------------------------------------------------
# Repetition rule, card skills, bot levels, live mode, notes
# ---------------------------------------------------------------------------

def test_two_square_rule_blocks_fourth_shuttle():
    s = _state([_piece(1, "user", "regular", 4, 0, power=60), _piece(2, "user", "regular", 5, 5, power=60),
                _piece(9, "opponent", "regular", 0, 5, power=10), _piece(8, "opponent", "regular", 0, 3, power=10)])
    shuttle = [(4, 0, 3, 0), (3, 0, 4, 0), (4, 0, 3, 0)]
    for i, (fr, fc, tr, tc) in enumerate(shuttle):
        engine.apply_move(s, "user", fr, fc, tr, tc)
        engine.apply_move(s, "opponent", 0, 5 if i % 2 == 0 else 4, 0, 4 if i % 2 == 0 else 5)
    assert engine.repeat_blocked(s, "user") == (1, frozenset({(3, 0), (4, 0)}))
    assert (1, 3, 0, 4, 0) not in engine.legal_moves(s, "user")
    with pytest.raises(engine.EngineError):
        engine.apply_move(s, "user", 3, 0, 4, 0)
    engine.apply_move(s, "user", 3, 0, 2, 0)  # moving elsewhere is fine


def test_card_skill_bonus_decides_a_close_fight():
    attacker = {**_piece(1, "user", "regular", 3, 0, power=70), "atk_bonus": 4}
    defender = _piece(2, "opponent", "regular", 2, 0, power=72)
    assert engine.resolve_combat(attacker, defender) == "attacker"
    guarded = {**defender, "def_bonus": 4}
    assert engine.resolve_combat(attacker, guarded) == "defender"
    # an attacking skill does nothing on defence
    assert engine.resolve_combat(defender, attacker) == "attacker"


def test_skill_snapshot_on_card_info():
    info = stratego_service._with_skill(_info(1, 70, "ST", "rare"), "sniper", 2, 2)
    assert info["atk_bonus"] == 4 and info["card"]["skill_kind"] == "atk" and info["card"]["skill_bonus"] == 4
    info = stratego_service._with_skill(_info(2, 70, "CB", "rare"), "last_line", 3, 2)
    assert info["def_bonus"] == 6 and info["card"]["skill_kind"] == "def"


def test_bot_levels_are_deterministic_and_hard_hunts_the_star():
    s = _state([
        _piece(1, "opponent", "provocateur", 1, 4, power=40), _piece(2, "opponent", "regular", 1, 0, power=40),
        _piece(5, "opponent", "cup", 0, 7),
        _piece(3, "user", "star", 4, 4, power=95, revealed=True), _piece(4, "user", "cup", 7, 0),
    ], turn="opponent", board_size=8)
    for level in engine.BOT_DIFFICULTIES:
        first = engine.bot_choose_move(s, "opponent", random.Random(1), level)
        assert first == engine.bot_choose_move(s, "opponent", random.Random(1), level)
    move = engine.bot_choose_move(s, "opponent", random.Random(1), "hard")
    assert move[0] == 1 and move[3:] == (2, 4)  # provocateur heads for the revealed star


async def test_easy_bot_pays_less_and_caps_rating(client, db_session, bot_token):
    await _set_config(db_session, stratego_reward_win=100, stratego_bot_easy_reward_pct=60)
    headers, _, _ = await _player(client, db_session, bot_token, 970110)
    body = (await client.post(f"{API}/matches/bot", headers=headers, json={"difficulty": "easy"})).json()
    assert body["difficulty"] == "easy"
    end = await _win_by_cup(client, db_session, headers, body["id"])
    assert end["reward_coins"] == 60 and end["rating_delta"] == 1
    hard = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    assert hard["difficulty"] == "hard"
    end = await _win_by_cup(client, db_session, headers, hard["id"])
    assert end["reward_coins"] == 100 and end["rating_delta"] == 3


async def test_matchmaking_match_is_live_with_short_deadline(client, db_session, bot_token):
    await _set_config(db_session, stratego_live_move_seconds=60)
    headers_a, _, _ = await _player(client, db_session, bot_token, 970111, prefix="LiveA")
    headers_b, _, _ = await _player(client, db_session, bot_token, 970112, prefix="LiveB")
    await client.post(f"{API}/matchmaking/search", headers=headers_a)
    await client.post(f"{API}/matchmaking/search", headers=headers_b)
    match_id = (await client.get(f"{API}/matchmaking/status", headers=headers_b)).json()["match_id"]
    body = (await client.get(f"{API}/matches/{match_id}", headers=headers_a)).json()
    assert body["live"] is True
    left = datetime.fromisoformat(body["deadline"].replace("Z", "+00:00")) - datetime.now(timezone.utc)
    assert timedelta(seconds=0) < left <= timedelta(seconds=61)


async def test_notes_are_private_and_only_on_opponent_pieces(client, db_session, bot_token):
    headers_a, headers_b, _, _, created = await _friend_match(client, db_session, bot_token, 970113, 970114)
    await client.post(f"{API}/matches/{created['id']}/accept", headers=headers_b)
    body_a = (await client.get(f"{API}/matches/{created['id']}", headers=headers_a)).json()
    enemy = next(p for p in body_a["pieces"] if not p["mine"])
    mine = next(p for p in body_a["pieces"] if p["mine"])
    url = f"{API}/matches/{created['id']}/notes"
    resp = await client.post(url, headers=headers_a, json={"piece_id": enemy["id"], "tag": "wall"})
    assert resp.status_code == 200 and resp.json()["notes"] == {str(enemy["id"]): "wall"}
    assert (await client.post(url, headers=headers_a, json={"piece_id": mine["id"], "tag": "wall"})).status_code == 409
    body_b = (await client.get(f"{API}/matches/{created['id']}", headers=headers_b)).json()
    assert body_b["notes"] == {}
    cleared = await client.post(url, headers=headers_a, json={"piece_id": enemy["id"], "tag": None})
    assert cleared.json()["notes"] == {}


# ---------------------------------------------------------------------------
# «Задача дня» and the tutorial
# ---------------------------------------------------------------------------

def test_every_puzzle_is_solvable_and_not_shorter():
    from app.services import stratego_puzzles

    for puzzle in stratego_puzzles.PUZZLES:
        assert stratego_puzzles.solve(puzzle) is not None, puzzle["code"]
        assert stratego_puzzles.solve(puzzle, puzzle["moves"] - 1) is None, puzzle["code"]


async def test_daily_puzzle_solve_pays_once_a_day(client, db_session, bot_token):
    from app.core.timeutil import local_today
    from app.services import stratego_puzzles

    await _set_config(db_session, stratego_puzzle_reward=50)
    headers = await _register(client, bot_token, 970120)  # no cards needed
    info = (await client.get(f"{API}/puzzle", headers=headers)).json()
    assert info["solved_today"] is False and info["reward"] == 50
    puzzle = stratego_puzzles.daily_puzzle(local_today())
    solution = stratego_puzzles.solve(puzzle)

    rewards = []
    for _ in range(2):
        body = (await client.post(f"{API}/puzzle/start", headers=headers)).json()
        assert body["mode"] == "puzzle" and body["puzzle"]["code"] == puzzle["code"]
        assert all(not p["hidden"] for p in body["pieces"])  # it's a puzzle: everything is shown
        for _, fr, fc, tr, tc in solution:
            body = (await client.post(f"{API}/matches/{body['id']}/move", headers=headers, json={
                "from_row": fr, "from_col": fc, "to_row": tr, "to_col": tc,
            })).json()
        assert body["status"] == "finished" and body["result"] == "win" and body["win_reason"] == "cup_captured"
        rewards.append(body["reward_coins"])
    assert rewards == [50, 0]
    info = (await client.get(f"{API}/puzzle", headers=headers)).json()
    assert info["solved_today"] is True and info["solved_total"] == 1
    # puzzles never show up among real matches nor block one
    assert (await client.get(f"{API}/matches", headers=headers)).json() == []


async def test_tutorial_needs_no_cards_and_does_not_block_play(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 970121)
    tut = (await client.post(f"{API}/tutorial/start", headers=headers)).json()
    assert tut["mode"] == "tutorial" and tut["board_size"] == 6 and tut["difficulty"] == "easy"
    assert len([p for p in tut["pieces"] if p["mine"]]) == 8
    assert (await client.post(f"{API}/matches/bot", headers=headers)).status_code == 200
    headers_new = await _register(client, bot_token, 970122)  # a brand-new player with no cards
    assert (await client.post(f"{API}/tutorial/start", headers=headers_new)).status_code == 200


# ---------------------------------------------------------------------------
# Провокатор / Подкатчик / Скорость: at most epic
# ---------------------------------------------------------------------------

async def test_special_roles_capped_at_epic(client, db_session, bot_token):
    headers = await _register(client, bot_token, 970130)
    user = await get_user_by_telegram_id(db_session, 970130)
    ids = await _give_cards(db_session, user.id, spec=[
        (95, Position.ST, Rarity.diamond),
        (90, Position.LW, Rarity.legendary), (89, Position.CM, Rarity.legendary), (88, Position.CB, Rarity.legendary),
        (70, Position.RW, Rarity.epic), (69, Position.CAM, Rarity.rare), (68, Position.RB, Rarity.common),
        (60, Position.GK),
    ])
    squad = (await client.get(f"{API}/squad", headers=headers)).json()
    assert squad["role_max_rarity"] == {"tackler": "epic", "provocateur": "epic", "speedster": "epic"}
    picked = {s["slot"]: s["card"] for s in squad["card_slots"]}
    for slot in ("tackler", "provocateur", "speedster"):
        assert picked[slot]["rarity"] in ("common", "rare", "epic"), slot
    assert picked["speedster"]["user_card_id"] == ids[4]
    assert picked["provocateur"]["user_card_id"] == ids[5]
    assert picked["tackler"]["user_card_id"] == ids[6]

    layout = squad["layout"]
    for slot, legendary in (("speedster", ids[1]), ("provocateur", ids[2])):
        cards = {"star": ids[0], "tackler": ids[6], "speedster": ids[4], "provocateur": ids[5], "regular_1": ids[7]}
        cards[slot] = legendary
        resp = await client.put(f"{API}/squad", headers=headers, json={"cards": cards, "layout": layout})
        assert resp.status_code == 409
        assert ("Скорость" if slot == "speedster" else "Провокатор") in resp.json()["error"]["message"]

    info = (await client.get(f"{API}/info", headers=headers)).json()
    assert info["role_max_rarity"]["provocateur"] == "epic"


async def test_admin_sets_role_caps(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    resp = await client.put("/api/v1/admin/games/config", headers=auth, json={
        "stratego_provocateur_max_rarity": "legendary", "stratego_speedster_max_rarity": "rare",
    })
    assert resp.status_code == 200
    assert resp.json()["stratego_provocateur_max_rarity"] == "legendary"
    assert resp.json()["stratego_speedster_max_rarity"] == "rare"


# Stake tests here are about stake mechanics; the anti-farming limits have
# their own file (test_stake_guard.py).
pytestmark = pytest.mark.usefixtures("stake_guards_off")


def test_auto_assign_never_picks_two_copies_of_one_footballer():
    def info(cid, power, position, person):
        return {"person": person, "power": power, "rarity_rank": 0, "card": {
            "user_card_id": cid, "player_id": cid, "display_name": person, "position": position,
            "image_path": None, "rarity": "common", "rating": power,
        }}

    infos = [info(1, 90, "CB", "неста"), info(2, 89, "CB", "неста"), info(3, 70, "CB", "мальдини"),
             info(4, 65, "LW", "фигу"), info(5, 60, "CM", "пирло"), info(6, 50, "GK", "буффон"), info(7, 40, "ST", "индзаги")]
    chosen = stratego_service._auto_assign(infos, engine.card_slots(SMALL_COUNTS))
    persons = [c["person"] for c in chosen.values()]
    assert len(persons) == len(set(persons))
