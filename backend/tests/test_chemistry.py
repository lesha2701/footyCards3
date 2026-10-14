"""«Химия карточек» — neighbour-link chemistry (services/chemistry_service.py)
and how it plugs into Card Arena lineups, player-tournament squads and the
FUT Draft hints. Everything here is deterministic (no random draws are
asserted on, and the two places that jitter are monkeypatched)."""

import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.card import UserCard
from app.models.coach import Coach
from app.models.enums import CardSource, Position, Rarity
from app.models.game_config import GameConfig
from app.models.player_tournament import PlayerTournament
from app.services import chemistry_service, match_service
from app.services.card_creation import create_user_card
from app.services.chemistry_service import (
    LINK_MEDIUM, LINK_NONE, LINK_STRONG, ChemistryResult, ChemistryRules, compute_chemistry, link_level,
    player_points, rules_from_config, rules_from_dict,
)
from app.services.club_formation_service import CLUB_FORMATIONS, get_formation_slots
from app.services.coach_boost_service import arena_rarity_team_strength_bonus
from app.services.lineup_service import (
    CATEGORY_POSITIONS, FORMATION_SLOTS, calculate_base_strength, legacy_chemistry_bonus,
)
from app.services.player_stats_service import effective_card_stats
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

CASES_PATH = Path(__file__).resolve().parents[2] / "frontend" / "src" / "test" / "chemistryCases.json"


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


def _pl(club="C", country="X", position=Position.ST, rating=80, rarity=Rarity.common):
    return NS(club=club, country=country, position=position, rating=rating, rarity=rarity,
              attack_rating=None, defense_rating=None)


def _squad(formation="4-3-3", club=lambda s: f"club-{s.code}", country=lambda s: f"cty-{s.code}", rating=80):
    """One on-position card per slot; club/country per slot via callables."""
    return [(NS(player=_pl(club(s), country(s), s.ideal_position, rating)), s) for s in get_formation_slots(formation)]


async def _config(db_session) -> GameConfig:
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
        await db_session.commit()
        config = await db_session.get(GameConfig, 1)
    return config


# --- pure rules -------------------------------------------------------------------------------


def test_link_levels():
    assert link_level(_pl("Real", "Spain"), _pl("Real", "Spain")) == LINK_STRONG
    assert link_level(_pl("Real", "Spain"), _pl("Real", "France")) == LINK_MEDIUM
    assert link_level(_pl("Real", "Spain"), _pl("Barca", "Spain")) == LINK_MEDIUM
    assert link_level(_pl("Real", "Spain"), _pl("Barca", "France")) == LINK_NONE
    # Whitespace variants are one group; blank values never link.
    assert link_level(_pl(" Real ", "Spain"), _pl("Real", "Spain ")) == LINK_STRONG
    assert link_level(_pl("", ""), _pl("", "")) == LINK_NONE


def test_every_formation_has_a_connected_adjacency_over_its_own_slots():
    for formation, slots in CLUB_FORMATIONS.items():
        codes = {s.code for s in slots}
        edges = chemistry_service.FORMATION_LINKS[formation]
        assert {c for e in edges for c in e} == codes, formation
        assert len(set(edges)) == len(edges)
        seen, stack = set(), ["GK"]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack += [b if a == node else a for a, b in edges if node in (a, b)]
        assert seen == codes, formation


def test_player_points_thresholds_floor_max_and_position():
    rules = ChemistryRules(thresholds=(1, 2, 4), player_floor=0, player_max=3)
    assert [player_points(s, True, rules) for s in range(6)] == [0, 1, 2, 2, 3, 3]
    assert player_points(10, False, rules) == 0
    floored = ChemistryRules(thresholds=(1, 2, 4), player_floor=1, player_max=3)
    assert player_points(0, True, floored) == 1
    assert player_points(0, False, floored) == 0  # the floor never covers an off-position player
    capped = ChemistryRules(thresholds=(1, 2, 4), player_floor=3, player_max=2)
    assert player_points(0, True, capped) == 2  # floor clamped to the maximum
    assert player_points(9, True, capped) == 2


