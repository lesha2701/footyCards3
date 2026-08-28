import pytest_asyncio

from app.models.club import Club
from app.models.club_budget import ClubBudgetTransaction
from app.models.enums import ClubBudgetTransactionType, Position
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """create_club seeds a starting squad on every creation — same seeding every other club test
    file needs (see test_clubs.py's identical fixture)."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _admin_auth(client, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    token = session_resp.json()["admin_token"]
    return {"Authorization": f"Bearer {token}"}


async def _make_club(client, db_session, bot_token, telegram_id, name, club_type="open"):
    await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    resp = await client.post(
        "/api/v1/clubs", headers=telegram_headers(telegram_id, bot_token),
        json={"name": name, "club_type": club_type, "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 200
    return await db_session.get(Club, resp.json()["id"])


async def test_list_clubs_requires_admin(client):
    resp = await client.get("/api/v1/admin/clubs")
    assert resp.status_code == 401


async def test_list_clubs_filters_by_search_and_includes_disbanded(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    await _make_club(client, db_session, bot_token, 870001, "Красные дьяволы")
    disbanded = await _make_club(client, db_session, bot_token, 870002, "Синие орлы")
    disbanded.is_disbanded = True
    db_session.add(disbanded)
    await db_session.commit()

    resp = await client.get("/api/v1/admin/clubs", params={"search": "дьявол"}, headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["name"] == "Красные дьяволы"

    resp2 = await client.get("/api/v1/admin/clubs", params={"search": "орл"}, headers=auth)
    assert resp2.json()["items"][0]["is_disbanded"] is True


async def test_get_club_detail_returns_full_fields_and_404s_for_missing(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    club = await _make_club(client, db_session, bot_token, 870003, "Клуб детали")

    resp = await client.get(f"/api/v1/admin/clubs/{club.id}", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["member_count"] == 1
    assert body["invite_code"] == club.invite_code
    assert body["description"] == ""

    missing_resp = await client.get("/api/v1/admin/clubs/999999", headers=auth)
    assert missing_resp.status_code == 404


async def test_get_club_members_returns_roster(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    club = await _make_club(client, db_session, bot_token, 870004, "Клуб состава")

    resp = await client.get(f"/api/v1/admin/clubs/{club.id}/members", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["role"] == "captain"


async def test_get_club_budget_transactions_paginated(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    club = await _make_club(client, db_session, bot_token, 870005, "Клуб бюджета")

    db_session.add(
        ClubBudgetTransaction(
            club_id=club.id, amount=200, balance_before=0, balance_after=200,
            type=ClubBudgetTransactionType.daily_claim, description="Ежедневная награда",
        )
    )
    await db_session.commit()

    resp = await client.get(f"/api/v1/admin/clubs/{club.id}/budget-transactions", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["amount"] == 200
    assert body["items"][0]["type"] == "daily_claim"


async def test_get_club_tournaments_shows_null_rewards_before_completion_and_real_values_after(
    client, db_session, bot_token
):
    from app.services.tournament_simulation_service import simulate_next_round
    from app.services.tournament_queue_service import apply_to_tournament

    auth = await _admin_auth(client, bot_token)
    clubs_and_captains = []
    tournament_id = None
    for i in range(8):
        await client.post("/api/v1/auth/session", headers=telegram_headers(870100 + i, bot_token))
        create_resp = await client.post(
            "/api/v1/clubs", headers=telegram_headers(870100 + i, bot_token),
            json={"name": f"Клуб турнира {i}", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
        )
        club = await db_session.get(Club, create_resp.json()["id"])
        second_telegram_id = 870100 + i + 900_000
        await client.post("/api/v1/auth/session", headers=telegram_headers(second_telegram_id, bot_token))
        await client.post(f"/api/v1/clubs/{club.id}/join", headers=telegram_headers(second_telegram_id, bot_token))
        captain = await get_user_by_telegram_id(db_session, 870100 + i)
        result = await apply_to_tournament(db_session, captain)
        clubs_and_captains.append(club)
        if result.tournament_id is not None:
            tournament_id = result.tournament_id

    assert tournament_id is not None
    club0 = clubs_and_captains[0]

    mid_resp = await client.get(f"/api/v1/admin/clubs/{club0.id}/tournaments", headers=auth)
    assert mid_resp.status_code == 200
    mid_body = mid_resp.json()
    assert len(mid_body) == 1
    assert mid_body[0]["tournament_id"] == tournament_id
    assert mid_body[0]["status"] == "active"
    assert mid_body[0]["final_rank"] is None
    assert mid_body[0]["budget_awarded"] is None

    for _ in range(14):
        await simulate_next_round(db_session)
        await db_session.commit()

    done_resp = await client.get(f"/api/v1/admin/clubs/{club0.id}/tournaments", headers=auth)
    done_body = done_resp.json()
    assert done_body[0]["status"] == "completed"
    assert done_body[0]["budget_awarded"] is not None
    assert done_body[0]["final_rank"] is not None
