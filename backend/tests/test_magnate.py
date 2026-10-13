import copy
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

import app.core.rate_limit as rate_limit_module
from app.config import get_settings
from app.models.enums import TransactionType
from app.models.game_config import GameConfig
from app.models.magnate import MagnateMatch, MagnateSeat
from app.models.transaction import CoinTransaction
from app.services import magnate_engine as engine
from tests.factories import get_user_by_telegram_id
from tests.test_admin_packs import _admin_auth
from tests.utils import telegram_headers

API = "/api/v1/magnate"
INTERNAL_HEADERS = {"X-Internal-Secret": get_settings().internal_api_secret}

SETTINGS = {
    "start_money": 1500, "pass_start_bonus": 200, "jail_fine": 50, "max_jail_turns": 3, "fine_amount": 100,
    "building_sell_pct": 50, "max_rounds": 12, "stadium_rents": [25, 50, 100, 200],
    "bot_buy_reserve": 150, "bot_build_reserve": 250,
}

# Landmarks of engine.BOARD_24, the compact board the engine tests use (the
# shipped 32-cell default is covered by its own tests below).
AMSTERDAM, ROTTERDAM, STADIUM_N, PORTO, LISBON, JAIL = 1, 2, 3, 4, 5, 6
MARSEILLE, VAR, LYON, STADIUM_E, PARIS = 7, 8, 9, 10, 11
TRANSFER, GO_TO_JAIL, FINE, MANCHESTER = 15, 18, 20, 23


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


def _state(n: int = 4, seed: str = "t", bots: bool = False, **settings) -> dict:
    s = engine.new_state(
        engine.BOARD_24, engine.DEFAULT_CARDS, {**SETTINGS, **settings},
        [{"name": f"P{i}", "is_bot": bots} for i in range(n)], seed,
    )
    s["turn"] = s["first_seat"] = 0
    return s


def _turn_back(s: dict, seat: int = 0) -> None:
    s["turn"] = seat
    s["phase"] = "roll"


# ---------------------------------------------------------------------------
# Engine: movement, doubles, disqualification
# ---------------------------------------------------------------------------

def test_default_board_and_cards_are_valid():
    board = engine.validate_board(engine.DEFAULT_BOARD)
    cells = board["cells"]
    assert len(cells) == engine.BOARD_CELLS == 32
    types = [c["type"] for c in cells]
    assert types.count("stadium") == 4 and types.count("club") == 18
    assert [cells[i]["type"] for i in (0, 8, 16, 24)] == ["start", "chance", "break", "jail"]
    assert cells[24]["arrest"] and {"var", "transfer", "fine"} <= set(types)
    groups = {c["group"] for c in cells if c["type"] == "club"}
    assert len(groups) == 8
    assert all(2 <= sum(1 for c in cells if c.get("group") == g) <= 3 for g in groups)
    names = {c["name"] for c in cells}
    assert {"Челси", "Арсенал", "Барселона", "Реал"} <= names
    clubs = [c for c in cells if c["type"] == "club"]
    assert max(clubs, key=lambda c: c["price"])["name"] == "Реал"
    assert {c["name"] for c in clubs if c["group"] == clubs[-1]["group"]} == {"Барселона", "Реал"}
    assert all(c.get("short") and c.get("colors") for c in clubs)
    engine.validate_board(engine.BOARD_24)
    engine.validate_cards(engine.DEFAULT_CARDS)


def _big_state(seed: str = "big") -> dict:
    s = engine.new_state(
        engine.DEFAULT_BOARD, engine.DEFAULT_CARDS, SETTINGS,
        [{"name": f"P{i}", "is_bot": False} for i in range(4)], seed,
    )
    s["turn"] = s["first_seat"] = 0
    return s


def _penalty_outcome(seed: str) -> tuple[dict, bool]:
    s = _big_state(seed)
    s["players"][0]["pos"] = 5
    engine.apply_action(s, 0, "roll", dice=[1, 2])  # lands on «Пенальти» (8)
    return s, s["last_penalty"]["scored"]


def test_penalty_cell_is_a_fair_coin_between_good_and_bad_cards():
    outcomes = [_penalty_outcome(f"pen-{i}")[1] for i in range(200)]
    assert 70 < sum(outcomes) < 130  # roughly half scored
    s, scored = next(_penalty_outcome(f"pen-{i}") for i in range(200) if _penalty_outcome(f"pen-{i}")[1])
    goal_log = [e for e in s["log"] if e["kind"] == "penalty_goal"]
    assert goal_log and "ГОЛ" in goal_log[-1]["text"]
    # Same seed → same outcome (server RNG is reproducible).
    assert _penalty_outcome("pen-7")[1] == _penalty_outcome("pen-7")[1]


def test_disqualification_corner_arrests_and_releases_on_a_double():
    s = _big_state()
    s["players"][0]["pos"] = 21
    engine.apply_action(s, 0, "roll", dice=[1, 2])  # «Дисквалификация» (24)
    p = s["players"][0]
    assert p["in_jail"] and p["pos"] == 24 and s["turn"] == 1
    s["turn"], s["phase"] = 0, "roll"
    engine.apply_action(s, 0, "roll", dice=[1, 2])
    assert p["in_jail"] and p["jail_turns"] == 1  # no double: still out
    s["turn"], s["phase"] = 0, "roll"
    engine.apply_action(s, 0, "roll", dice=[2, 2])
    assert not p["in_jail"] and p["pos"] == 28