def test_team_chemistry_is_the_sum_and_bonus_follows_rules():
    rules = ChemistryRules(rating_per_point=2, off_position_penalty=3)
    pairs = _squad(club=lambda s: "Same", country=lambda s: "Same")
    result = compute_chemistry(pairs, "4-3-3", rules)
    assert result.team == 33 and result.team_max == 33
    assert all(p.rating_bonus == 6 for p in result.players.values())
    assert sum(p.points for p in result.players.values()) == result.team
    # Off-position (CB in the LB slot): 0 chemistry, penalty instead of a bonus,
    # but his links still count for his neighbours.
    lb_slot = next(s for s in FORMATION_SLOTS if s.code == "DEF1")
    pairs = [(NS(player=_pl("Same", "Same", Position.CB)), s) if s.code == "DEF1" else (c, s) for c, s in pairs]
    result = compute_chemistry(pairs, "4-3-3", rules)
    assert result.players[lb_slot.code].points == 0
    assert result.players[lb_slot.code].rating_bonus == -3
    assert result.players["DEF2"].points == 3
    assert result.team == 30


def test_empty_slots_have_no_links_and_team_max_uses_formation_size():
    pairs = [p for p in _squad(club=lambda s: "Same") if p[1].code in ("GK", "DEF2")]
    result = compute_chemistry(pairs, "4-3-3", ChemistryRules(), slot_count=11)
    assert [(l.a, l.b, l.level) for l in result.links] == [("GK", "DEF2", LINK_MEDIUM)]
    assert result.team_max == 33


def test_rules_round_trip_through_config_and_dict():
    config = GameConfig(
        chemistry_link_strong=3, chemistry_link_medium=1, chemistry_threshold_1=5, chemistry_threshold_2=1,
        chemistry_threshold_3=3, chemistry_player_max=3, chemistry_player_floor=1, chemistry_rating_per_point=2,
        chemistry_off_position_penalty=1, chemistry_coach_country_points=2, chemistry_stadium_club_points=0,
    )
    rules = rules_from_config(config)
    assert rules.thresholds == (1, 3, 5)
    assert rules_from_dict(rules.as_dict()) == rules
    assert rules_from_dict(None) is None


def test_shared_fixture_matches_python_implementation():
    """frontend/src/test/chemistryCases.json is also asserted by
    src/test/chemistry.test.ts — both implementations must produce these exact
    numbers, which is what keeps the instant client-side recalculation equal
    to the server's."""
    if not CASES_PATH.exists():
        pytest.skip("frontend checkout not available")
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    assert len(cases) >= 4
    for case in cases:
        slots = {s.code: s for s in get_formation_slots(case["formation"])}
        pairs = [
            (NS(player=_pl(p["club"], p["country"], Position(p["position"]))), slots[p["slot"]])
            for p in case["players"]
        ]
        assert [tuple(e) for e in case["adjacency"]] == list(chemistry_service.FORMATION_LINKS[case["formation"]])
        rules = rules_from_dict(case["rules"])
        result = compute_chemistry(
            pairs, case["formation"], rules, slot_count=case["slot_count"],
            coach_country=case.get("coach_country"), stadium_club=case.get("stadium_club"),
        )
        expected = case["expected"]
        assert result.team == expected["team"], case["name"]
        assert result.team_max == expected["team_max"], case["name"]
        assert [{"a": l.a, "b": l.b, "level": l.level, "points": l.points} for l in result.links] == expected["links"]
        assert {
            code: {"points": p.points, "link_sum": p.link_sum, "on_position": p.on_position, "rating_bonus": p.rating_bonus,
                   "coach_bonus": p.coach_bonus, "stadium_bonus": p.stadium_bonus}
            for code, p in result.players.items()
        } == expected["players"], case["name"]


