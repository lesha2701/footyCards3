"""Card Arena divisions, four-style tactics, the balance and the pre-match
opponent preview / match report."""
from types import SimpleNamespace

import pytest

import app.core.rate_limit as rate_limit_module
from app.models.enums import MatchResult
from app.models.game_config import GameConfig
from app.services import arena_ladder_service, arena_tactics, match_service
from tests.factories import get_user_by_telegram_id
from tests.test_lineups_matches import _build_full_squad, _play_to_completion
from tests.utils import telegram_headers


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


def _config(**overrides) -> SimpleNamespace:
    values = {}
    for column in GameConfig.__table__.columns:
        if column.default is not None:
            arg = column.default.arg
            values[column.name] = arg(None) if callable(arg) else arg
    values.update(overrides)
    return SimpleNamespace(**values)


# --- styles -----------------------------------------------------------------

def test_styles_beat_each_other_in_a_circle():
    for style in arena_tactics.STYLES:
        beaten = arena_tactics.BEATS[style]
        assert arena_tactics.matchup(style, beaten) == "win"
        assert arena_tactics.matchup(beaten, style) == "loss"
        assert arena_tactics.matchup(style, style) == "neutral"
    # every style is beaten by exactly one other
    assert sorted(arena_tactics.BEATS.values()) == sorted(arena_tactics.STYLES)
    assert arena_tactics.matchup("attacking", "possession") == "neutral"


def test_legacy_balanced_reads_as_possession():
    assert arena_tactics.resolve_style("balanced") == "possession"
    assert arena_tactics.resolve_style(None) == "possession"
    assert arena_tactics.resolve_style("nonsense") == "possession"


def test_balance_is_neutral_for_equal_squads_and_favours_the_stronger():
    config = _config()
    even = arena_tactics.compute_balance(900, "possession", 900, "possession", config)
    assert even["share"] == pytest.approx(0.5)
    assert even["edge"] == 0
    assert even["user_shot_weight"] == even["opponent_shot_weight"]

    strong = arena_tactics.compute_balance(1100, "possession", 850, "possession", config)
    assert strong["share"] > 0.55
    assert strong["edge"] > 0
    assert strong["user_shot_weight"] > strong["opponent_shot_weight"]

    huge = arena_tactics.compute_balance(3000, "possession", 300, "possession", config)
    assert huge["edge"] == config.arena_edge_rating_max


def test_style_matchup_bonus_tips_an_even_match():
    config = _config()
    win = arena_tactics.compute_balance(900, "counter", 900, "attacking", config)
    assert win["matchup"] == "win" and win["matchup_bonus_pct"] == config.arena_style_matchup_bonus_pct
    assert win["strength_ratio"] > 1
    loss = arena_tactics.compute_balance(900, "attacking", 900, "counter", config)
    assert loss["matchup"] == "loss" and loss["strength_ratio"] < 1


def test_win_chances_follow_the_strength_ratio():
    favourite = match_service.win_chances(1.3)
    even = match_service.win_chances(1.0)
    underdog = match_service.win_chances(1 / 1.3)
    assert favourite["win"] >= 80 and favourite["loss"] <= 6
    assert underdog["loss"] >= 60
    assert favourite["win"] > even["win"] > underdog["win"]
    for chances in (favourite, even, underdog):
        assert chances["win"] + chances["draw"] + chances["loss"] == 100


# --- ladder -----------------------------------------------------------------

def test_points_change_is_elo_like():
    config = _config()
    assert arena_ladder_service.points_change(500, 500, MatchResult.win, config) == 20
    assert arena_ladder_service.points_change(500, 500, MatchResult.loss, config) == -20
    assert arena_ladder_service.points_change(500, 500, MatchResult.draw, config) == 0
    # beating a higher-ranked opponent pays more, losing to a lower one costs more
    assert arena_ladder_service.points_change(500, 700, MatchResult.win, config) > 20
    assert arena_ladder_service.points_change(500, 300, MatchResult.loss, config) < -20


def test_division_of_uses_thresholds():
    config = _config()
    assert arena_ladder_service.division_of(0, config) == 1
    assert arena_ladder_service.division_of(99, config) == 1
    assert arena_ladder_service.division_of(100, config) == 2
    assert arena_ladder_service.division_of(5000, config) == len(config.arena_division_min_points)


async def _make_user(client, db_session, bot_token, telegram_id: int):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    return headers, await get_user_by_telegram_id(db_session, telegram_id)


