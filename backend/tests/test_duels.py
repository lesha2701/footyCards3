"""Flank duels of «Карьера тренера» (services/duel_service.py): styles and
their rock-paper-scissors, known rivalries, the global history (fear /
favourite opponent), the left/right flank pick in the engine, the season
integration, the «Дуэли на флангах» preview and the admin."""
import random

import pytest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import select

from app.models.career import CareerSeason
from app.models.duel import DuelHistory, PlayerRivalry
from app.models.enums import Position
from app.models.player import Player
from app.services import career_service, duel_service
from app.services import career_tactics_service as tactics
from app.services import club_tactical_matchup_service as matchup
from tests.test_career import _reset_rate_limits  # noqa: F401  (autouse fixture)
from tests.test_career_tactics import API, _defaults, _runner, _season
from tests.utils import telegram_headers

TUNING = duel_service.DEFAULT_TUNING


def _book(players: dict, rivalries=None, history=None) -> duel_service.DuelBook:
    return duel_service.DuelBook(tuning=dict(TUNING), players=players, rivalries=rivalries or {}, history=history or {})


def _c(player_id: int):
    return SimpleNamespace(id=1000 + player_id, player_id=player_id)


# --- the table ------------------------------------------------------------------------------

def test_matrix_is_a_fair_rock_paper_scissors():
    attackers = ("speed", "technique", "power")
    defenders = ("speed", "power", "reading")
    for a in attackers:
        assert sorted(duel_service.MATRIX[(a, d)] for d in defenders) == [-1, 0, 1]
    for d in defenders:
        assert sorted(duel_service.MATRIX[(a, d)] for a in attackers) == [-1, 0, 1]
    # The logic in words: a fast defender stops the speedster, the technician beats him.
    assert duel_service.MATRIX[("speed", "speed")] == -1 and duel_service.MATRIX[("technique", "speed")] == 1
    assert duel_service.MATRIX[("technique", "reading")] == -1 and duel_service.MATRIX[("power", "reading")] == 1


def test_style_is_set_or_derived_stably():
    lb = SimpleNamespace(display_name="Нуну Мендеш", person_key=None, position=Position.LB, duel_style=None)
    assert duel_service.style_of(lb) in ("speed", "power", "reading")
    assert duel_service.style_of(lb) == duel_service.style_of(lb)
    lb.duel_style = "speed"
    assert duel_service.style_of(lb) == "speed"
    # The same field in both roles of a duel.
    assert duel_service.AS_ATTACKER["reading"] == "technique" and duel_service.AS_DEFENDER["technique"] == "reading"


def test_sides_by_slot():
    assert duel_service.side_of(Position.LB) == "left" and duel_service.side_of("RW") == "right"
    assert duel_service.side_of(Position.ST) is None


# --- the edge -------------------------------------------------------------------------------

def test_edge_adds_style_rivalry_and_history_within_the_cap():
    yamal, mendes, other = _c(1), _c(2), _c(3)
    players = {1: ("ямаль", "speed", "Ямаль"), 2: ("мендеш", "speed", "Мендеш"), 3: ("бэк", "power", "Бэк")}
    book = _book(players)
    assert book.edge(yamal, other)["bias"] == TUNING["style"]          # speedster vs a slow full-back
    assert book.edge(yamal, mendes)["bias"] == -TUNING["style"]        # vs a fast one
    book.rivalries[("ямаль", "мендеш")] = -3
    book.history[("ямаль", "мендеш")] = (5.0, 20.0)                   # 80% lost: fear level 2
    edge = book.edge(yamal, mendes)
    assert edge["rivalry"] == -3 and edge["history"] == -2
    assert edge["bias"] == -TUNING["cap"]                              # capped
    assert duel_service.pp(edge["bias"]) == -10
    # Unknown players (e.g. «Мой игрок») have no edge.
    assert book.edge(yamal, _c(99)) is None


def test_history_needs_enough_duels_and_turns_into_fear_or_a_favourite():
    assert duel_service.history_level(2, 8, TUNING) == 0         # too few
    assert duel_service.history_level(8, 13, TUNING) == -1       # 62% lost
    assert duel_service.history_level(6, 15, TUNING) == -2       # 71% lost
    assert duel_service.history_level(15, 6, TUNING) == 2
    assert duel_service.history_level(11, 10, TUNING) == 0


