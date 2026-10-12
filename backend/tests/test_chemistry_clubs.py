"""«Химия карточек», этап 2: club squads and club tournaments (rules frozen per
Tournament like player tournaments), the frozen-rules flag every squad
editor gets, and chemistry-aware «Собрать лучший состав»."""

from types import SimpleNamespace as NS

import pytest
import pytest_asyncio
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.club import Club
from app.models.enums import CardSource, Position, Rarity
from app.models.game_config import GameConfig
from app.models.player_tournament import PlayerTournament
from app.models.tournament import Tournament
from app.services import chemistry_service
from app.services import tournament_simulation_service as sim
from app.services.auto_squad_service import SlotSpec, improve_for_chemistry, pick_cards
from app.services.card_creation import create_user_card
from app.services.chemistry_service import ChemistryRules, compute_chemistry, rules_from_config, with_match_ratings
from app.services.club_formation_service import get_formation_slots
from app.services.lineup_service import FORMATION_SLOTS, calculate_base_strength
from app.services.tournament_queue_service import apply_to_tournament
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1"


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """Starter squads draw from active players per category (same seeding as
    test_tournament_simulation_service.py). Factory players all share one
    country and have unique clubs, so every club-squad link is «medium»."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _config(db_session) -> GameConfig:
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
        await db_session.commit()
        config = await db_session.get(GameConfig, 1)
    return config


async def _club(client, db_session, bot_token, telegram_id, name):
    """Captain + a second member (apply_to_tournament needs >= 2)."""
    headers = telegram_headers(telegram_id, bot_token)
    assert (await client.post(f"{API}/auth/session", headers=headers)).status_code == 200
    captain = await get_user_by_telegram_id(db_session, telegram_id)
    resp = await client.post(
        f"{API}/clubs", headers=headers,
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 200
    club = await db_session.get(Club, resp.json()["id"])
    second = telegram_headers(telegram_id + 900_000, bot_token)
    assert (await client.post(f"{API}/auth/session", headers=second)).status_code == 200
    assert (await client.post(f"{API}/clubs/{club.id}/join", headers=second)).status_code == 200
    return club, captain, headers


async def _eight_clubs(client, db_session, bot_token, base):
    clubs, tournament_id = [], None
    for i in range(8):
        club, captain, headers = await _club(client, db_session, bot_token, base + i, f"Химия клуб {base + i}")
        result = await apply_to_tournament(db_session, captain)
        clubs.append((club, captain, headers))
        tournament_id = result.tournament_id or tournament_id
    assert tournament_id is not None
    return await db_session.get(Tournament, tournament_id), clubs


# --- pure helpers -----------------------------------------------------------------------------


def _card(cid, position, rating=80, club="C", country="X", rarity=Rarity.common, player_id=None):
    return NS(
        id=cid, player_id=player_id or cid, diamond_rating_bonus=0, is_locked_by_admin=False, is_locked_in_trade=False,
        skill_code=None, skill_level=None,
        player=NS(display_name=f"P{cid}", position=position, rating=rating, rarity=rarity, club=club, country=country,
                  attack_rating=None, defense_rating=None),
    )


def test_with_match_ratings_passes_through_unchanged_cards():
    pairs = [(_card(i, s.ideal_position, club="Real", country="Spain"), s) for i, s in enumerate(FORMATION_SLOTS, 1)]
    assert with_match_ratings(pairs, None) == pairs

    chemistry = compute_chemistry(pairs, "4-3-3", ChemistryRules(rating_per_point=2))
    boosted = with_match_ratings(pairs, chemistry)
    for (orig, slot), (card, slot_b) in zip(pairs, boosted):
        assert slot is slot_b and card.id == orig.id and card.player_id == orig.player_id
        assert card.player.rating == orig.player.rating + chemistry.rating_bonus(slot.code)
        assert orig.player.rating == 80  # the real card is never mutated

    # A zero-bonus card is the very same object (no stand-in).
    lonely = [(_card(1, Position.GK, club="A", country="B"), FORMATION_SLOTS[0])]
    assert with_match_ratings(lonely, compute_chemistry(lonely, "4-3-3", ChemistryRules()))[0][0] is lonely[0][0]


def _arena_slots():
    return [SlotSpec(s.code, s.category, s.ideal_position) for s in FORMATION_SLOTS]


def _linked_team_and_lone_star():
    """Ten Real/Spain players at 80 on their positions, two STs: a lone 85
    (no club/country in common with anyone) and a Real/Spain 82."""
    cards = [_card(i, s.ideal_position, 80, "Real", "Spain") for i, s in enumerate(FORMATION_SLOTS, 1) if s.code != "FWD2"]
    star = _card(100, Position.ST, 85, "Бавария", "Германия")
    linked = _card(101, Position.ST, 82, "Real", "Spain")
    return cards + [star, linked], star, linked


def test_improve_for_chemistry_trades_raw_rating_for_links():
    cards, star, linked = _linked_team_and_lone_star()
    slots = _arena_slots()
    greedy = pick_cards(slots, cards, "arena")
    assert greedy["FWD2"] is star  # greedy = highest rating

    rules = ChemistryRules()
    improved = improve_for_chemistry(greedy, slots, cards, "4-3-3", rules)
    assert improved["FWD2"] is linked
    by_code = {s.code: s for s in FORMATION_SLOTS}

    def strength(chosen):
        pairs = [(c, by_code[code]) for code, c in chosen.items()]
        return calculate_base_strength(pairs, chemistry=compute_chemistry(pairs, "4-3-3", rules))

    assert strength(improved) > strength(greedy)
    # Same hard rules as the greedy pick: one copy per player, no duplicates.
    assert len({c.player_id for c in improved.values()}) == len(improved)


def test_improve_for_chemistry_keeps_fixed_cards_and_diamond_limit():
    cards, star, _linked = _linked_team_and_lone_star()
    slots = _arena_slots()
    greedy = pick_cards(slots, cards, "arena")
    assert improve_for_chemistry(greedy, slots, cards, "4-3-3", ChemistryRules(), fixed_ids=frozenset({star.id}))["FWD2"] is star

    # A linked diamond would beat everything but the limit (1) is already used.
    cards2, _star, _ = _linked_team_and_lone_star()
    gk_diamond = _card(200, Position.GK, 90, "Ajax", "NL", rarity=Rarity.diamond)
    linked_diamond = _card(201, Position.ST, 90, "Real", "Spain", rarity=Rarity.diamond)
    pool = cards2 + [gk_diamond, linked_diamond]
    greedy = pick_cards(slots, pool, "arena", max_diamonds=1)
    improved = improve_for_chemistry(greedy, slots, pool, "4-3-3", ChemistryRules(), max_diamonds=1)
    assert sum(1 for c in improved.values() if c.player.rarity == Rarity.diamond) <= 1


# --- club squads ------------------------------------------------------------------------------


async def test_club_lineup_chemistry_off_keeps_old_strength(client, db_session, bot_token):
    club, _captain, headers = await _club(client, db_session, bot_token, 885001, "Химия-офф")
    body = (await client.get(f"{API}/clubs/me/lineup", headers=headers)).json()
    assert body["chemistry"]["enabled"] is False and body["chemistry"]["frozen"] is False
    _lineup, _sub, pairs, _club_lineup = await sim.resolve_match_lineup(db_session, club.id)
    assert body["team_strength"] == round(calculate_base_strength(pairs))
    assert body["chemistry"]["strength_bonus"] == body["team_strength"] - round(
        calculate_base_strength(pairs, chemistry=chemistry_service.ChemistryResult(formation="4-3-3"))
    )


async def test_club_lineup_chemistry_on_uses_live_rules_outside_tournament(client, db_session, bot_token):
    config = await _config(db_session)
    _club_row, _captain, headers = await _club(client, db_session, bot_token, 885002, "Химия-он")
    off = (await client.get(f"{API}/clubs/me/lineup", headers=headers)).json()
    config.chemistry_enabled = True
    await db_session.commit()

    body = (await client.get(f"{API}/clubs/me/lineup", headers=headers)).json()
    chem = body["chemistry"]
    assert chem["enabled"] is True and chem["frozen"] is False and chem["live_enabled"] is True
    assert chem["team_max"] == 33 and chem["team"] > 0
    assert {l["level"] for l in chem["links"]} == {"medium"}  # shared country, unique clubs
    assert body["team_strength"] != off["team_strength"]
    # Line stats stay the plain card ratings shown on the pitch.
    assert (body["attack"], body["midfield"], body["defence"]) == (off["attack"], off["midfield"], off["defence"])


async def test_club_tournament_freezes_rules_and_editor_says_so(client, db_session, bot_token):
    config = await _config(db_session)
    config.chemistry_enabled = True
    config.chemistry_rating_per_point = 2
    await db_session.commit()
    tournament, clubs = await _eight_clubs(client, db_session, bot_token, 886000)
    assert tournament.chemistry_rules == rules_from_config(config).as_dict()

    # Retuning GameConfig mid-tournament changes nothing for this tournament.
    config.chemistry_rating_per_point = 5
    await db_session.commit()
    headers = clubs[0][2]
    chem = (await client.get(f"{API}/clubs/me/lineup", headers=headers)).json()["chemistry"]
    assert chem["frozen"] is True and chem["enabled"] is True
    assert chem["rules"]["rating_per_point"] == 2

    # A tournament that started with the mechanic off stays off.
    tournament.chemistry_rules = None
    await db_session.commit()
    chem = (await client.get(f"{API}/clubs/me/lineup", headers=headers)).json()["chemistry"]
    assert chem == {**chem, "enabled": False, "frozen": True, "live_enabled": True}


async def test_apply_chemistry_boosts_fielded_club_cards(client, db_session, bot_token):
    club, _captain, _headers = await _club(client, db_session, bot_token, 887001, "Химия движок")
    lineup, _sub, pairs, club_lineup = await sim.resolve_match_lineup(db_session, club.id)
    assert sim.apply_chemistry(lineup, pairs, club_lineup, None) == (lineup, pairs)

    rules = ChemistryRules(rating_per_point=2)
    boosted_lineup, boosted_pairs = sim.apply_chemistry(lineup, pairs, club_lineup, rules)
    chemistry = compute_chemistry(pairs, club_lineup.formation, rules, slot_count=11)
    for actor, plain, (_card_row, slot) in zip(boosted_lineup, lineup, pairs):
        assert actor["club_card_id"] == plain["club_card_id"]
        assert actor["rating"] == min(99, plain["rating"] + 2 * chemistry.players[slot.code].points)
    assert [c.id for c, _ in boosted_pairs] == [c.id for c, _ in pairs]


async def test_club_round_plays_with_the_tournaments_frozen_rules(client, db_session, bot_token, monkeypatch):
    tournament, clubs = await _eight_clubs(client, db_session, bot_token, 888000)
    assert tournament.chemistry_rules is None  # flag was off at the start

    captured: list[list[int]] = []
    real_build_side = sim.build_side

    def spy(cards_with_slots, *args, **kwargs):
        captured.append([card.player.rating for card, _slot in cards_with_slots])
        return real_build_side(cards_with_slots, *args, **kwargs)

    monkeypatch.setattr(sim, "build_side", spy)
    # Live GameConfig turned on mid-tournament must NOT leak into its rounds.
    config = await _config(db_session)
    config.chemistry_enabled = True
    await db_session.commit()
    await sim.simulate_next_round(db_session)
    await db_session.commit()
    plain = [list(r) for r in captured]
    assert plain and all(r == 70 for side in plain for r in side)

    captured.clear()
    tournament = (await db_session.execute(select(Tournament))).scalars().one()
    tournament.chemistry_rules = ChemistryRules(rating_per_point=3).as_dict()
    await db_session.commit()
    await sim.simulate_next_round(db_session)
    await db_session.commit()
    assert captured and any(r > 70 for side in captured for r in side)


# --- player tournaments: frozen rules in the squad editor ------------------------------------


async def test_personal_squad_reports_frozen_tournament_rules(client, db_session, bot_token):
    from app.services.player_tournament_fixture_service import TOURNAMENT_SIZE
    from app.services.player_tournament_queue_service import apply_to_tournament as apply_player
    from tests.player_tournament_helpers import make_ready_user

    config = await _config(db_session)
    config.chemistry_enabled = True
    config.chemistry_rating_per_point = 2
    await db_session.commit()
    for i in range(TOURNAMENT_SIZE):
        user = await make_ready_user(client, db_session, bot_token, 889000 + i)
        await apply_player(db_session, user)
    assert (await db_session.execute(select(PlayerTournament))).scalars().one().chemistry_rules is not None

    config.chemistry_rating_per_point = 4
    await db_session.commit()
    squads = (await client.get(f"{API}/player-tournaments/squads", headers=telegram_headers(889000, bot_token))).json()
    chem = next(s for s in squads if s["is_active"])["chemistry"]
    assert chem["frozen"] is True and chem["rules"]["rating_per_point"] == 2

    # Not in a tournament: live rules, not frozen.
    await make_ready_user(client, db_session, bot_token, 889100)
    squads = (await client.get(f"{API}/player-tournaments/squads", headers=telegram_headers(889100, bot_token))).json()
    chem = next(s for s in squads if s["is_active"])["chemistry"]
    assert chem["frozen"] is False and chem["rules"]["rating_per_point"] == 4


# --- «Собрать лучший состав» -----------------------------------------------------------------


async def _arena_collection(client, db_session, bot_token, telegram_id):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post(f"{API}/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, telegram_id)
    for slot in FORMATION_SLOTS:
        if slot.code == "FWD2":
            continue
        player = await create_player(db_session, rating=80, position=slot.ideal_position, club="Реал", country="Испания")
        await create_user_card(db_session, user.id, player.id, CardSource.seed)
    star = await create_player(db_session, rating=85, position=Position.ST, club="Бавария", country="Германия")
    linked = await create_player(db_session, rating=82, position=Position.ST, club="Реал", country="Испания")
    star_card = await create_user_card(db_session, user.id, star.id, CardSource.seed)
    linked_card = await create_user_card(db_session, user.id, linked.id, CardSource.seed)
    await db_session.commit()
    return headers, star_card.id, linked_card.id


async def test_auto_arena_lineup_flag_off_keeps_greedy_pick(client, db_session, bot_token):
    headers, star_id, _linked_id = await _arena_collection(client, db_session, bot_token, 890001)
    body = (await client.post(f"{API}/lineups/templates/1/auto", headers=headers)).json()
    assert next(s for s in body["slots"] if s["slot_code"] == "FWD2")["card"]["id"] == star_id


async def test_auto_arena_lineup_flag_on_picks_for_chemistry(client, db_session, bot_token):
    config = await _config(db_session)
    config.chemistry_enabled = True
    await db_session.commit()
    headers, _star_id, linked_id = await _arena_collection(client, db_session, bot_token, 890002)
    body = (await client.post(f"{API}/lineups/templates/1/auto", headers=headers)).json()
    assert next(s for s in body["slots"] if s["slot_code"] == "FWD2")["card"]["id"] == linked_id
    assert body["chemistry"]["team"] == body["chemistry"]["team_max"] == 33


# --- «тренер-земляк» / «домашний стадион» -----------------------------------------------------


def test_coach_and_stadium_extras_on_position_only_and_capped():
    pairs = [
        (_card(1, Position.GK, club="Real", country="Spain"), FORMATION_SLOTS[0]),
        (_card(2, Position.ST, club="Real", country="Spain"), FORMATION_SLOTS[2]),  # off position at DEF2
        (_card(3, Position.CB, club="Milan", country="Italy"), FORMATION_SLOTS[3]),
    ]
    rules = ChemistryRules(coach_country_points=1, stadium_club_points=2)
    plain = compute_chemistry(pairs, "4-3-3", rules)
    extra = compute_chemistry(pairs, "4-3-3", rules, coach_country=" Spain ", stadium_club="Real")
    gk_plain, gk = plain.players["GK"], extra.players["GK"]
    assert (gk.coach_bonus, gk.stadium_bonus) == (1, 2)
    assert gk.points == min(3, gk_plain.points + 3)
    assert extra.players["DEF2"].points == 0 and extra.players["DEF2"].coach_bonus == 0  # off position
    assert extra.players["DEF3"] == plain.players["DEF3"]  # Milan/Italy: nothing
    assert extra.coach_country == "Spain"

    # Rules frozen before the extras existed carry none of them.
    old = {k: v for k, v in rules.as_dict().items() if k not in ("coach_country_points", "stadium_club_points")}
    frozen = chemistry_service.rules_from_dict(old)
    assert (frozen.coach_country_points, frozen.stadium_club_points) == (0, 0)


async def _equip_personal_coach_and_stadium(db_session, user, *, country, club):
    from app.models.coach import Coach, CoachBoost
    from app.models.enums import CoachBoostType
    from app.models.stadium import Stadium
    from app.models.user_coach_card import UserCoachCard
    from app.models.user_stadium_card import UserStadiumCard
    from app.services import personal_squad_service

    coach = Coach(display_name="Земляк", rarity=Rarity.common, country=country)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.ATTACK_CENTRAL, magnitude=1)]
    stadium = Stadium(display_name="Домашний", rarity=Rarity.common, boost_pct=0.0, club=club)
    db_session.add_all([coach, stadium])
    await db_session.flush()
    coach_card = UserCoachCard(user_id=user.id, coach_id=coach.id, serial_number=1, source=CardSource.pack)
    stadium_card = UserStadiumCard(user_id=user.id, stadium_id=stadium.id, serial_number=1, source=CardSource.pack)
    db_session.add_all([coach_card, stadium_card])
    await db_session.flush()
    squad = await personal_squad_service._get_row(db_session, user.id, None)
    squad.user_coach_card_id, squad.user_stadium_card_id = coach_card.id, stadium_card.id
    await db_session.commit()


async def test_player_tournament_stadium_extra_only_at_home(client, db_session, bot_token):
    from app.services import player_tournament_simulation_service as psim
    from app.services import personal_squad_service
    from tests.player_tournament_helpers import make_ready_user

    user = await make_ready_user(client, db_session, bot_token, 891001)
    _squad, pairs = await personal_squad_service.resolve_active_squad(db_session, user.id)
    gk_card = next(c for c, s in pairs if s.code == "GK")
    await _equip_personal_coach_and_stadium(db_session, user, country="Тестландия", club=gk_card.player.club)
    config = await _config(db_session)
    rules = ChemistryRules(coach_country_points=1, stadium_club_points=1, thresholds=(9, 10, 11))  # links alone give 0

    home = await psim._build_side(db_session, user.id, is_home=True, config=config, chemistry_rules=rules)
    away = await psim._build_side(db_session, user.id, is_home=False, config=config, chemistry_rules=rules)
    # Factory players share the coach's country: everyone gets the coach point.
    assert all(points == 1 for cid, points in away.chemistry["cards"].items())
    assert home.chemistry["cards"][str(gk_card.id)] == 2
    assert home.chemistry["team"] == away.chemistry["team"] + 1

    # The squad editor shows the home view and names coach country / stadium club.
    headers = telegram_headers(891001, bot_token)
    config.chemistry_enabled = True
    await db_session.commit()
    squads = (await client.get(f"{API}/player-tournaments/squads", headers=headers)).json()
    chem = next(s for s in squads if s["is_active"])["chemistry"]
    assert chem["coach_country"] == "Тестландия" and chem["stadium_club"] == gk_card.player.club
    gk = next(p for p in chem["players"] if p["slot_code"] == "GK")
    assert gk["coach_bonus"] == 1 and gk["stadium_bonus"] == 1


async def test_club_stadium_extra_only_for_home_side(client, db_session, bot_token):
    from app.models.club_stadium_card import ClubStadiumCard
    from app.models.enums import ClubStadiumCardSource
    from app.models.stadium import Stadium
    from app.services.club_squad_service import _get_or_none_lineup

    club, _captain, _headers = await _club(client, db_session, bot_token, 892001, "Химия стадион")
    _lineup, _sub, pairs, club_lineup = await sim.resolve_match_lineup(db_session, club.id)
    gk_card = next(c for c, s in pairs if s.code == "GK")
    stadium = Stadium(display_name="Клубный дом", rarity=Rarity.common, boost_pct=0.0, club=gk_card.player.club)
    db_session.add(stadium)
    await db_session.flush()
    card = ClubStadiumCard(club_id=club.id, stadium_id=stadium.id, serial_number=1, source=ClubStadiumCardSource.club_pack)
    db_session.add(card)
    await db_session.flush()
    row = await _get_or_none_lineup(db_session, club.id)
    row.club_stadium_card_id = card.id
    await db_session.commit()

    lineup, _sub, pairs, club_lineup = await sim.resolve_match_lineup(db_session, club.id)
    rules = ChemistryRules(stadium_club_points=1, thresholds=(9, 10, 11), rating_per_point=2)
    home, _ = sim.apply_chemistry(lineup, pairs, club_lineup, rules, is_home=True)
    away, _ = sim.apply_chemistry(lineup, pairs, club_lineup, rules, is_home=False)
    gk_home = next(a for a in home if a["club_card_id"] == gk_card.id)
    gk_away = next(a for a in away if a["club_card_id"] == gk_card.id)
    assert gk_home["rating"] == gk_away["rating"] + 2


async def test_admin_sets_and_clears_coach_country_and_stadium_club(client, db_session, bot_token):
    resp = await client.post(f"{API}/auth/session", headers=telegram_headers(999000001, bot_token))
    auth = {"Authorization": f"Bearer {resp.json()['admin_token']}"}
    created = await client.post(f"{API}/admin/coaches", headers=auth, json={
        "display_name": "Луис", "rarity": "common", "country": "  Испания ", "boosts": [{"boost_type": "attack_central"}],
    })
    assert created.status_code == 200, created.text
    assert created.json()["country"] == "Испания"
    cleared = await client.put(f"{API}/admin/coaches/{created.json()['id']}", headers=auth, json={"country": ""})
    assert cleared.status_code == 200 and cleared.json()["country"] is None

    stadium = await client.post(f"{API}/admin/stadiums", headers=auth, json={
        "display_name": "Бернабеу", "rarity": "rare", "boost_pct": 0.05, "club": "Реал Мадрид",
    })
    assert stadium.status_code == 200, stadium.text
    assert stadium.json()["club"] == "Реал Мадрид"
