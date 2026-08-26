import pytest_asyncio
from sqlalchemy import select

from app.models.club_lineup import ClubLineup, ClubLineupCard
from app.models.enums import Position
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """club_service.create_club seeds a starting squad on every club
    creation (Task 4) — give every test in this file enough active players
    per formation category (GK/DEF/MID/FWD) to draw from. Unlike
    test_clubs.py, this file has no other autouse fixture doing this —
    autouse fixtures are file-scoped in this codebase's test setup, so it
    must be repeated here (fresh SQLite schema per test, see conftest.py's
    `_fresh_schema`)."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _register_only(client, bot_token, telegram_id):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200


async def _create_club(client, bot_token, telegram_id, name):
    await _register_only(client, bot_token, telegram_id)
    headers = telegram_headers(telegram_id, bot_token)
    resp = await client.post(
        "/api/v1/clubs", headers=headers,
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 200
    return resp.json(), headers


async def test_get_club_lineup_is_complete_after_creation(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820300, "Клуб с готовым составом")
    resp = await client.get("/api/v1/clubs/me/lineup", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_complete"] is True
    assert body["team_strength"] is not None
    assert len(body["slots"]) == 11
    assert all(s["card"] is not None for s in body["slots"])


async def test_list_club_cards_includes_bench(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820301, "Клуб со скамейкой")
    resp = await client.get("/api/v1/clubs/me/cards", headers=headers)
    assert resp.status_code == 200
    cards = resp.json()
    assert len(cards) == 15
    assert sum(1 for c in cards if not c["is_in_lineup"]) == 4


CATEGORY_POSITIONS_FOR_TEST = {
    "GK": {"GK"}, "DEF": {"LB", "CB", "RB"}, "MID": {"CDM", "CM", "CAM", "LM", "RM"}, "FWD": {"LW", "ST", "RW"},
}


def _category_for_position(position: str) -> str:
    return next(category for category, positions in CATEGORY_POSITIONS_FOR_TEST.items() if position in positions)


async def test_set_club_lineup_swaps_a_bench_card_into_a_slot(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820302, "Клуб с заменой")
    cards = (await client.get("/api/v1/clubs/me/cards", headers=headers)).json()
    bench_card = next(c for c in cards if not c["is_in_lineup"])
    bench_category = _category_for_position(bench_card["player"]["position"])
    lineup = (await client.get("/api/v1/clubs/me/lineup", headers=headers)).json()

    # Every club is seeded with exactly one bench card per category and one
    # starter per formation slot within that same category, so there is
    # always at least one legal target slot — same category, any slot.
    matching_slot = next(s for s in lineup["slots"] if s["category"] == bench_category)
    slots_payload = [
        {"slot_code": s["slot_code"], "club_card_id": bench_card["id"] if s["slot_code"] == matching_slot["slot_code"] else s["card"]["id"]}
        for s in lineup["slots"]
    ]
    resp = await client.put("/api/v1/clubs/me/lineup", headers=headers, json={"slots": slots_payload})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_complete"] is True

    # Regression check for the identity-map staleness bug fixed alongside
    # this test: the PUT response itself (not just a subsequent GET) must
    # reflect the just-swapped card in its slot. With expire_on_commit=False
    # (see database.py), a re-read missing populate_existing=True can
    # silently return the session's pre-swap cached ClubLineup object.
    put_slot = next(s for s in body["slots"] if s["slot_code"] == matching_slot["slot_code"])
    assert put_slot["card"]["id"] == bench_card["id"]


async def test_non_manager_cannot_set_lineup(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820303, "Клуб без прав")
    await _register_only(client, bot_token, 820304)
    member_headers = telegram_headers(820304, bot_token)
    await client.post(f"/api/v1/clubs/{club['id']}/join", headers=member_headers)

    lineup = (await client.get("/api/v1/clubs/me/lineup", headers=member_headers)).json()
    slots_payload = [{"slot_code": s["slot_code"], "club_card_id": s["card"]["id"]} for s in lineup["slots"]]
    resp = await client.put("/api/v1/clubs/me/lineup", headers=member_headers, json={"slots": slots_payload})
    assert resp.status_code == 403