def test_edge_bias_of_the_cap_moves_about_ten_points_of_duels_won():
    def won_share(bias):
        breakdown, _stall, advance = matchup._stage1_weights(0.5, bias)
        return advance / (advance + breakdown)
    swing = (won_share(TUNING["cap"]) - won_share(0)) * 100
    assert 8 <= swing <= 12


# --- the engine -----------------------------------------------------------------------------

def _duel_sides(flank="both"):
    config = _defaults()
    a = _runner("a", tactic={**tactics.NEUTRAL_TACTIC, "flank": flank}, config=config)
    b = _runner("b", config=config, offset=100)
    players = {p.card.player_id: (f"k{p.card.player_id}", "technique", p.card.player.display_name)
               for r in (a, b) for p in r.on_pitch}
    book = _book(players)
    a.duels = b.duels = book
    side_a, _lineup_a, _ = a.state_at(1, 0, 0)
    side_b, _lineup_b, _ = b.state_at(1, 0, 0)
    return a, b, side_a, side_b, book


def test_flank_attack_meets_the_opposite_full_back():
    a, b, side_a, side_b, _book_ = _duel_sides()
    random.seed(3)
    for flank in ("left", "right"):
        for _ in range(20):
            att, dfn = matchup._flank_duelists(side_a, side_b, flank, "wing_attack", "wing_defence")
            assert side_a.career.side_by_card[att.id] == flank
            assert side_b.career.side_by_card[dfn.id] == ("right" if flank == "left" else "left")


def test_flank_choice_leans_the_attacks():
    a, b, side_a, side_b, _ = _duel_sides(flank="left")
    random.seed(5)
    lefts = sum(side_a.career.flank_pick() == "left" for _ in range(2000))
    assert 0.65 < lefts / 2000 < 0.75


def test_engine_records_flank_duels_and_applies_the_edge():
    a, b, side_a, side_b, book = _duel_sides(flank="left")
    config = _defaults()
    random.seed(11)
    for minute in range(1, 400):
        matchup._resolve_progression_and_duel(side_a, side_b, "a", minute % 90 + 1, config)
    assert book.log, "flank duels are recorded"
    assert all(a_key.startswith("k") and d_key.startswith("k") for a_key, d_key, *_ in book.log)
    assert {where for *_, where in book.log} <= {"left", "right", "centre"}
    assert all(1 <= minute <= 90 for *_, minute, _where in book.log)
    # The edge is part of the duel's bias.
    att = next(p.card for p in a.on_pitch if p.slot.ideal_position == Position.LW)
    dfn = next(p.card for p in b.on_pitch if p.slot.ideal_position == Position.RB)
    book.rivalries[(book.info(att)[0], book.info(dfn)[0])] = -2
    bias, ids = side_a.career.player_shift(side_b.career, att, dfn, "wing_attack")
    assert "duel_hard" in ids and bias < 0
    _, ids = side_a.career.player_shift(side_b.career, att, dfn, "central_attack")
    assert "duel_hard" not in ids                                    # a winger is no centre duel


def test_centre_duels_striker_vs_centre_back_are_scaled():
    a, b, side_a, side_b, book = _duel_sides()
    st = next(p.card for p in a.on_pitch if p.slot.ideal_position == Position.ST)
    cb = next(p.card for p in b.on_pitch if p.slot.ideal_position == Position.CB)
    book.rivalries[(book.info(st)[0], book.info(cb)[0])] = -3
    flank_bias = book.edge(st, cb)["bias"]
    bias, ids = side_a.career.player_shift(side_b.career, st, cb, "central_attack")
    assert "duel_hard" in ids and bias == pytest.approx(flank_bias * TUNING["centre_scale"])
    # The engine records centre duels too.
    config = _defaults()
    random.seed(4)
    for minute in range(1, 600):
        matchup._resolve_progression_and_duel(side_a, side_b, "a", minute % 90 + 1, config)
    assert any(where == "centre" for *_, where in book.log)