def test_three_doubles_send_to_the_disqualification_corner():
    s = _big_state()
    s["players"][0]["pos"] = 1  # 1 → 3 (Аякс) → 7 (Бенфика): no event cards on the way
    for dice in ([1, 1], [2, 2]):
        engine.apply_action(s, 0, "roll", dice=dice)
        if s["phase"] == "buy":
            engine.apply_action(s, 0, "skip")
    engine.apply_action(s, 0, "roll", dice=[3, 3])
    assert s["players"][0]["in_jail"] and s["players"][0]["pos"] == 24 and s["turn"] == 1


def test_red_card_kind_skips_a_turn_on_boards_without_disqualification():
    board = copy.deepcopy(engine.DEFAULT_BOARD)
    board["cells"][24] = {"type": "break", "name": "Перерыв 2"}
    s = engine.new_state(board, engine.DEFAULT_CARDS, SETTINGS, [{"name": f"P{i}"} for i in range(4)], "rc")
    s["turn"] = s["first_seat"] = 0
    s["players"][0]["pos"] = 1
    for dice in ([1, 1], [2, 2]):
        engine.apply_action(s, 0, "roll", dice=dice)
        if s["phase"] == "buy":
            engine.apply_action(s, 0, "skip")
    engine.apply_action(s, 0, "roll", dice=[3, 3])  # third double, no jail on this board
    assert s["players"][0]["skip_turns"] == 1 and s["turn"] == 1
    for seat in (1, 2, 3):
        s["players"][seat]["pos"] = 15
        engine.apply_action(s, seat, "roll", dice=[1, 3])
        engine.apply_action(s, seat, "skip")
    assert s["turn"] == 1 and s["players"][0]["skip_turns"] == 0


def test_chance_deck_needs_good_and_bad_cards():
    cards = copy.deepcopy(engine.DEFAULT_CARDS)
    cards["chance"] = [c for c in cards["chance"] if c["good"]]
    with pytest.raises(engine.EngineError):
        engine.validate_cards(cards)


def test_default_board_plays_through_and_uses_cell_fine_amounts():
    s = engine.new_state(
        engine.DEFAULT_BOARD, engine.DEFAULT_CARDS, SETTINGS,
        [{"name": f"P{i}", "is_bot": False} for i in range(4)], "big",
    )
    s["turn"] = s["first_seat"] = 0
    s["players"][0]["pos"] = 7
    engine.apply_action(s, 0, "roll", dice=[1, 2])  # «Налог на зарплаты» 150
    assert s["players"][0]["pos"] == 10 and s["players"][0]["cash"] == 1500 - 150
    s["players"][1]["pos"] = 27
    engine.apply_action(s, 1, "roll", dice=[1, 2])  # «Штраф федерации» — settings amount
    assert s["players"][1]["cash"] == 1500 - SETTINGS["fine_amount"]
    bots = engine.new_state(
        engine.DEFAULT_BOARD, engine.DEFAULT_CARDS, SETTINGS,
        [{"name": f"B{i}", "is_bot": True} for i in range(4)], "big-bots",
    )
    engine.run_bots(bots)
    assert bots["finished"]


def test_roll_moves_and_offers_purchase():
    s = _state()
    engine.apply_action(s, 0, "roll", dice=[2, 3])
    assert s["players"][0]["pos"] == LISBON
    assert s["phase"] == "buy" and s["pending"] == {"cell": LISBON} and s["turn"] == 0
    assert s["last_roll"]["dice"] == [2, 3]


def test_buy_and_skip():
    s = _state()
    engine.apply_action(s, 0, "roll", dice=[2, 3])
    engine.apply_action(s, 0, "buy")
    assert s["owner"][LISBON] == 0 and s["players"][0]["cash"] == 1500 - 120
    assert s["turn"] == 1 and s["phase"] == "roll"
    engine.apply_action(s, 1, "roll", dice=[1, 3])
    engine.apply_action(s, 1, "skip")
    assert s["owner"][PORTO] is None and s["turn"] == 2


def test_out_of_turn_and_out_of_phase_actions_are_rejected():
    s = _state()
    with pytest.raises(engine.EngineError):
        engine.apply_action(s, 1, "roll", dice=[1, 2])
    with pytest.raises(engine.EngineError):
        engine.apply_action(s, 0, "buy")
    engine.apply_action(s, 0, "roll", dice=[2, 3])
    with pytest.raises(engine.EngineError):
        engine.apply_action(s, 0, "roll", dice=[1, 2])


def test_passing_start_pays_the_bonus():
    s = _state()
    s["players"][0]["pos"] = 22
    engine.apply_action(s, 0, "roll", dice=[1, 2])
    assert s["players"][0]["pos"] == AMSTERDAM and s["players"][0]["cash"] == 1700


def test_doubles_give_another_roll():
    s = _state()
    engine.apply_action(s, 0, "roll", dice=[1, 1])
    engine.apply_action(s, 0, "skip")
    assert s["turn"] == 0 and s["phase"] == "roll"