# --- strength integration ---------------------------------------------------------------------


def _legacy_reference_strength(pairs, coach=None, tactic=None, stadium_multiplier=1.0):
    """Independent re-statement of the pre-chemistry formula."""
    from collections import Counter

    from app.models.enums import RARITY_ORDER
    from app.services.lineup_service import TACTIC_CATEGORY_MULTIPLIERS

    mults = TACTIC_CATEGORY_MULTIPLIERS.get(tactic, {}) if tactic else {}
    total = 0.0
    for card, slot in pairs:
        p = card.player
        fit = 1.0 if p.position == slot.ideal_position else (0.9 if p.position in CATEGORY_POSITIONS[slot.category] else 0.75)
        total += p.rating * fit * (1 + 0.03 * RARITY_ORDER[p.rarity]) * mults.get(slot.category, 1.0)
    clubs = Counter(" ".join(c.player.club.split()) for c, _ in pairs)
    countries = Counter(" ".join(c.player.country.split()) for c, _ in pairs)
    total += (clubs.most_common(1)[0][1] - 1) * 2 + (countries.most_common(1)[0][1] - 1)
    total += arena_rarity_team_strength_bonus(coach)
    return round(total * stadium_multiplier)


@pytest.mark.parametrize("tactic", [None, "attacking", "balanced", "defensive"])
def test_flag_off_strength_is_byte_for_byte_the_old_formula(tactic):
    coach = Coach(display_name="T", rarity=Rarity.legendary)
    coach.boosts = []
    pairs = _squad(club=lambda s: "A" if s.category in ("DEF", "GK") else f"c{s.code}",
                   country=lambda s: "N" if s.category == "MID" else f"n{s.code}", rating=83)
    pairs[3] = (NS(player=_pl("A", "Z", Position.LB, 77)), pairs[3][1])  # off-position CB slot
    for stadium in (1.0, 1.07):
        assert calculate_base_strength(pairs, coach=coach, tactic=tactic, stadium_multiplier=stadium) == \
            _legacy_reference_strength(pairs, coach=coach, tactic=tactic, stadium_multiplier=stadium)


def test_chemistry_strength_replaces_flat_bonus_and_respects_coach_and_stadium_order():
    from app.models.enums import RARITY_ORDER

    coach = Coach(display_name="T", rarity=Rarity.epic)
    coach.boosts = []
    pairs = _squad(club=lambda s: "A", country=lambda s: "N", rating=98)
    chemistry = compute_chemistry(pairs, "4-3-3", ChemistryRules(rating_per_point=1))
    got = calculate_base_strength(pairs, coach=coach, tactic="balanced", stadium_multiplier=1.05, chemistry=chemistry)
    # rating + chemistry (capped at 99) -> fit/rarity/tactic -> + coach -> × stadium; no flat bonus.
    per_card = sum(min(99, 98 + 3) * 1.0 * (1 + 0.03 * RARITY_ORDER[Rarity.common]) * 1.02 for _ in pairs)
    assert got == round((per_card + arena_rarity_team_strength_bonus(coach)) * 1.05)
    # An empty result = neither the per-card bonus nor the old flat bonus.
    zero = calculate_base_strength(pairs, coach=coach, tactic="balanced", stadium_multiplier=1.05,
                                   chemistry=ChemistryResult(formation="4-3-3"))
    flat = calculate_base_strength(pairs, coach=coach, tactic="balanced", stadium_multiplier=1.05)
    assert legacy_chemistry_bonus(pairs) == 30 and flat > zero


def test_diamond_bonus_then_chemistry_never_exceeds_99():
    player = _pl(rating=97)
    card = NS(player=player, diamond_rating_bonus=5)
    rating, _, _ = effective_card_stats(player, card.diamond_rating_bonus)
    assert chemistry_service.boosted_rating(rating, 3) == 99
    assert chemistry_service.boosted_rating(2, -5) == 1
    assert chemistry_service.boosted_rating(80, 0) == 80