def test_half_time_flank_switch_of_a_bot():
    book = _book({1: ("a", "speed", "A"), 2: ("d", "speed", "D")})
    for _ in range(4):
        book.record(_c(1), _c(2), "breakdown", 20, "left")
    book.record(_c(1), _c(2), "advance", 30, "left")
    book.record(_c(1), _c(2), "advance", 60, "left")                     # second half: not counted
    assert duel_service.halftime_flank(book, {"a"}, "left") == "right"
    assert duel_service.halftime_flank(book, {"a"}, "right") is None      # the right flank was fine
    assert duel_service.halftime_flank(book, {"a"}, "both") == "right"
    assert duel_service.halftime_flank(book, {"zzz"}, "left") is None


def test_adaptive_bot_switches_the_flank_after_the_break():
    a, b, side_a, side_b, book = _duel_sides(flank="left")
    a.adaptive_flank = True
    lw = next(p.card for p in a.on_pitch if p.slot.ideal_position == Position.LW)
    rb = next(p.card for p in b.on_pitch if p.slot.ideal_position == Position.RB)
    for _ in range(5):
        book.record(lw, rb, "breakdown", 30, "left")
    assert a._adapt_flank(40) == []
    events = a._adapt_flank(46)
    assert events and events[0]["payload"] == {"flank": "right"} and a.tactic["flank"] == "right"
    assert a.effective_tactic["flank"] == "right"
    assert a._adapt_flank(50) == []                                      # once


def test_first_half_report_and_match_stories():
    players = {1: ("ямаль", "speed", "Ямаль"), 2: ("мендеш", "speed", "Мендеш")}
    book = _book(players, rivalries={("ямаль", "мендеш"): -3}, history={("ямаль", "мендеш"): (8.0, 11.0)})
    for minute in (10, 20, 30, 40):
        book.record(_c(1), _c(2), "breakdown", minute, "right")
    report = duel_service.first_half(book, {"ямаль"})
    assert report["duels"] == [{"attacker": "Ямаль", "defender": "Мендеш", "attacker_wins": 0, "defender_wins": 4,
                                "mine": "attack", "flank": "right"}]
    assert report["hints"][0]["flank"] == "left" and "переведи атаки на левый фланг" in report["hints"][0]["text"]
    # Defender's side: their attacker loses — no hint for me.
    assert duel_service.first_half(book, {"мендеш"})["hints"] == []
    # 8:15 after the match — fear is born.
    assert duel_service.stories(book, {"ямаль"}) == ["Мендеш стал неудобным соперником для Ямаль: 8:15 в дуэлях."]
    beaten = _book(players, rivalries={("ямаль", "мендеш"): -3})
    for outcome in ("advance", "advance", "breakdown"):
        beaten.record(_c(1), _c(2), outcome, 10, "right")
    assert duel_service.stories(beaten, {"ямаль"}) == ["Ямаль переиграл своего «палача» Мендеш: 2:1."]
    assert duel_service.stories(beaten, {"чужой"}) == []


def test_without_a_book_the_engine_keeps_its_old_draws():
    config = _defaults()
    a, b = _runner("a", config=config), _runner("b", config=config, offset=100)
    side_a, _, _ = a.state_at(1, 0, 0)
    side_b, _, _ = b.state_at(1, 0, 0)
    assert side_a.career.duels is None and side_a.career.side_by_card == {}
    random.seed(7)
    first = [matchup._resolve_progression_and_duel(side_a, side_b, "a", 10, config) for _ in range(50)]
    random.seed(7)
    second = [matchup._resolve_progression_and_duel(side_a, side_b, "a", 10, config) for _ in range(50)]
    assert [getattr(c, "quality", None) for c in first] == [getattr(c, "quality", None) for c in second]


# --- history in the DB ----------------------------------------------------------------------

