import secrets

import pytest_asyncio
from sqlalchemy import select

from app.models.club import Club, ClubMember
from app.models.enums import ClubRole, ClubType, ClubLogoShape, Position
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """club_service.create_club now seeds a starting squad on every club
    creation (Task 4) — give every test in this file enough active players
    per formation category (GK/DEF/MID/FWD) to draw from, since the pytest
    suite's players table is otherwise empty (fresh SQLite schema per test,
    see conftest.py's `_fresh_schema`)."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def test_create_club_debits_cost_and_makes_creator_captain(client, db_session, bot_token):
    user = await _register(client, db_session, 820001, bot_token)
    headers = telegram_headers(820001, bot_token)

    resp = await client.post(
        "/api/v1/clubs",
        headers=headers,
        json={"name": "Ночные волки", "description": "test", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["captain_id"] == user.id
    assert body["my_role"] == "captain"
    assert body["member_count"] == 1
    assert body["invite_code"]

    await db_session.refresh(user)
    assert user.balance == 500 - 500  # starting_balance (500 in test settings) - default club_creation_cost_coins (500)


async def test_create_club_rejects_user_already_in_a_club(client, db_session, bot_token):
    await _register(client, db_session, 820002, bot_token)
    headers = telegram_headers(820002, bot_token)
    payload = {"name": "Клуб раз", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"}
    first = await client.post("/api/v1/clubs", headers=headers, json=payload)
    assert first.status_code == 200

    payload2 = {"name": "Клуб два", "club_type": "open", "logo_shape": "circle", "logo_color": "#00FF00"}
    second = await client.post("/api/v1/clubs", headers=headers, json=payload2)
    assert second.status_code == 409


async def test_create_club_fails_on_insufficient_balance(client, db_session, bot_token):
    user = await _register(client, db_session, 820003, bot_token)
    user.balance = 10
    db_session.add(user)
    await db_session.commit()
    headers = telegram_headers(820003, bot_token)

    resp = await client.post(
        "/api/v1/clubs", headers=headers,
        json={"name": "Бедный клуб", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 400  # InsufficientBalanceError maps to 400 (core/exceptions.py)


async def test_create_club_rejects_duplicate_name(client, db_session, bot_token):
    await _register(client, db_session, 820015, bot_token)
    first = await client.post(
        "/api/v1/clubs", headers=telegram_headers(820015, bot_token),
        json={"name": "Уникальный клуб", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert first.status_code == 200

    await _register(client, db_session, 820016, bot_token)
    second = await client.post(
        "/api/v1/clubs", headers=telegram_headers(820016, bot_token),
        json={"name": "Уникальный клуб", "club_type": "open", "logo_shape": "circle", "logo_color": "#00FF00"},
    )
    assert second.status_code == 409
    assert second.json()["error"]["message"] == "Клуб с таким названием уже существует"


async def test_list_clubs_filters_by_search(client, db_session, bot_token):
    await _register(client, db_session, 820004, bot_token)
    await client.post(
        "/api/v1/clubs", headers=telegram_headers(820004, bot_token),
        json={"name": "Красные дьяволы", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    await _register(client, db_session, 820005, bot_token)
    await client.post(
        "/api/v1/clubs", headers=telegram_headers(820005, bot_token),
        json={"name": "Синие орлы", "club_type": "closed", "logo_shape": "circle", "logo_color": "#0000FF"},
    )

    resp = await client.get("/api/v1/clubs", params={"search": "дьявол"}, headers=telegram_headers(820004, bot_token))
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert names == ["Красные дьяволы"]


async def test_get_my_club_404_when_not_in_a_club(client, db_session, bot_token):
    await _register(client, db_session, 820006, bot_token)
    resp = await client.get("/api/v1/clubs/me", headers=telegram_headers(820006, bot_token))
    assert resp.status_code == 404


async def test_get_club_detail_hides_invite_code_from_non_members(client, db_session, bot_token):
    await _register(client, db_session, 820007, bot_token)
    create_resp = await client.post(
        "/api/v1/clubs", headers=telegram_headers(820007, bot_token),
        json={"name": "Скрытый клуб", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    club_id = create_resp.json()["id"]

    await _register(client, db_session, 820008, bot_token)
    outsider_resp = await client.get(f"/api/v1/clubs/{club_id}", headers=telegram_headers(820008, bot_token))
    assert outsider_resp.status_code == 200
    assert outsider_resp.json()["invite_code"] is None
    assert outsider_resp.json()["my_role"] is None

    member_resp = await client.get(f"/api/v1/clubs/{club_id}", headers=telegram_headers(820007, bot_token))
    assert member_resp.json()["invite_code"]
    assert member_resp.json()["my_role"] == "captain"


async def _create_club(client, bot_token, telegram_id, name, club_type="open"):
    await _register_only(client, bot_token, telegram_id)
    headers = telegram_headers(telegram_id, bot_token)
    resp = await client.post(
        "/api/v1/clubs", headers=headers,
        json={"name": name, "club_type": club_type, "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 200
    return resp.json(), headers


async def _register_only(client, bot_token, telegram_id):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200


async def test_join_open_club_adds_member(client, db_session, bot_token):
    club, _ = await _create_club(client, bot_token, 820101, "Открытый клуб")
    await _register_only(client, bot_token, 820102)
    headers2 = telegram_headers(820102, bot_token)

    resp = await client.post(f"/api/v1/clubs/{club['id']}/join", headers=headers2)
    assert resp.status_code == 200
    assert resp.json()["member_count"] == 2


async def test_join_closed_club_creates_request_then_accept_adds_member(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820103, "Закрытый клуб", club_type="closed")
    await _register_only(client, bot_token, 820104)
    headers2 = telegram_headers(820104, bot_token)

    direct_join = await client.post(f"/api/v1/clubs/{club['id']}/join", headers=headers2)
    assert direct_join.status_code == 409

    req_resp = await client.post(f"/api/v1/clubs/{club['id']}/join-requests", headers=headers2)
    assert req_resp.status_code == 200
    request_id = req_resp.json()["id"]

    list_resp = await client.get("/api/v1/clubs/me/join-requests", headers=captain_headers)
    assert len(list_resp.json()) == 1

    accept_resp = await client.post(f"/api/v1/clubs/me/join-requests/{request_id}/accept", headers=captain_headers)
    assert accept_resp.status_code == 200
    assert accept_resp.json()["member_count"] == 2


async def test_leave_club_promotes_longest_tenured_assistant(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820105, "Клуб с ассистентом")
    await _register_only(client, bot_token, 820106)
    member_headers = telegram_headers(820106, bot_token)
    join = await client.post(f"/api/v1/clubs/{club['id']}/join", headers=member_headers)
    member_user_id = [m for m in join.json()["members"] if m["role"] == "member"][0]["user_id"]

    appoint = await client.post(f"/api/v1/clubs/me/assistants/{member_user_id}/appoint", headers=captain_headers)
    assert appoint.status_code == 200

    leave_resp = await client.post("/api/v1/clubs/me/leave", headers=captain_headers)
    assert leave_resp.status_code == 200

    new_club_state = await client.get("/api/v1/clubs/me", headers=member_headers)
    assert new_club_state.json()["captain_id"] == member_user_id


async def test_leave_club_disbands_when_no_assistants(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820107, "Клуб без ассистентов")
    leave_resp = await client.post("/api/v1/clubs/me/leave", headers=captain_headers)
    assert leave_resp.status_code == 200

    check = await client.get(f"/api/v1/clubs/{club['id']}", headers=captain_headers)
    assert check.status_code == 404


async def test_kick_member_removes_them(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820108, "Клуб-кикер")
    await _register_only(client, bot_token, 820109)
    member_headers = telegram_headers(820109, bot_token)
    join = await client.post(f"/api/v1/clubs/{club['id']}/join", headers=member_headers)
    member_user_id = [m for m in join.json()["members"] if m["role"] == "member"][0]["user_id"]

    kick_resp = await client.post(f"/api/v1/clubs/me/members/{member_user_id}/kick", headers=captain_headers)
    assert kick_resp.status_code == 200
    assert kick_resp.json()["member_count"] == 1

    solo_check = await client.get("/api/v1/clubs/me", headers=member_headers)
    assert solo_check.status_code == 404


async def test_join_by_invite_code(client, db_session, bot_token):
    club, _ = await _create_club(client, bot_token, 820110, "Клуб по инвайту", club_type="closed")
    await _register_only(client, bot_token, 820111)
    headers2 = telegram_headers(820111, bot_token)

    resp = await client.post("/api/v1/clubs/join-by-invite", headers=headers2, json={"invite_code": club["invite_code"]})
    assert resp.status_code == 200
    assert resp.json()["member_count"] == 2


async def test_transfer_captain(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820112, "Клуб-передача")
    await _register_only(client, bot_token, 820113)
    member_headers = telegram_headers(820113, bot_token)
    join = await client.post(f"/api/v1/clubs/{club['id']}/join", headers=member_headers)
    member_user_id = [m for m in join.json()["members"] if m["role"] == "member"][0]["user_id"]

    resp = await client.post("/api/v1/clubs/me/transfer-captain", headers=captain_headers, json={"user_id": member_user_id})
    assert resp.status_code == 200
    assert resp.json()["captain_id"] == member_user_id


async def test_disband_club(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820114, "Клуб на роспуск")
    resp = await client.post("/api/v1/clubs/me/disband", headers=captain_headers)
    assert resp.status_code == 204

    check = await client.get(f"/api/v1/clubs/{club['id']}", headers=captain_headers)
    assert check.status_code == 404


async def test_create_club_seeds_a_complete_starting_squad(client, db_session, bot_token):
    from app.models.club_card import ClubCard
    from app.models.club_lineup import ClubLineup, ClubLineupCard
    from sqlalchemy import func, select

    await _register_only(client, bot_token, 820200)
    headers = telegram_headers(820200, bot_token)
    resp = await client.post(
        "/api/v1/clubs", headers=headers,
        json={"name": "Клуб со стартовым составом", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    club_id = resp.json()["id"]

    total_cards = (
        await db_session.execute(select(func.count(ClubCard.id)).where(ClubCard.club_id == club_id))
    ).scalar_one()
    assert total_cards == 15  # 11 starters + 4 bench

    lineup = (await db_session.execute(select(ClubLineup).where(ClubLineup.club_id == club_id))).scalar_one()
    lineup_card_count = (
        await db_session.execute(select(func.count(ClubLineupCard.id)).where(ClubLineupCard.club_lineup_id == lineup.id))
    ).scalar_one()
    assert lineup_card_count == 11

    slot_codes = (
        await db_session.execute(select(ClubLineupCard.slot_code).where(ClubLineupCard.club_lineup_id == lineup.id))
    ).scalars().all()
    assert len(set(slot_codes)) == 11  # every formation slot filled exactly once