# --- Card Arena API ---------------------------------------------------------------------------


async def _arena_user(client, db_session, bot_token, telegram_id, *, same_club=True):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, telegram_id)
    slots = []
    for slot in FORMATION_SLOTS:
        player = await create_player(
            db_session, rating=80, position=slot.ideal_position,
            **({"club": "Реал", "country": "Испания"} if same_club else {}),
        )
        card = await create_user_card(db_session, user.id, player.id, CardSource.seed)
        await db_session.commit()
        slots.append({"slot_code": slot.code, "user_card_id": card.id})
    resp = await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})
    assert resp.status_code == 200
    return headers, user, slots, resp.json()


async def test_arena_lineup_flag_off_keeps_old_strength_and_reports_flat_bonus(client, db_session, bot_token):
    headers, _user, _slots, body = await _arena_user(client, db_session, bot_token, 880001)
    assert body["chemistry"]["enabled"] is False
    assert body["chemistry"]["strength_bonus"] == 10 * 2 + 10 * 1
    assert body["chemistry"]["links"] == []


async def test_arena_lineup_flag_on_exposes_links_points_and_bonus(client, db_session, bot_token):
    config = await _config(db_session)
    headers, user, slots, off_body = await _arena_user(client, db_session, bot_token, 880002)
    config.chemistry_enabled = True
    await db_session.commit()

    body = (await client.get("/api/v1/lineups/active", headers=headers)).json()
    chem = body["chemistry"]
    assert chem["enabled"] is True and chem["formation"] == "4-3-3"
    assert chem["team"] == 33 and chem["team_max"] == 33
    assert {l["level"] for l in chem["links"]} == {"strong"}
    assert len(chem["links"]) == len(chemistry_service.FORMATION_LINKS["4-3-3"])
    assert all(p["points"] == 3 and p["rating_bonus"] == 3 for p in chem["players"])
    assert chem["rules"]["thresholds"] == [1, 2, 4]
    assert chem["strength_bonus"] == body["team_strength"] - (off_body["team_strength"] - 30)
    # Displayed card ratings never change.
    assert {s["card"]["player"]["rating"] for s in body["slots"]} == {80}


async def test_chemistry_preview_for_hypothetical_arrangement(client, db_session, bot_token):
    config = await _config(db_session)
    headers, user, slots, _ = await _arena_user(client, db_session, bot_token, 880003)
    other = await create_player(db_session, rating=90, position=Position.ST, club="Бавария", country="Германия")
    card = await create_user_card(db_session, user.id, other.id, CardSource.seed)
    await db_session.commit()
    swapped = [s if s["slot_code"] != "FWD2" else {"slot_code": "FWD2", "user_card_id": card.id} for s in slots]

    resp = await client.post("/api/v1/lineups/chemistry/preview", headers=headers, json={"formation": "4-3-3", "slots": swapped})
    assert resp.status_code == 200 and resp.json()["enabled"] is False  # flag off: nothing computed

    config.chemistry_enabled = True
    await db_session.commit()
    resp = await client.post("/api/v1/lineups/chemistry/preview", headers=headers, json={"formation": "4-3-3", "slots": swapped})
    preview = resp.json()
    by_slot = {p["slot_code"]: p for p in preview["players"]}
    assert by_slot["FWD2"]["link_sum"] == 0 and by_slot["FWD2"]["points"] == config.chemistry_player_floor
    assert preview["team"] < 33
    # Nothing was saved.
    saved = (await client.get("/api/v1/lineups/active", headers=headers)).json()
    assert saved["chemistry"]["team"] == 33

    # Someone else's card cannot be previewed.
    other_headers = telegram_headers(880004, bot_token)
    await client.post("/api/v1/auth/session", headers=other_headers)
    resp = await client.post("/api/v1/lineups/chemistry/preview", headers=other_headers, json={"formation": "4-3-3", "slots": swapped})
    assert resp.status_code == 404