async def test_save_log_upserts_and_caps_the_history(db_session):
    book = _book({1: ("ямаль", "speed", "Ямаль"), 2: ("мендеш", "speed", "Мендеш")})
    book.tuning["history_cap"] = 10
    for outcome in ["breakdown"] * 6 + ["advance"] * 2 + ["stall"]:
        book.record(_c(1), _c(2), outcome)
    await duel_service.save_log(db_session, book)
    await duel_service.save_log(db_session, book)
    await db_session.commit()
    row = (await db_session.execute(select(DuelHistory))).scalar_one()
    # 16 decided duels, capped to 10 keeping the 3:1 ratio.
    assert round(row.attacker_wins + row.defender_wins, 6) == 10
    assert round(row.defender_wins / row.attacker_wins, 6) == 3
    loaded = await duel_service.load_book(db_session, set(), None)
    assert loaded.history == {}


# --- the season -----------------------------------------------------------------------------

async def test_a_season_with_duels_records_history_and_shows_the_preview(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 880001)
    row = await db_session.get(CareerSeason, season["id"])
    assert row.state.get("duels") == 1
    preview = (await client.get(f"{API}/career/duels", headers=headers)).json()
    assert preview["enabled"] and preview["flank"] == "both"
    assert {"attack", "defence", "centre", "hints"} <= set(preview)
    for hint in preview["hints"]:
        assert hint["text"] and all(a["kind"] in ("flank", "direction", "squad", "marking") for a in hint["actions"])
    view = (await client.get(f"{API}/career", headers=headers)).json()["season"]
    styles = [c["duel_style"] for c in view["squad"] if c["card"]]
    assert styles and all(s in duel_service.STYLES for s in styles)
    for duel in preview["attack"] + preview["defence"]:
        assert duel["verdict"] in ("easy", "hard", "even") and duel["flank"] in ("left", "right")

    later = datetime.now(timezone.utc) + timedelta(days=8)
    await career_service.resolve_due(db_session, season["id"], now=later)
    db_session.expire_all()
    assert (await db_session.execute(select(DuelHistory))).scalars().first() is not None
    row = await db_session.get(CareerSeason, season["id"])
    mine = [m for rnd in row.state["results"] for m in rnd if m.get("duels")]
    assert mine and all(isinstance(rows, list) for m in mine for rows in m["duels"].values())


async def test_an_old_season_without_the_flag_plays_without_duels(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 880002)
    row = await db_session.get(CareerSeason, season["id"])
    row.state = {k: v for k, v in row.state.items() if k != "duels"}
    await db_session.commit()
    assert (await client.get(f"{API}/career/duels", headers=headers)).json() == {"enabled": False}
    await career_service.resolve_due(db_session, season["id"], now=datetime.now(timezone.utc) + timedelta(days=8))
    assert (await db_session.execute(select(DuelHistory))).scalars().first() is None


# --- admin ----------------------------------------------------------------------------------

async def _admin(client, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(999000001, bot_token))
    return {"Authorization": f"Bearer {resp.json()['admin_token']}"}


