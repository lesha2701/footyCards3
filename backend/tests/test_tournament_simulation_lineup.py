import pytest_asyncio

from app.models.club import Club
from app.models.club_card_availability import ClubCardAvailability
from app.models.enums import Position
from app.services.tournament_simulation_service import form_multiplier, resolve_match_lineup
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """Same seeding test_tournament_queue_service.py's own autouse fixture does —
    each club's starter squad needs active Players to draw from per formation
    category, plus enough extra depth for substitution tests to have a bench
    of matching-category candidates to pick from."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _create_club_with_full_squad(client, db_session, bot_token, telegram_id, name):
    """Registers telegram_id as captain of a fresh club. club_service.create_club
    already auto-seeds a full 11/11 starting lineup (plus 4 bench cards) via
    seed_starting_squad (Phase 2) — no extra lineup-filling step needed."""
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    captain = await get_user_by_telegram_id(db_session, telegram_id)

    create_resp = await client.post(
        "/api/v1/clubs", headers=telegram_headers(telegram_id, bot_token),
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert create_resp.status_code == 200
    club = await db_session.get(Club, create_resp.json()["id"])

    return club, captain


@pytest_asyncio.fixture
async def seeded_club_with_full_squad(client, db_session, bot_token):
    club, captain = await _create_club_with_full_squad(client, db_session, bot_token, 840001, "Тестовый клуб симуляции")
    return club, captain


async def test_resolve_match_lineup_returns_engine_shape(db_session, seeded_club_with_full_squad):
    club, _captain = seeded_club_with_full_squad
    lineup, had_sub, cards_with_slots = await resolve_match_lineup(db_session, club.id)
    assert len(lineup) == 11
    assert had_sub is False
    assert len(cards_with_slots) == 11
    for card, slot in cards_with_slots:
        assert card.id in {c["club_card_id"] for c in lineup}
        assert slot.code in {"GK", "DEF1", "DEF2", "DEF3", "DEF4", "MID1", "MID2", "MID3", "FWD1", "FWD2", "FWD3"}
    for c in lineup:
        assert set(c.keys()) >= {"club_card_id", "player_id", "name", "rating", "position", "category"}


async def test_resolve_match_lineup_substitutes_suspended_card(db_session, seeded_club_with_full_squad):
    club, _captain = seeded_club_with_full_squad
    lineup, _, _ = await resolve_match_lineup(db_session, club.id)
    suspended_card_id = lineup[0]["club_card_id"]
    db_session.add(ClubCardAvailability(club_card_id=suspended_card_id, rounds_remaining=2))
    await db_session.commit()

    new_lineup, had_sub, cards_with_slots = await resolve_match_lineup(db_session, club.id)
    assert had_sub is True
    assert suspended_card_id not in {c["club_card_id"] for c in new_lineup}
    assert len(new_lineup) == 11
    assert len(cards_with_slots) == 11
    assert suspended_card_id not in {c.id for c, _ in cards_with_slots}


async def test_form_multiplier_is_one_with_no_history(db_session, seeded_club_with_full_squad):
    club, _captain = seeded_club_with_full_squad
    from app.services.game_config_service import get_config
    config = await get_config(db_session)
    assert await form_multiplier(db_session, club.id, config) == 1.0