async def test_promotion_grants_reward_once_and_shield_blocks_relegation(client, db_session, bot_token):
    _, user = await _make_user(client, db_session, bot_token, 760001)
    config = _config()
    user.arena_points = 95
    balance_before = user.balance

    ladder = await arena_ladder_service.apply_result(db_session, user, 95, MatchResult.win, config)
    await db_session.commit()
    assert ladder["promoted"] and ladder["division_after"] == 2
    assert ladder["rewards"] == [{"division": 2, "coins": config.arena_division_reward_coins[1]}]
    assert user.balance == balance_before + config.arena_division_reward_coins[1]
    assert user.arena_shield_matches == config.arena_shield_matches

    # A loss right after promotion: the shield holds the division floor.
    ladder = await arena_ladder_service.apply_result(db_session, user, user.arena_points, MatchResult.loss, config)
    assert ladder["shield_used"] and user.arena_points == 100
    assert user.arena_shield_matches == config.arena_shield_matches - 1

    # Shield gone: a loss relegates; promoting again pays nothing new.
    user.arena_shield_matches = 0
    ladder = await arena_ladder_service.apply_result(db_session, user, user.arena_points, MatchResult.loss, config)
    assert ladder["relegated"] and ladder["division_after"] == 1
    coins = user.balance
    user.arena_points = 99
    ladder = await arena_ladder_service.apply_result(db_session, user, 99, MatchResult.win, config)
    assert ladder["promoted"] and ladder["rewards"] == [] and user.balance == coins


async def test_points_never_go_negative(client, db_session, bot_token):
    _, user = await _make_user(client, db_session, bot_token, 760002)
    ladder = await arena_ladder_service.apply_result(db_session, user, 0, MatchResult.loss, _config())
    assert user.arena_points == 0 and ladder["delta"] == 0


# --- API --------------------------------------------------------------------

async def test_preview_is_stable_until_the_match_is_played(client, db_session, bot_token):
    headers, user = await _make_user(client, db_session, bot_token, 760003)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    resp = await client.post("/api/v1/matches/opponent", headers=headers)
    assert resp.status_code == 200
    preview = resp.json()
    assert preview["opponent_is_bot"]  # nobody else exists
    assert [line["key"] for line in preview["lines"]] == ["GK", "DEF", "MID", "FWD"]
    assert set(preview["points_at_stake"]) == {"win", "draw", "loss"}
    assert preview["division"]["division"] == 1
    assert sum(preview["chances"].values()) == 100

    again = (await client.post("/api/v1/matches/opponent", headers=headers)).json()
    assert again["opponent_name"] == preview["opponent_name"]
    assert again["opponent_style"] == preview["opponent_style"]

    # Switching the style changes the matchup line, not the opponent.
    await client.post("/api/v1/lineups/tactic", headers=headers, json={"tactic": "counter"})
    switched = (await client.post("/api/v1/matches/opponent", headers=headers)).json()
    assert switched["opponent_name"] == preview["opponent_name"] and switched["user_style"] == "counter"

    match = await _play_to_completion(client, headers)
    assert match["opponent_name"] == preview["opponent_name"]
    await db_session.refresh(user)
    assert user.arena_pending_opponent is None
    assert user.arena_last_strength is not None


async def test_finished_match_has_report_and_moves_the_ladder(client, db_session, bot_token):
    headers, user = await _make_user(client, db_session, bot_token, 760004)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    match = await _play_to_completion(client, headers)
    assert match["status"] == "finished"
    assert match["arena"]["user_style"] in arena_tactics.STYLES
    ladder = match["ladder"]
    assert ladder["points_after"] == ladder["points_before"] + ladder["delta"]
    report = match["report"]
    assert report["verdict"] and report["reasons"]
    assert [line["key"] for line in report["lines"]] == ["GK", "DEF", "MID", "FWD"]

    await db_session.refresh(user)
    assert user.arena_points == ladder["points_after"]
    stats = (await client.get("/api/v1/matches/stats", headers=headers)).json()
    assert stats["division"]["points"] == user.arena_points


async def test_forfeit_counts_as_a_ladder_loss(client, db_session, bot_token):
    headers, user = await _make_user(client, db_session, bot_token, 760005)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})
    user.arena_points = 300
    await db_session.commit()

    match = (await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})).json()
    if match["status"] != "in_progress":
        pytest.skip("queue drew no interactive moment")
    resp = await client.post(f"/api/v1/matches/{match['id']}/forfeit", headers=headers)
    body = resp.json()
    assert body["result"] == "loss"
    assert body["ladder"]["delta"] < 0
    assert body["report"]["verdict"].startswith("Матч прерван")