async def test_started_arena_match_keeps_strength_and_ratings_frozen(client, db_session, bot_token, monkeypatch):
    config = await _config(db_session)
    config.chemistry_enabled = True
    await db_session.commit()
    headers, *_ = await _arena_user(client, db_session, bot_token, 880005)
    monkeypatch.setattr(match_service, "_with_jitter", lambda strength: strength)

    lineup = (await client.get("/api/v1/lineups/active", headers=headers)).json()
    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 200
    match_id = resp.json()["id"]
    from app.models.match import Match

    match = await db_session.get(Match, match_id)
    await db_session.refresh(match)
    assert match.user_team_strength == lineup["team_strength"]
    assert match.server_state["ratings"]["user_fwd"] == 83  # 80 + 3 chemistry
    assert match.server_state["chemistry"]["user"] == 33
    frozen = (match.user_team_strength, dict(match.server_state["ratings"]))

    # Turning the mechanic off (or retuning it) does not touch the started match.
    config.chemistry_enabled = False
    await db_session.commit()
    await db_session.refresh(match)
    assert (match.user_team_strength, match.server_state["ratings"]) == frozen
    new_lineup = (await client.get("/api/v1/lineups/active", headers=headers)).json()
    assert new_lineup["team_strength"] != lineup["team_strength"]


async def test_arena_category_avg_unchanged_when_flag_off(client, db_session, bot_token):
    _headers, user, _slots, _ = await _arena_user(client, db_session, bot_token, 880006)
    from app.services.lineup_service import get_active_lineup

    lineup = await get_active_lineup(db_session, user)
    assert match_service._category_avg(lineup, "FWD") == 80


# --- player tournaments -----------------------------------------------------------------------


async def test_tournament_freezes_rules_at_start(client, db_session, bot_token):
    from app.services.player_tournament_fixture_service import TOURNAMENT_SIZE
    from app.services.player_tournament_queue_service import apply_to_tournament
    from tests.player_tournament_helpers import make_ready_user

    config = await _config(db_session)
    config.chemistry_enabled = True
    config.chemistry_rating_per_point = 2
    await db_session.commit()
    for i in range(TOURNAMENT_SIZE):
        user = await make_ready_user(client, db_session, bot_token, 881000 + i)
        await apply_to_tournament(db_session, user)
    tournament = (await db_session.execute(select(PlayerTournament))).scalars().one()
    assert tournament.chemistry_rules["rating_per_point"] == 2
    assert rules_from_dict(tournament.chemistry_rules) == rules_from_config(config)


async def test_tournament_match_applies_frozen_chemistry_to_engine_ratings(client, db_session, bot_token):
    from app.services import player_tournament_simulation_service as sim
    from tests.player_tournament_helpers import make_ready_user

    user_a = await make_ready_user(client, db_session, bot_token, 882001, rating=70)
    user_b = await make_ready_user(client, db_session, bot_token, 882002, rating=70)
    config = await _config(db_session)

    plain = await sim._build_side(db_session, user_a.id, is_home=True, config=config)
    rules = ChemistryRules(rating_per_point=2)
    boosted = await sim._build_side(db_session, user_a.id, is_home=True, config=config, chemistry_rules=rules)
    # Factory players share one country -> every link is medium; on-position
    # players reach thresholds by their link sum (=degree).
    assert plain.chemistry is None
    assert boosted.chemistry["max"] == 33
    for p_plain, p_boost in zip(plain.lineup, boosted.lineup):
        pts = boosted.chemistry["cards"][str(p_plain["club_card_id"])]
        assert p_boost["rating"] == p_plain["rating"] + 2 * pts
    assert boosted.side.profile.central_attack > plain.side.profile.central_attack

    _sa, _sb, _ev, snapshot_off = await sim._play_match(db_session, user_a.id, user_b.id, {user_a.id: "A", user_b.id: "B"}, config)
    assert snapshot_off is None  # nothing frozen = old behaviour, no snapshot
    _sa, _sb, _ev, snapshot = await sim._play_match(
        db_session, user_a.id, user_b.id, {user_a.id: "A", user_b.id: "B"}, config, chemistry_rules=rules,
    )
    assert snapshot["chemistry"]["a"]["team"] == boosted.chemistry["team"]
    assert snapshot["chemistry"]["b"]["max"] == 33