def test_three_doubles_in_a_row_disqualify():
    s = _state()
    engine.apply_action(s, 0, "roll", dice=[1, 1])
    engine.apply_action(s, 0, "skip")
    engine.apply_action(s, 0, "roll", dice=[2, 2])  # lands on «Дисквалификация» just visiting
    assert s["turn"] == 0 and not s["players"][0]["in_jail"]
    engine.apply_action(s, 0, "roll", dice=[3, 3])
    p = s["players"][0]
    assert p["in_jail"] and p["pos"] == JAIL and s["turn"] == 1


def test_red_card_cell_sends_to_disqualification_without_extra_turn():
    s = _state()
    s["players"][0]["pos"] = 15
    engine.apply_action(s, 0, "roll", dice=[1, 2])
    assert s["players"][0]["in_jail"] and s["players"][0]["pos"] == JAIL and s["turn"] == 1


def test_disqualification_waits_then_forces_the_fine():
    s = _state()
    s["players"][0].update(pos=JAIL, in_jail=True)
    engine.apply_action(s, 0, "roll", dice=[1, 2])
    assert s["players"][0]["in_jail"] and s["players"][0]["jail_turns"] == 1 and s["turn"] == 1
    _turn_back(s)
    engine.apply_action(s, 0, "roll", dice=[1, 2])
    assert s["players"][0]["jail_turns"] == 2
    _turn_back(s)
    engine.apply_action(s, 0, "roll", dice=[1, 3])
    p = s["players"][0]
    assert not p["in_jail"] and p["pos"] == STADIUM_E and p["cash"] == 1450 and s["phase"] == "buy"


def test_doubles_release_from_disqualification_without_extra_turn():
    s = _state()
    s["players"][0].update(pos=JAIL, in_jail=True)
    engine.apply_action(s, 0, "roll", dice=[2, 2])
    assert not s["players"][0]["in_jail"] and s["players"][0]["pos"] == STADIUM_E
    engine.apply_action(s, 0, "skip")
    assert s["turn"] == 1


def test_bail_and_appeal_card():
    s = _state()
    s["players"][0].update(pos=JAIL, in_jail=True)
    with pytest.raises(engine.EngineError):
        engine.apply_action(s, 0, "use_card")
    engine.apply_action(s, 0, "pay_bail")
    assert not s["players"][0]["in_jail"] and s["players"][0]["cash"] == 1450 and s["phase"] == "roll"
    s["players"][0].update(in_jail=True, jail_cards=1)
    engine.apply_action(s, 0, "use_card")
    assert not s["players"][0]["in_jail"] and s["players"][0]["jail_cards"] == 0


# ---------------------------------------------------------------------------
# Engine: rent, group, buildings
# ---------------------------------------------------------------------------

def test_rent_base_full_group_tribunes_and_arena():
    s = _state()
    s["owner"][MARSEILLE] = 1
    assert engine.rent_for(s, MARSEILLE) == 10
    s["owner"][LYON] = s["owner"][PARIS] = 1
    assert engine.rent_for(s, MARSEILLE) == 20  # full group doubles the base
    s["level"][MARSEILLE] = 1
    assert engine.rent_for(s, MARSEILLE) == 50
    s["level"][MARSEILLE] = 3
    assert engine.rent_for(s, MARSEILLE) == 450
    s["level"][MARSEILLE] = engine.MAX_LEVEL
    assert engine.rent_for(s, MARSEILLE) == 700

    s["players"][0]["pos"] = PORTO
    engine.apply_action(s, 0, "roll", dice=[1, 2])
    assert s["players"][0]["cash"] == 800 and s["players"][1]["cash"] == 2200


def test_stadium_rent_grows_with_stadiums_owned():
    s = _state()
    s["owner"][STADIUM_N] = 2
    assert engine.rent_for(s, STADIUM_N) == 25
    s["owner"][STADIUM_E] = 2
    assert engine.rent_for(s, STADIUM_N) == 50 and engine.rent_for(s, STADIUM_E) == 50


def test_building_needs_the_full_group_but_no_even_rule():
    s = _state()
    s["owner"][AMSTERDAM] = 0
    with pytest.raises(engine.EngineError):
        engine.apply_action(s, 0, "build", AMSTERDAM)
    s["owner"][ROTTERDAM] = 0
    for _ in range(engine.MAX_LEVEL):
        engine.apply_action(s, 0, "build", AMSTERDAM)
    assert s["level"][AMSTERDAM] == engine.MAX_LEVEL and s["level"][ROTTERDAM] == 0
    assert s["players"][0]["cash"] == 1500 - 4 * 50
    with pytest.raises(engine.EngineError):
        engine.apply_action(s, 0, "build", AMSTERDAM)


def test_turn_waits_in_end_phase_when_building_is_possible():
    s = _state()
    s["owner"][AMSTERDAM] = s["owner"][ROTTERDAM] = 0
    engine.apply_action(s, 0, "roll", dice=[1, 2])
    engine.apply_action(s, 0, "skip")
    assert s["phase"] == "end" and s["turn"] == 0
    engine.apply_action(s, 0, "build", ROTTERDAM)
    engine.apply_action(s, 0, "end")
    assert s["turn"] == 1 and s["phase"] == "roll"


