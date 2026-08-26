import secrets

from sqlalchemy import select

from app.models.club import Club, ClubMember
from app.models.enums import ClubRole, ClubType, ClubLogoShape
from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers


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