async def test_admin_sets_styles_and_known_rivalries(client, db_session, bot_token):
    from tests.factories import create_player

    admin = await _admin(client, bot_token)
    yamal = await create_player(db_session, position=Position.RW, display_name="Ламин Ямаль")
    mendes = await create_player(db_session, position=Position.LB, display_name="Нуну Мендеш")
    resp = await client.put(f"/api/v1/admin/players/{mendes.id}", headers=admin, json={"duel_style": "speed"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["duel_style"] == "speed" and resp.json()["duel_style_auto"] == "speed"
    assert (await client.put(f"/api/v1/admin/players/{mendes.id}", headers=admin,
                             json={"duel_style": "magic"})).status_code == 422

    body = {"attacker_id": yamal.id, "defender_id": mendes.id, "level": -3, "note": "Мендеш гасит Ямаля"}
    data = (await client.post("/api/v1/admin/career/rivalries", headers=admin, json=body)).json()
    assert [(r["attacker"], r["defender"], r["level"]) for r in data["rivalries"]] == [("Ламин Ямаль", "Нуну Мендеш", -3)]
    rid = data["rivalries"][0]["id"]
    data = (await client.put(f"/api/v1/admin/career/rivalries/{rid}", headers=admin, json={**body, "level": -2})).json()
    assert data["rivalries"][0]["level"] == -2
    assert (await client.post("/api/v1/admin/career/rivalries", headers=admin,
                              json={**body, "defender_id": yamal.id})).status_code == 409
    book = await duel_service.load_book(db_session, {yamal.id, mendes.id}, None)
    assert book.rivalries == {("ламин ямаль", "нуну мендеш"): -2}
    data = (await client.delete(f"/api/v1/admin/career/rivalries/{rid}", headers=admin)).json()
    assert data["rivalries"] == []
    assert (await db_session.execute(select(PlayerRivalry))).scalars().first() is None
    assert (await client.get("/api/v1/admin/career/rivalries")).status_code in (401, 403)


async def test_admin_bulk_rivalries_and_duel_stats(client, db_session, bot_token):
    from tests.factories import create_player

    admin = await _admin(client, bot_token)
    yamal = await create_player(db_session, position=Position.RW, display_name="Ламин Ямаль")
    mendes = await create_player(db_session, position=Position.LB, display_name="Нуну Мендеш", duel_style="speed")
    await create_player(db_session, position=Position.LB, display_name="Двойник")
    await create_player(db_session, position=Position.RB, display_name="Двойник", person_key="другой двойник")
    text = "\n".join([
        "# комментарий", "Ламин Ямаль; Нуну Мендеш; -3; гасит", "ламин ямаль;Двойник;1", "Кто-то; Нуну Мендеш; 2",
        "Ламин Ямаль; Нуну Мендеш; 9", "Ламин Ямаль; Нуну Мендеш",
    ])
    data = (await client.post("/api/v1/admin/career/rivalries/bulk", headers=admin, json={"text": text})).json()
    assert data["bulk"]["saved"] == 1
    assert [e["line"] for e in data["bulk"]["errors"]] == [3, 4, 5, 6]
    assert "несколько" in data["bulk"]["errors"][0]["error"] and "не найден" in data["bulk"]["errors"][1]["error"]
    assert [(r["attacker"], r["level"], r["note"]) for r in data["rivalries"]] == [("Ламин Ямаль", -3, "гасит")]

    db_session.add(DuelHistory(attacker_key="ламин ямаль", defender_key="нуну мендеш", attacker_wins=6, defender_wins=18))
    await db_session.commit()
    stats = (await client.get("/api/v1/admin/career/duel-stats", headers=admin)).json()
    assert stats["pairs"] == 1 and stats["duels"] == 24 and stats["levels"]["-2"] == 1
    assert stats["rivalries"] == 1 and stats["players_explicit_style"] == 1
    a_type = duel_service.AS_ATTACKER[duel_service.style_of(yamal)]
    cell = next(c for c in stats["matrix"] if c["attacker_type"] == a_type and c["defender_type"] == "speed")
    assert cell["duels"] == 24 and cell["attacker_win_pct"] == 25.0
    assert len(stats["matrix"]) == 9


def test_duel_hints_never_contradict_about_the_centre():
    def d(flank, pp, verdict, **over):
        return {"attacker": "A", "defender": "D", "flank": flank, "pp": pp, "verdict": verdict, **over}

    centre_bad = [d("centre", -3, "hard"), d("centre", -3, "hard")]
    hints = career_service._duel_hints([d("left", -4, "hard")], [], centre_bad, {"flank": "both", "direction": "mixed"}, None)
    texts = " ".join(h["text"] for h in hints)
    assert "сыграй через центр" not in texts and "переведи атаки на правый фланг" in texts
    assert sum("В центре" in h["text"] for h in hints) == 1                       # one summary hint
    assert hints[-1]["actions"] == [{"kind": "direction", "value": "wings", "label": "Играть по флангам"}]
    # Both flanks hard, the centre fine: one tap to the centre.
    hints = career_service._duel_hints([d("left", -4, "hard"), d("right", -4, "hard")], [], [d("centre", 0, "even")],
                                       {"flank": "both", "direction": "wings"}, None)
    assert hints[0]["actions"][0] == {"kind": "direction", "value": "center", "label": "Играть через центр"}
    assert "переведи" not in hints[0]["text"]