def test_capital_counts_cash_property_and_buildings():
    s = _state()
    s["players"][0]["cash"] = 1000
    s["owner"][AMSTERDAM] = 0
    s["level"][AMSTERDAM] = 2
    s["owner"][STADIUM_N] = 0
    assert engine.capital(s, 0) == 1000 + 60 + 2 * 50 + 200


# ---------------------------------------------------------------------------
# Engine: bankruptcy and the end of the game
# ---------------------------------------------------------------------------

def test_bankruptcy_sells_buildings_first_then_eliminates():
    s = _state()
    p0 = s["players"][0]
    p0.update(cash=100, pos=20)
    s["owner"][AMSTERDAM] = s["owner"][ROTTERDAM] = 0
    s["level"][AMSTERDAM] = 2
    s["owner"][MANCHESTER] = 1
    s["level"][MANCHESTER] = engine.MAX_LEVEL  # rent 1500
    engine.apply_action(s, 0, "roll", dice=[1, 2])
    assert p0["bankrupt"] and p0["cash"] == 0 and p0["bankrupt_order"] == 1
    assert s["players"][1]["cash"] == 1500 + 100 + 2 * 25  # all cash incl. sold tribunes
    assert s["owner"][AMSTERDAM] is None and s["level"][AMSTERDAM] == 0
    assert not s["finished"] and s["turn"] == 1


def test_paying_from_buildings_avoids_bankruptcy_when_enough():
    s = _state()
    p0 = s["players"][0]
    p0.update(cash=10, pos=17)
    s["owner"][AMSTERDAM] = s["owner"][ROTTERDAM] = 0
    s["level"][AMSTERDAM] = s["level"][ROTTERDAM] = 2  # 4 tribunes × 25 back
    engine.apply_action(s, 0, "roll", dice=[1, 2])  # «Штраф федерации» 100
    assert not p0["bankrupt"] and p0["cash"] == 10 + 4 * 25 - 100
    assert s["level"][AMSTERDAM] + s["level"][ROTTERDAM] == 0


def test_last_player_standing_wins():
    s = _state(n=2)
    s["players"][0].update(cash=5, pos=17)
    engine.apply_action(s, 0, "roll", dice=[1, 2])
    assert s["finished"] and s["finish_reason"] == "last_standing"
    assert engine.standings(s) == [1, 0]


def test_round_limit_ends_and_ranks_by_capital():
    s = _state(bots=True, seed="rounds", max_rounds=2)
    engine.run_bots(s)
    assert s["finished"] and s["finish_reason"] == "rounds" and s["round"] == 2
    order = engine.standings(s)
    alive = [seat for seat in order if not s["players"][seat]["bankrupt"]]
    capitals = [engine.capital(s, seat) for seat in alive]
    assert capitals == sorted(capitals, reverse=True)


def test_rounds_count_whole_table_turns():
    s = _state(max_rounds=12)
    for seat in range(4):
        engine.apply_action(s, seat, "roll", dice=[1, 3])  # Порту / buy phase for each in turn
        engine.apply_action(s, seat, "skip")
    assert s["round"] == 2 and s["turn"] == 0


def test_standings_put_later_bankruptcies_higher():
    s = _state()
    s["players"][2].update(bankrupt=True, bankrupt_order=1, cash=0)
    s["players"][3].update(bankrupt=True, bankrupt_order=2, cash=0)
    s["players"][1]["cash"] = 2000
    assert engine.standings(s) == [1, 0, 3, 2]


# ---------------------------------------------------------------------------
# Engine: event cards
# ---------------------------------------------------------------------------

def _force_card(s: dict, deck: str, index: int) -> None:
    s["decks"][deck] = [index]
    s["deck_pos"][deck] = 0


def test_var_card_move_to_start_pays_bonus():
    s = _state()
    _force_card(s, "var", 0)
    s["players"][0]["pos"] = LISBON
    engine.apply_action(s, 0, "roll", dice=[1, 2])
    p = s["players"][0]
    assert p["pos"] == 0 and p["cash"] == 1700 and s["turn"] == 1


def test_var_card_move_back_resolves_the_new_cell():
    s = _state()
    _force_card(s, "var", 1)
    s["players"][0]["pos"] = LISBON
    engine.apply_action(s, 0, "roll", dice=[1, 2])
    assert s["players"][0]["pos"] == LISBON and s["phase"] == "buy"


def test_var_card_appeal_and_money():
    s = _state()
    _force_card(s, "var", 3)
    s["players"][0]["pos"] = LISBON
    engine.apply_action(s, 0, "roll", dice=[1, 2])
    assert s["players"][0]["jail_cards"] == 1
    _force_card(s, "var", 7)
    _turn_back(s)
    s["players"][0]["pos"] = LISBON
    engine.apply_action(s, 0, "roll", dice=[1, 2])
    assert s["players"][0]["cash"] == 1450