async def test_chemistry_leaves_card_skill_effects_untouched(client, db_session, bot_token):
    from app.services.player_tournament_simulation_service import _engine_card

    config = await _config(db_session)
    player = await create_player(db_session, rating=80, position=Position.ST)
    card = NS(id=1, player_id=player.id, player=player, diamond_rating_bonus=0, skill_code="sniper", skill_level=2)
    plain, boosted = _engine_card(card, config), _engine_card(card, config, chemistry_bonus=3)
    assert plain.skill == boosted.skill and plain.skill is not None
    assert boosted.player.rating == plain.player.rating + 3


async def test_personal_squad_response_carries_chemistry_when_enabled(client, db_session, bot_token):
    from tests.player_tournament_helpers import make_ready_user

    user = await make_ready_user(client, db_session, bot_token, 883001)
    headers = telegram_headers(883001, bot_token)
    squads = (await client.get("/api/v1/player-tournaments/squads", headers=headers)).json()
    assert squads[0]["chemistry"]["enabled"] is False
    config = await _config(db_session)
    config.chemistry_enabled = True
    await db_session.commit()
    squads = (await client.get("/api/v1/player-tournaments/squads", headers=headers)).json()
    active = next(s for s in squads if s["is_active"])
    assert active["chemistry"]["enabled"] is True
    assert active["chemistry"]["team_max"] == 33
    assert active["chemistry"]["team"] > 0
    assert all(l["level"] == "medium" for l in active["chemistry"]["links"])


# --- FUT Draft ---------------------------------------------------------------------------------


async def test_fut_draft_hints_add_up_to_the_actual_chemistry_contribution(db_session):
    from app.services import fut_draft_service

    config = await _config(db_session)
    config.chemistry_enabled = True  # FUT Draft keeps its own formula regardless
    await db_session.commit()
    slots = get_formation_slots("4-4-2")
    players = {}
    picks = {}
    clubs = ["ПСЖ", "ПСЖ", "ПСЖ", "Бавария", "Бавария", "Милан", "Интер", "Ювентус"]
    countries = ["Франция", "Франция", "Германия", "Германия", "Германия", "Италия", "Италия", "Бразилия"]
    for slot, club, country in zip(slots, clubs, countries):
        p = await create_player(db_session, position=slot.ideal_position, club=club, country=country, rating=75)
        players[p.id] = p
        picks[slot.code] = p.id
    club_counts, country_counts = {}, {}
    for p in players.values():
        club_counts[p.club] = club_counts.get(p.club, 0) + 1
        country_counts[p.country] = country_counts.get(p.country, 0) + 1
    state = {"picks": picks, "club_counts": club_counts, "country_counts": country_counts}

    strength = await fut_draft_service._compute_team_strength(db_session, picks, slots, config, club_counts, country_counts)
    by_code = {s.code: s for s in slots}
    pairs = [(NS(player=players[pid]), by_code[code]) for code, pid in picks.items()]
    without_chemistry = calculate_base_strength(pairs, chemistry=ChemistryResult(formation="4-4-2"))
    hints = fut_draft_service._chemistry_hints(config, state, players, by_code)
    shown = sum(int(h.split("+")[1].split(" ")[0]) for h in hints if "к силе" in h)
    assert shown == strength - without_chemistry
    assert any(h.startswith("Сыгранность") for h in hints)