async def test_opponent_is_found_among_arena_players_by_points(client, db_session, bot_token):
    headers, user = await _make_user(client, db_session, bot_token, 760006)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    near_headers, near = await _make_user(client, db_session, bot_token, 760007)
    near_slots = await _build_full_squad(db_session, near.id)
    await client.put("/api/v1/lineups/active", headers=near_headers, json={"slots": near_slots})
    far_headers, far = await _make_user(client, db_session, bot_token, 760008)
    near.arena_points, near.arena_last_strength = 520, 900
    far.arena_points, far.arena_last_strength = 2000, 900
    user.arena_points = 500
    await db_session.commit()

    preview = (await client.post("/api/v1/matches/opponent", headers=headers)).json()
    assert preview["opponent_name"] == near.full_display_name()
    assert not preview["opponent_is_bot"]
    assert preview["opponent_points"] == 520


# --- formations ---------------------------------------------------------------

def test_formation_tilts_chances_but_not_the_strength_edge():
    config = _config()
    attacking = arena_tactics.compute_balance(900, "possession", 900, "possession", config, user_formation="3-4-3")
    defensive = arena_tactics.compute_balance(900, "possession", 900, "possession", config, user_formation="5-3-2")
    assert attacking["user_shot_weight"] > defensive["user_shot_weight"]
    assert attacking["opponent_shot_weight"] > defensive["opponent_shot_weight"]
    assert attacking["edge"] == defensive["edge"] == 0
    off = arena_tactics.compute_balance(
        900, "possession", 900, "possession", _config(arena_formation_effect_pct=0), user_formation="3-4-3",
    )
    assert off["share"] == pytest.approx(0.5)


async def test_changing_formation_keeps_players_in_their_lines(client, db_session, bot_token):
    headers, user = await _make_user(client, db_session, bot_token, 760010)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    resp = await client.post("/api/v1/lineups/templates/1/formation", headers=headers, json={"formation": "3-5-2"})
    assert resp.status_code == 200
    lineup = resp.json()
    assert lineup["formation"] == "3-5-2"
    filled = [s for s in lineup["slots"] if s["card"]]
    by_cat = {cat: sum(1 for s in filled if s["category"] == cat) for cat in ("GK", "DEF", "MID", "FWD")}
    # 4 DEF -> 3 slots, 3 MID -> all kept (5 slots), 3 FWD -> 2 slots
    assert by_cat == {"GK": 1, "DEF": 3, "MID": 3, "FWD": 2}
    assert not lineup["is_complete"] and len(lineup["slots"]) == 11

    # Back to 4-3-3: the kept players return to their lines.
    back = (await client.post("/api/v1/lineups/templates/1/formation", headers=headers, json={"formation": "4-3-3"})).json()
    assert back["formation"] == "4-3-3"
    assert sum(1 for s in back["slots"] if s["card"]) == 9

    # 3-4-3 from the full 4-3-3: the right-back takes the right wing-back
    # slot, not the left one that shares his old code.
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})
    wide = (await client.post("/api/v1/lineups/templates/1/formation", headers=headers, json={"formation": "3-4-3"})).json()
    by_ideal = {s["ideal_position"]: s["card"] for s in wide["slots"]}
    assert by_ideal["RWB"] is not None and by_ideal["RWB"]["player"]["position"] == "RB"
    assert by_ideal["LWB"] is not None and by_ideal["LWB"]["player"]["position"] == "LB"

    bad = await client.post("/api/v1/lineups/templates/1/formation", headers=headers, json={"formation": "2-2-6"})
    assert bad.status_code == 409


async def test_match_and_preview_carry_the_formations(client, db_session, bot_token):
    headers, user = await _make_user(client, db_session, bot_token, 760011)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})
    await client.post("/api/v1/lineups/templates/1/formation", headers=headers, json={"formation": "4-3-3H"})
    lineup = (await client.get("/api/v1/lineups/active", headers=headers)).json()
    assert lineup["is_complete"]  # 4-3-3H has the same lines as 4-3-3

    preview = (await client.post("/api/v1/matches/opponent", headers=headers)).json()
    assert preview["user_formation"] == "4-3-3H"
    assert preview["opponent_formation"] in arena_tactics.FORMATION_SHIFT
    match = await _play_to_completion(client, headers)
    assert match["arena"]["user_formation"] == "4-3-3H"
    assert match["report"]["user_formation"] == "4-3-3H"