def test_transfer_card_collect_from_each_and_repairs():
    s = _state()
    _force_card(s, "transfer", 2)
    s["players"][0]["pos"] = 12
    engine.apply_action(s, 0, "roll", dice=[1, 2])
    assert s["players"][0]["cash"] == 1500 + 3 * 25 and all(s["players"][i]["cash"] == 1475 for i in (1, 2, 3))

    s = _state()
    _force_card(s, "transfer", 4)
    s["owner"][AMSTERDAM] = s["owner"][ROTTERDAM] = 0
    s["level"][AMSTERDAM] = engine.MAX_LEVEL
    s["level"][ROTTERDAM] = 2
    s["players"][0]["pos"] = 12
    engine.apply_action(s, 0, "roll", dice=[1, 2])
    assert s["players"][0]["cash"] == 1500 - (2 * 40 + 115)


def test_nearest_stadium_card():
    s = _state()
    _force_card(s, "var", 5)
    s["players"][0]["pos"] = LISBON
    engine.apply_action(s, 0, "roll", dice=[1, 2])
    assert s["players"][0]["pos"] == STADIUM_E and s["phase"] == "buy"


# ---------------------------------------------------------------------------
# Engine: determinism and the bot
# ---------------------------------------------------------------------------

def test_same_seed_replays_the_same_game():
    a, b = _state(bots=True, seed="same"), _state(bots=True, seed="same")
    engine.run_bots(a)
    engine.run_bots(b)
    assert a["finished"] and a == b
    c = _state(bots=True, seed="other")
    engine.run_bots(c)
    assert c["log"] != a["log"]


def test_bot_buys_only_above_its_reserve():
    s = _state()
    s["players"][0]["pos"] = 20
    s["players"][0]["cash"] = 500
    engine.apply_action(s, 0, "roll", dice=[1, 2])
    assert engine.bot_action(s, 0) == ("buy", None)  # 500 − 350 = 150 ≥ reserve
    s["players"][0]["cash"] = 499
    assert engine.bot_action(s, 0) == ("skip", None)


def test_bot_builds_on_a_full_group_while_keeping_its_reserve():
    s = _state()
    s["owner"][AMSTERDAM] = s["owner"][ROTTERDAM] = 0
    s["players"][0]["cash"] = 1000
    assert engine.bot_action(s, 0) == ("build", AMSTERDAM)
    s["players"][0]["cash"] = 299  # 299 − 50 < 250
    assert engine.bot_action(s, 0) == ("roll", None)
    s["players"][0].update(cash=1000, in_jail=True, jail_cards=1)
    s["owner"][AMSTERDAM] = None
    assert engine.bot_action(s, 0) == ("use_card", None)


def test_validation_rejects_broken_boards_and_cards():
    bad = copy.deepcopy(engine.DEFAULT_BOARD)
    bad["cells"] = bad["cells"][:-1]
    with pytest.raises(engine.EngineError):
        engine.validate_board(bad)
    bad = copy.deepcopy(engine.DEFAULT_BOARD)
    bad["cells"][1]["group"] = 99
    with pytest.raises(engine.EngineError):
        engine.validate_board(bad)
    bad = copy.deepcopy(engine.DEFAULT_BOARD)
    bad["cells"][1]["rent"] = [1, 2]
    with pytest.raises(engine.EngineError):
        engine.validate_board(bad)
    with pytest.raises(engine.EngineError):
        engine.validate_cards({"var": [{"kind": "teleport", "text": "x"}], "transfer": []})


# ---------------------------------------------------------------------------
# Service / API
# ---------------------------------------------------------------------------

async def _login(client, bot_token, tg_id: int, name: str = "Test") -> dict:
    headers = telegram_headers(tg_id, bot_token, first_name=name)
    assert (await client.post("/api/v1/auth/session", headers=headers)).status_code == 200
    return headers


async def _config(db_session) -> GameConfig:
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
        await db_session.commit()
    return config


async def _set_config(db_session, **values) -> None:
    config = await _config(db_session)
    for k, v in values.items():
        setattr(config, k, v)
    await db_session.commit()


async def _match_row(db_session, match_id: int) -> MagnateMatch:
    result = await db_session.execute(
        select(MagnateMatch).where(MagnateMatch.id == match_id).execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def _expire_turn(db_session, match_id: int) -> None:
    row = await _match_row(db_session, match_id)
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    state = copy.deepcopy(row.server_state)
    state["deadline"] = past.isoformat()
    row.server_state = state
    flag_modified(row, "server_state")
    row.next_deadline_at = past
    await db_session.commit()


async def _expire_lobby(db_session, match_id: int) -> None:
    row = await _match_row(db_session, match_id)
    row.next_deadline_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()


async def _play_out(client, headers, db_session, match_id: int) -> dict:
    """Plays the viewer's turns with the bot policy until the match ends."""
    for _ in range(800):
        m = (await client.get(f"{API}/matches/{match_id}", headers=headers)).json()
        if m["status"] == "finished":
            return m
        if not m["my_turn"]:
            pytest.fail(f"waiting on another human: {m['turn']}")
        state = (await _match_row(db_session, match_id)).server_state
        action, cell = engine.bot_action(state, m["my_seat"])
        r = await client.post(
            f"{API}/matches/{match_id}/action", headers=headers,
            json={"action": action, "cell": cell, "version": m["version"]},
        )
        assert r.status_code == 200, r.text
    pytest.fail("match never finished")


async def test_bot_match_starts_on_my_decision(client, bot_token, db_session):
    headers = await _login(client, bot_token, 7100001)
    r = await client.post(f"{API}/matches/bot", headers=headers)
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["mode"] == "bot" and m["status"] == "in_progress" and m["my_seat"] == 0
    assert [p["is_bot"] for p in m["players"]] == [False, True, True, True]
    assert m["my_turn"] and m["phase"] == "roll" and m["deadline"] is not None
    assert all(p["cash"] > 0 for p in m["players"])
    # Nothing secret leaves the server.
    assert "seed" not in r.text and "deck" not in r.text
    user = await get_user_by_telegram_id(db_session, 7100001)
    assert user.magnate_hourly_attempts == 1
    limits = (await client.get("/api/v1/games/limits", headers=headers)).json()
    assert limits["magnate"] == limits["hourly_limit"] - 1

    r = await client.post(f"{API}/matches/{m['id']}/action", headers=headers, json={"action": "roll", "version": m["version"]})
    assert r.status_code == 200, r.text
    after = r.json()
    # Bots may already have rolled after us — look for our roll in the feed.
    assert after["version"] > m["version"] and any(e["seat"] == 0 and e["kind"] == "roll" for e in after["log"])


async def test_stale_version_and_duplicate_submit_are_rejected(client, bot_token):
    headers = await _login(client, bot_token, 7100002)
    m = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    body = {"action": "roll", "version": m["version"]}
    first = await client.post(f"{API}/matches/{m['id']}/action", headers=headers, json=body)
    second = await client.post(f"{API}/matches/{m['id']}/action", headers=headers, json=body)
    assert first.status_code == 200
    assert second.status_code == 409 and second.json()["error"]["details"]["version"] == first.json()["version"]


async def test_full_bot_match_pays_by_place_within_daily_limit(client, bot_token, db_session):
    await _set_config(db_session, magnate_max_rounds=3, magnate_place_rewards=[100, 50, 20, 10], magnate_bot_reward_pct=50)
    headers = await _login(client, bot_token, 7100003)
    m = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    final = await _play_out(client, headers, db_session, m["id"])
    assert final["finish_reason"] in ("rounds", "last_standing")
    place = final["my_place"]
    assert place in (1, 2, 3, 4) and sorted(p["place"] for p in final["players"]) == [1, 2, 3, 4]
    expected = round([100, 50, 20, 10][place - 1] * 50 / 100)
    assert final["my_reward"] == expected
    user = await get_user_by_telegram_id(db_session, 7100003)
    await db_session.refresh(user)
    assert user.magnate_rewarded_attempts_today == 1 and user.magnate_wins == (1 if place == 1 else 0)
    txs = (await db_session.execute(
        select(CoinTransaction).where(CoinTransaction.user_id == user.id, CoinTransaction.type == TransactionType.magnate_reward)
    )).scalars().all()
    assert [t.amount for t in txs] == ([expected] if expected else [])

    # Daily limit reached: the next match still plays but pays nothing.
    await _set_config(db_session, magnate_daily_limit=1)
    m2 = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    final2 = await _play_out(client, headers, db_session, m2["id"])
    assert final2["my_reward"] == 0
    info = (await client.get(f"{API}/info", headers=headers)).json()
    assert info["rewarded_today"] == 1 and info["daily_limit"] == 1 and info["active_match_id"] is None


async def test_timeout_autoplays_then_bot_replaces_the_player(client, bot_token, db_session):
    await _set_config(db_session, magnate_max_missed_turns=2)
    headers = await _login(client, bot_token, 7100004)
    m = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    await _expire_turn(db_session, m["id"])
    m1 = (await client.get(f"{API}/matches/{m['id']}", headers=headers)).json()
    me = m1["players"][0]
    assert me["missed"] == 1 and not me["is_bot"] and m1["status"] == "in_progress" and m1["my_turn"]
    assert any("автопилот" in e["text"] for e in m1["log"])

    await _expire_turn(db_session, m["id"])
    m2 = (await client.get(f"{API}/matches/{m['id']}", headers=headers)).json()
    # The only human was replaced: nothing left to wait for.
    assert m2["players"][0]["left"] and m2["status"] == "finished" and m2["finish_reason"] == "abandoned"
    assert m2["my_reward"] == 0 and m2["my_place"] is not None
    seat = (await db_session.execute(select(MagnateSeat).where(MagnateSeat.match_id == m["id"], MagnateSeat.seat == 0))).scalar_one()
    assert seat.replaced_by_bot


async def test_acting_resets_the_missed_counter(client, bot_token, db_session):
    headers = await _login(client, bot_token, 7100005)
    m = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    await _expire_turn(db_session, m["id"])
    m1 = (await client.get(f"{API}/matches/{m['id']}", headers=headers)).json()
    assert m1["players"][0]["missed"] == 1
    state = (await _match_row(db_session, m["id"])).server_state
    action, cell = engine.bot_action(state, 0)
    m2 = (await client.post(f"{API}/matches/{m['id']}/action", headers=headers, json={"action": action, "cell": cell})).json()
    assert m2["players"][0]["missed"] == 0


async def test_time_limit_ends_the_match_by_capital(client, bot_token, db_session):
    headers = await _login(client, bot_token, 7100006)
    m = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    row = await _match_row(db_session, m["id"])
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    state = copy.deepcopy(row.server_state)
    state["ends_at"] = past.isoformat()
    row.server_state = state
    flag_modified(row, "server_state")
    row.next_deadline_at = past
    await db_session.commit()
    final = (await client.get(f"{API}/matches/{m['id']}", headers=headers)).json()
    assert final["status"] == "finished" and final["finish_reason"] == "time" and final["my_place"] is not None


async def test_public_lobby_fills_with_bots_after_the_wait(client, bot_token, db_session):
    a = await _login(client, bot_token, 7100010, "Анна")
    b = await _login(client, bot_token, 7100011, "Борис")
    la = (await client.post(f"{API}/lobby/join", headers=a)).json()
    assert la["status"] == "lobby" and la["lobby_deadline"] and len(la["players"]) == 1
    lb = (await client.post(f"{API}/lobby/join", headers=b)).json()
    assert lb["id"] == la["id"] and len(lb["players"]) == 2 and lb["my_seat"] == 1

    assert (await client.post("/api/v1/internal/magnate/sweep", headers=INTERNAL_HEADERS)).json() == {"advanced": 0}
    await _expire_lobby(db_session, la["id"])
    assert (await client.post("/api/v1/internal/magnate/sweep", headers=INTERNAL_HEADERS)).json() == {"advanced": 1}
    started = (await client.get(f"{API}/matches/{la['id']}", headers=a)).json()
    assert started["status"] == "in_progress"
    assert [p["is_bot"] for p in started["players"]] == [False, False, True, True]
    assert (await _match_row(db_session, la["id"])).server_state["reward_pct"] == 100
    assert started["turn"] in (0, 1)  # bots already moved up to a human decision


async def test_lonely_public_lobby_pays_vs_bots_rate(client, bot_token, db_session):
    await _set_config(db_session, magnate_bot_reward_pct=40)
    a = await _login(client, bot_token, 7100015)
    lobby = (await client.post(f"{API}/lobby/join", headers=a)).json()
    await _expire_lobby(db_session, lobby["id"])
    await client.get(f"{API}/matches/{lobby['id']}", headers=a)
    assert (await _match_row(db_session, lobby["id"])).server_state["reward_pct"] == 40


async def test_full_public_lobby_starts_immediately(client, bot_token):
    heads = [await _login(client, bot_token, 7100020 + i) for i in range(4)]
    joined = [(await client.post(f"{API}/lobby/join", headers=h)).json() for h in heads]
    assert len({j["id"] for j in joined}) == 1
    assert joined[-1]["status"] == "in_progress" and not any(p["is_bot"] for p in joined[-1]["players"])
    fifth = await _login(client, bot_token, 7100029)
    other = (await client.post(f"{API}/lobby/join", headers=fifth)).json()
    assert other["id"] != joined[0]["id"] and other["status"] == "lobby"


async def test_leaving_a_lobby_refunds_and_cancels_when_empty(client, bot_token, db_session):
    headers = await _login(client, bot_token, 7100030)
    lobby = (await client.post(f"{API}/lobby/join", headers=headers)).json()
    r = await client.post(f"{API}/matches/{lobby['id']}/leave", headers=headers)
    assert r.status_code == 200 and r.json() is None
    user = await get_user_by_telegram_id(db_session, 7100030)
    await db_session.refresh(user)
    assert user.magnate_hourly_attempts == 0
    assert (await _match_row(db_session, lobby["id"])).status == "cancelled"


async def test_private_room_invite_flow(client, bot_token, db_session):
    a = await _login(client, bot_token, 7100040, "Хозяин")
    b = await _login(client, bot_token, 7100041, "Гость")
    stranger = await _login(client, bot_token, 7100042)
    room = (await client.post(f"{API}/rooms", headers=a)).json()
    code = room["invite_code"]
    assert room["mode"] == "private" and room["is_creator"] and code

    preview = (await client.get(f"{API}/rooms/{code}", headers=b)).json()
    assert preview["creator_name"] == "Хозяин" and preview["players"] == ["Хозяин"] and not preview["is_member"]
    assert (await client.get(f"{API}/matches/{room['id']}", headers=stranger)).status_code == 403

    joined = (await client.post(f"{API}/rooms/{code}/join", headers=b)).json()
    assert joined["status"] == "lobby" and len(joined["players"]) == 2 and not joined["is_creator"]
    again = await client.post(f"{API}/rooms/{code}/join", headers=b)
    assert again.status_code == 200 and again.json()["my_seat"] == joined["my_seat"]

    assert (await client.post(f"{API}/matches/{room['id']}/start", headers=b)).status_code == 403
    started = (await client.post(f"{API}/matches/{room['id']}/start", headers=a)).json()
    assert started["status"] == "in_progress" and [p["is_bot"] for p in started["players"]] == [False, False, True, True]
    late = await client.post(f"{API}/rooms/{code}/join", headers=stranger)
    assert late.status_code == 409


async def test_out_of_turn_action_is_rejected(client, bot_token):
    a = await _login(client, bot_token, 7100050)
    b = await _login(client, bot_token, 7100051)
    room = (await client.post(f"{API}/rooms", headers=a)).json()
    await client.post(f"{API}/rooms/{room['invite_code']}/join", headers=b)
    started = (await client.post(f"{API}/matches/{room['id']}/start", headers=a)).json()
    waiting = b if started["my_turn"] else a
    view = (await client.get(f"{API}/matches/{room['id']}", headers=waiting)).json()
    assert not view["my_turn"]
    r = await client.post(f"{API}/matches/{room['id']}/action", headers=waiting, json={"action": "roll", "version": view["version"]})
    assert r.status_code == 409


async def test_private_room_alone_is_cancelled_at_the_deadline(client, bot_token, db_session):
    a = await _login(client, bot_token, 7100060)
    room = (await client.post(f"{API}/rooms", headers=a)).json()
    await _expire_lobby(db_session, room["id"])
    view = (await client.get(f"{API}/matches/{room['id']}", headers=a)).json()
    assert view["status"] == "cancelled"
    user = await get_user_by_telegram_id(db_session, 7100060)
    await db_session.refresh(user)
    assert user.magnate_hourly_attempts == 0


async def test_leaving_mid_game_hands_the_seat_to_a_bot_without_reward(client, bot_token, db_session):
    await _set_config(db_session, magnate_max_rounds=2)
    a = await _login(client, bot_token, 7100070)
    b = await _login(client, bot_token, 7100071)
    room = (await client.post(f"{API}/rooms", headers=a)).json()
    await client.post(f"{API}/rooms/{room['invite_code']}/join", headers=b)
    await client.post(f"{API}/matches/{room['id']}/start", headers=a)
    left = (await client.post(f"{API}/matches/{room['id']}/leave", headers=b)).json()
    assert left["players"][1]["left"] and left["players"][1]["is_bot"]
    assert (await client.post(f"{API}/matches/{room['id']}/action", headers=b, json={"action": "roll"})).status_code == 403
    final = await _play_out(client, a, db_session, room["id"])
    seat_b = (await db_session.execute(
        select(MagnateSeat).where(MagnateSeat.match_id == room["id"], MagnateSeat.seat == 1).execution_options(populate_existing=True)
    )).scalar_one()
    assert final["status"] == "finished" and seat_b.place is not None and seat_b.reward_coins == 0
    # b may start something new right away.
    assert (await client.post(f"{API}/matches/bot", headers=b)).status_code == 200


async def test_one_table_at_a_time_and_hourly_limit(client, bot_token, db_session):
    await _set_config(db_session, hourly_game_limit=2)
    headers = await _login(client, bot_token, 7100080)
    m = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    assert (await client.post(f"{API}/lobby/join", headers=headers)).status_code == 409
    assert (await client.post(f"{API}/rooms", headers=headers)).status_code == 409
    await client.post(f"{API}/matches/{m['id']}/leave", headers=headers)
    assert (await client.post(f"{API}/matches/bot", headers=headers)).status_code == 200
    m3 = (await client.get(f"{API}/matches", headers=headers)).json()
    assert len(m3) == 2 and m3[1]["left"]
    active = m3[0]["id"]
    await client.post(f"{API}/matches/{active}/leave", headers=headers)
    blocked = await client.post(f"{API}/matches/bot", headers=headers)
    assert blocked.status_code == 409 and "retry_after_seconds" in blocked.json()["error"]["details"]


async def test_internal_sweep_requires_the_secret(client):
    assert (await client.post("/api/v1/internal/magnate/sweep", headers={"X-Internal-Secret": "wrong"})).status_code == 401


async def test_sweep_and_read_do_not_double_process_a_deadline(client, bot_token, db_session):
    headers = await _login(client, bot_token, 7100090)
    m = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    await _expire_turn(db_session, m["id"])
    r1 = await client.post("/api/v1/internal/magnate/sweep", headers=INTERNAL_HEADERS)
    r2 = await client.post("/api/v1/internal/magnate/sweep", headers=INTERNAL_HEADERS)
    view = (await client.get(f"{API}/matches/{m['id']}", headers=headers)).json()
    assert r1.json() == {"advanced": 1} and r2.json() == {"advanced": 0}
    assert view["players"][0]["missed"] == 1


async def test_admin_edits_board_and_validates_it(client, bot_token, db_session):
    auth = await _admin_auth(client, bot_token)
    defaults = (await client.get("/api/v1/admin/games/magnate-defaults", headers=auth)).json()
    board = defaults["board"]
    board["cells"][1]["name"] = "Гронинген"
    board["groups"][0]["name"] = "Эредивизи"
    bad = copy.deepcopy(board)
    bad["cells"][1]["rent"] = [1]
    r = await client.put("/api/v1/admin/games/config", headers=auth, json={"magnate_board": bad})
    assert r.status_code == 409 and "магнат" in r.json()["error"]["message"]
    r = await client.put("/api/v1/admin/games/config", headers=auth, json={"magnate_board": board, "magnate_max_rounds": 8})
    assert r.status_code == 200, r.text
    assert r.json()["magnate_board"]["cells"][1]["name"] == "Гронинген"

    headers = await _login(client, bot_token, 7100100)
    m = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    assert m["cells"][1]["name"] == "Гронинген" and m["groups"][0]["name"] == "Эредивизи" and m["max_rounds"] == 8
