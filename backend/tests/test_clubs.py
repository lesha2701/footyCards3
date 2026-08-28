import asyncio
import os
import secrets
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.exceptions import ConflictError
from app.models.club import Club, ClubMember
from app.models.club_daily_claim import ClubDailyClaim
from app.models.enums import ClubRole, ClubType, ClubLogoShape, Position
from app.models.user import User
from app.services.club_service import claim_daily_reward, join_by_invite, join_open_club, leave_club
from app.services.game_config_service import get_config
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

# See test_club_packs.py's REAL_POSTGRES_URL comment for why this test opens its own
# independent connection to the real dev Postgres instance rather than using the pytest
# suite's `client`/`db_session` fixtures (hardcoded to in-memory SQLite, single shared
# connection, can't reproduce genuine two-connection unique-constraint race timing).
REAL_POSTGRES_URL = os.environ.get("REAL_POSTGRES_URL", "postgresql+asyncpg://postgres:1234@postgres:5432/footycards")


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


async def test_captain_less_disband_marks_active_tournament_club_withdrawn(client, db_session, bot_token):
    from app.models.tournament import TournamentClub
    from app.services.tournament_queue_service import apply_to_tournament

    clubs_and_captains = []
    for i in range(8):
        telegram_id = 840000 + i
        club, _ = await _create_club(client, bot_token, telegram_id, f"Клуб выбывания {i}")
        second_member_id = telegram_id + 900_000
        await _register_only(client, bot_token, second_member_id)
        join_resp = await client.post(
            f"/api/v1/clubs/{club['id']}/join", headers=telegram_headers(second_member_id, bot_token),
        )
        assert join_resp.status_code == 200
        captain = await get_user_by_telegram_id(db_session, telegram_id)
        clubs_and_captains.append((club["id"], captain))

    tournament_id = None
    for club_id, captain in clubs_and_captains:
        result = await apply_to_tournament(db_session, captain)
        if result.tournament_id is not None:
            tournament_id = result.tournament_id
    assert tournament_id is not None

    disbanded_club_id, _sole_captain = clubs_and_captains[0]
    resp = await client.post("/api/v1/clubs/me/leave", headers=telegram_headers(840000, bot_token))
    assert resp.status_code == 200

    tc = (
        await db_session.execute(
            select(TournamentClub).where(
                TournamentClub.tournament_id == tournament_id, TournamentClub.club_id == disbanded_club_id,
            )
        )
    ).scalar_one()
    assert tc.is_withdrawn is True

    # Soft-disband, not hard-delete: the Club row itself must survive (so TournamentClub /
    # TournamentMatch / TournamentClubStanding rows FK'd to it with ON DELETE CASCADE don't get
    # silently wiped for every other club that ever played against it — see real-Postgres
    # verification in the task-15 fix-round report).
    disbanded_club_row = await db_session.get(Club, disbanded_club_id)
    assert disbanded_club_row is not None
    assert disbanded_club_row.is_disbanded is True
    remaining_memberships = (
        await db_session.execute(select(ClubMember).where(ClubMember.club_id == disbanded_club_id))
    ).scalars().all()
    assert remaining_memberships == []


async def test_leave_club_without_tournament_history_still_hard_deletes(client, db_session, bot_token):
    """Regression test: a club that never touched a tournament must behave exactly as before
    the soft-disband fix — hard-deleted outright, not left behind as an is_disbanded ghost."""
    club, captain_headers = await _create_club(client, bot_token, 830000, "Клуб без истории турниров")
    leave_resp = await client.post("/api/v1/clubs/me/leave", headers=captain_headers)
    assert leave_resp.status_code == 200

    club_row = await db_session.get(Club, club["id"])
    assert club_row is None


async def test_disbanded_club_hidden_from_list_and_join_entry_points(client, db_session, bot_token):
    from app.services.tournament_queue_service import apply_to_tournament

    clubs_and_captains = []
    for i in range(8):
        telegram_id = 831000 + i
        club, _ = await _create_club(client, bot_token, telegram_id, f"Клуб призрак {i}")
        second_member_id = telegram_id + 900_000
        await _register_only(client, bot_token, second_member_id)
        join_resp = await client.post(
            f"/api/v1/clubs/{club['id']}/join", headers=telegram_headers(second_member_id, bot_token),
        )
        assert join_resp.status_code == 200
        captain = await get_user_by_telegram_id(db_session, telegram_id)
        clubs_and_captains.append((club["id"], captain))

    tournament_id = None
    for club_id, captain in clubs_and_captains:
        result = await apply_to_tournament(db_session, captain)
        if result.tournament_id is not None:
            tournament_id = result.tournament_id
    assert tournament_id is not None

    ghost_club_id, _sole_captain = clubs_and_captains[0]
    resp = await client.post("/api/v1/clubs/me/leave", headers=telegram_headers(831000, bot_token))
    assert resp.status_code == 200

    list_resp = await client.get("/api/v1/clubs", headers=telegram_headers(831001, bot_token))
    assert list_resp.status_code == 200
    assert all(c["id"] != ghost_club_id for c in list_resp.json())

    await _register_only(client, bot_token, 839999)
    outsider_headers = telegram_headers(839999, bot_token)
    join_attempt = await client.post(f"/api/v1/clubs/{ghost_club_id}/join", headers=outsider_headers)
    assert join_attempt.status_code == 404

    join_request_attempt = await client.post(f"/api/v1/clubs/{ghost_club_id}/join-requests", headers=outsider_headers)
    assert join_request_attempt.status_code == 404


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


async def test_captain_can_change_club_type_after_creation(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820140, "Клуб-смена-типа", club_type="open")
    assert club["club_type"] == "open"

    resp = await client.put("/api/v1/clubs/me/type", headers=captain_headers, json={"club_type": "closed"})
    assert resp.status_code == 200
    assert resp.json()["club_type"] == "closed"

    check = await client.get(f"/api/v1/clubs/{club['id']}", headers=captain_headers)
    assert check.json()["club_type"] == "closed"


async def test_changing_club_type_to_closed_requires_join_request_afterwards(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820141, "Клуб-теперь-закрыт", club_type="open")
    await client.put("/api/v1/clubs/me/type", headers=captain_headers, json={"club_type": "closed"})

    await _register_only(client, bot_token, 820142)
    applicant_headers = telegram_headers(820142, bot_token)
    direct_join = await client.post(f"/api/v1/clubs/{club['id']}/join", headers=applicant_headers)
    assert direct_join.status_code == 409

    request = await client.post(f"/api/v1/clubs/{club['id']}/join-requests", headers=applicant_headers)
    assert request.status_code == 200


async def test_non_captain_cannot_change_club_type(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820143, "Клуб-чужой-тип", club_type="open")
    await _register_only(client, bot_token, 820144)
    member_headers = telegram_headers(820144, bot_token)
    await client.post(f"/api/v1/clubs/{club['id']}/join", headers=member_headers)

    resp = await client.put("/api/v1/clubs/me/type", headers=member_headers, json={"club_type": "closed"})
    assert resp.status_code == 403


async def test_disband_club(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820114, "Клуб на роспуск")
    resp = await client.post("/api/v1/clubs/me/disband", headers=captain_headers)
    assert resp.status_code == 204

    check = await client.get(f"/api/v1/clubs/{club['id']}", headers=captain_headers)
    assert check.status_code == 404


async def test_disband_club_with_tournament_history_soft_disbands(client, db_session, bot_token):
    """disband_club (POST /clubs/me/disband) is a separate, captain-initiated explicit-disband
    entry point from leave_club's auto-disband-when-no-assistant branch — a captain WITH
    assistants can call this directly. It must apply the same soft-disband decision (Club row
    ID 449-462's original bug: unconditional db.delete(club) with no tournament-history check,
    cascade-deleting TournamentClub/TournamentMatch/TournamentClubStanding rows)."""
    from app.models.tournament import TournamentClub
    from app.services.tournament_queue_service import apply_to_tournament

    clubs_and_captains = []
    for i in range(8):
        telegram_id = 832000 + i
        club, captain_headers = await _create_club(client, bot_token, telegram_id, f"Клуб роспуска {i}")
        second_member_id = telegram_id + 900_000
        await _register_only(client, bot_token, second_member_id)
        join_resp = await client.post(
            f"/api/v1/clubs/{club['id']}/join", headers=telegram_headers(second_member_id, bot_token),
        )
        assert join_resp.status_code == 200
        if i == 0:
            # Give the club-to-disband an assistant, so this exercises disband_club (reachable
            # by a captain WITH an assistant present) rather than leave_club's no-assistant
            # auto-disband path.
            assistant_user_id = [m for m in join_resp.json()["members"] if m["role"] == "member"][0]["user_id"]
            appoint = await client.post(
                f"/api/v1/clubs/me/assistants/{assistant_user_id}/appoint", headers=captain_headers,
            )
            assert appoint.status_code == 200
        captain = await get_user_by_telegram_id(db_session, telegram_id)
        clubs_and_captains.append((club["id"], captain, captain_headers))

    tournament_id = None
    for club_id, captain, _headers in clubs_and_captains:
        result = await apply_to_tournament(db_session, captain)
        if result.tournament_id is not None:
            tournament_id = result.tournament_id
    assert tournament_id is not None

    disbanded_club_id, _captain, disband_headers = clubs_and_captains[0]
    resp = await client.post("/api/v1/clubs/me/disband", headers=disband_headers)
    assert resp.status_code == 204

    club_row = await db_session.get(Club, disbanded_club_id)
    assert club_row is not None
    assert club_row.is_disbanded is True
    remaining_memberships = (
        await db_session.execute(select(ClubMember).where(ClubMember.club_id == disbanded_club_id))
    ).scalars().all()
    assert remaining_memberships == []

    tc = (
        await db_session.execute(
            select(TournamentClub).where(
                TournamentClub.tournament_id == tournament_id, TournamentClub.club_id == disbanded_club_id,
            )
        )
    ).scalar_one()
    assert tc.is_withdrawn is True


async def test_join_by_invite_rejects_disbanded_club(client, db_session, bot_token):
    from app.models.tournament import TournamentClub
    from app.services.tournament_queue_service import apply_to_tournament

    clubs_and_captains = []
    for i in range(8):
        telegram_id = 833000 + i
        club, _ = await _create_club(client, bot_token, telegram_id, f"Клуб инвайта {i}")
        second_member_id = telegram_id + 900_000
        await _register_only(client, bot_token, second_member_id)
        join_resp = await client.post(
            f"/api/v1/clubs/{club['id']}/join", headers=telegram_headers(second_member_id, bot_token),
        )
        assert join_resp.status_code == 200
        captain = await get_user_by_telegram_id(db_session, telegram_id)
        clubs_and_captains.append((club["id"], club["invite_code"], captain))

    tournament_id = None
    for club_id, _invite_code, captain in clubs_and_captains:
        result = await apply_to_tournament(db_session, captain)
        if result.tournament_id is not None:
            tournament_id = result.tournament_id
    assert tournament_id is not None

    disbanded_club_id, disbanded_invite_code, _captain = clubs_and_captains[0]
    resp = await client.post("/api/v1/clubs/me/leave", headers=telegram_headers(833000, bot_token))
    assert resp.status_code == 200

    club_row = await db_session.get(Club, disbanded_club_id)
    assert club_row.is_disbanded is True

    await _register_only(client, bot_token, 839998)
    outsider_headers = telegram_headers(839998, bot_token)
    invite_resp = await client.post(
        "/api/v1/clubs/join-by-invite", headers=outsider_headers, json={"invite_code": disbanded_invite_code},
    )
    assert invite_resp.status_code == 404


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


async def test_claim_daily_reward_credits_budget_once_per_day(client, db_session, bot_token):
    club, headers = await _create_club(client, bot_token, 820201, "Клуб с наградой")
    resp = await client.post("/api/v1/clubs/me/daily-claim", headers=headers)
    assert resp.status_code == 200

    from app.models.club import Club
    updated_club = await db_session.get(Club, club["id"])
    await db_session.refresh(updated_club)
    assert updated_club.budget == 200  # GameConfig.club_daily_reward_coins default

    second_attempt = await client.post("/api/v1/clubs/me/daily-claim", headers=headers)
    assert second_attempt.status_code == 409


async def test_club_detail_reports_daily_reward_countdown_only_after_claiming(client, db_session, bot_token):
    club, headers = await _create_club(client, bot_token, 820202, "Клуб с отсчётом")

    before = await client.get("/api/v1/clubs/me", headers=headers)
    assert before.json()["daily_reward_seconds_remaining"] is None

    claim_resp = await client.post("/api/v1/clubs/me/daily-claim", headers=headers)
    assert claim_resp.status_code == 200
    assert claim_resp.json()["daily_reward_seconds_remaining"] is not None
    assert claim_resp.json()["daily_reward_seconds_remaining"] > 0

    after = await client.get("/api/v1/clubs/me", headers=headers)
    assert after.json()["daily_reward_seconds_remaining"] is not None
    assert after.json()["daily_reward_seconds_remaining"] > 0


async def test_claim_daily_reward_concurrent_same_user_no_double_credit():
    """Genuine concurrency regression test for the same unhandled-IntegrityError race as
    test_club_packs.py's test_open_club_pack_concurrent_same_idempotency_key_no_double_debit:
    two truly concurrent claim_daily_reward calls (asyncio.gather, two independent DB
    sessions/connections) for the same user/club/day both pass the pre-check SELECT (which
    runs before any lock is held) before either commits, so both attempt the INSERT into
    club_daily_claims. Postgres enforces the (club_id, user_id, claim_date) unique constraint
    at INSERT/flush time, not at COMMIT time — before the fix, the loser's `await db.commit()`
    raised an unhandled IntegrityError instead of a clean ConflictError/409. Runs against real
    Postgres (see REAL_POSTGRES_URL above) — skips if unreachable.
    """
    engine = create_async_engine(REAL_POSTGRES_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except OSError as exc:
        await engine.dispose()
        pytest.skip(f"real dev Postgres not reachable at {REAL_POSTGRES_URL!r}: {exc!r}")
    except OperationalError as exc:
        await engine.dispose()
        pytest.skip(f"real dev Postgres not reachable at {REAL_POSTGRES_URL!r}: {exc!r}")

    RealSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]

    setup = RealSessionLocal()
    user = club_id = user_id = None
    try:
        user = User(telegram_id=991_000_000_000 + uuid.uuid4().int % 1_000_000_000, username=f"claim_race_{suffix}")
        setup.add(user)
        await setup.flush()

        club = Club(
            name=f"Claim Race Club {suffix}", club_type=ClubType.open, logo_shape=ClubLogoShape.shield,
            logo_color="#654321", captain_id=user.id, invite_code=f"claim{suffix}"[:16], budget=0,
        )
        setup.add(club)
        await setup.flush()

        setup.add(ClubMember(club_id=club.id, user_id=user.id, role=ClubRole.captain))

        await setup.commit()
        user_id, club_id = user.id, club.id

        session_a = RealSessionLocal()
        session_b = RealSessionLocal()
        try:
            user_a = await session_a.get(User, user_id)
            user_b = await session_b.get(User, user_id)

            results = await asyncio.gather(
                claim_daily_reward(session_a, user_a),
                claim_daily_reward(session_b, user_b),
                return_exceptions=True,
            )
        finally:
            await session_a.close()
            await session_b.close()

        successes = [r for r in results if not isinstance(r, BaseException)]
        failures = [r for r in results if isinstance(r, BaseException)]
        assert len(successes) == 1, f"expected exactly one winner, got results: {results!r}"
        assert len(failures) == 1, f"expected exactly one loser raising ConflictError, got results: {results!r}"
        assert isinstance(failures[0], ConflictError), f"loser must raise ConflictError (409), not an unhandled exception: {failures[0]!r}"

        async with RealSessionLocal() as verify:
            config = await get_config(verify)
            final_club = await verify.get(Club, club_id)
            assert final_club.budget == config.club_daily_reward_coins, "club budget must reflect exactly one daily-reward credit, not two"
            claims = (
                await verify.execute(select(ClubDailyClaim).where(ClubDailyClaim.club_id == club_id, ClubDailyClaim.user_id == user_id))
            ).scalars().all()
            assert len(claims) == 1, "exactly one ClubDailyClaim row must exist despite two concurrent attempts"
    finally:
        # Self-cleaning: this test writes real rows into the shared dev Postgres instance, so
        # tear everything it created back down regardless of pass/fail. Deleting the club first
        # cascades club_members/club_daily_claims/club_budget_transactions (all
        # ondelete="CASCADE" on club_id); the user is deleted afterwards.
        async with RealSessionLocal() as cleanup:
            if club_id is not None:
                club_row = await cleanup.get(Club, club_id)
                if club_row is not None:
                    await cleanup.delete(club_row)
            await cleanup.commit()
            if user is not None and user_id is not None:
                user_row = await cleanup.get(User, user_id)
                if user_row is not None:
                    await cleanup.delete(user_row)
                    await cleanup.commit()
        await setup.close()
        await engine.dispose()


async def test_join_open_club_converts_race_integrity_error_to_conflict(client, db_session, bot_token, monkeypatch):
    """Regression test for an unhandled IntegrityError observed in production as a 500 on
    POST /clubs/{id}/join: club_members.user_id is globally unique (one club per user), and
    the pre-check SELECT in join_open_club runs before any row lock is held, so under real
    concurrent timing (e.g. a double-tap) it can report "not a member" for a user who, by the
    time the INSERT actually runs, already has a committed membership row elsewhere — the
    INSERT then violates the constraint. Real async-timing races proved too fast/serialized to
    reproduce reliably via asyncio.gather in this test harness (the two requests' pre-checks
    consistently ran far enough apart to see each other's committed state), so this reproduces
    the exact failure mode deterministically instead: force the pre-check to report "not a
    member" while a real conflicting membership row already exists, and assert the resulting
    IntegrityError is converted into a clean ConflictError rather than propagating raw."""
    existing_club, _ = await _create_club(client, bot_token, 820150, "Клуб А (уже в нём)")
    await _register_only(client, bot_token, 820151)
    joiner_headers = telegram_headers(820151, bot_token)
    await client.post(f"/api/v1/clubs/{existing_club['id']}/join", headers=joiner_headers)
    joiner = await get_user_by_telegram_id(db_session, 820151)

    target_club, _ = await _create_club(client, bot_token, 820152, "Клуб Б (гонка вступления)")

    async def fake_not_a_member(db, user_id):
        return None

    monkeypatch.setattr("app.services.club_service._get_membership", fake_not_a_member)

    with pytest.raises(ConflictError, match="уже состоишь"):
        await join_open_club(db_session, joiner, target_club["id"])


async def test_join_by_invite_converts_race_integrity_error_to_conflict(client, db_session, bot_token, monkeypatch):
    """Same race as test_join_open_club_converts_race_integrity_error_to_conflict above,
    reproduced for join_by_invite — the sibling function has the identical
    check-before-lock shape and was fixed the same way."""
    existing_club, _ = await _create_club(client, bot_token, 820153, "Клуб В (уже в нём)")
    await _register_only(client, bot_token, 820154)
    joiner_headers = telegram_headers(820154, bot_token)
    await client.post(f"/api/v1/clubs/{existing_club['id']}/join", headers=joiner_headers)
    joiner = await get_user_by_telegram_id(db_session, 820154)

    target_club, _ = await _create_club(client, bot_token, 820155, "Клуб Г (гонка приглашения)")

    async def fake_not_a_member(db, user_id):
        return None

    monkeypatch.setattr("app.services.club_service._get_membership", fake_not_a_member)

    with pytest.raises(ConflictError, match="уже состоишь"):
        await join_by_invite(db_session, joiner, target_club["invite_code"])


async def test_soft_disband_survives_real_postgres_cascade():
    """Committed, CI-run proof that soft-disbanding a club with tournament history does NOT
    trigger the ON DELETE CASCADE bug found in review: TournamentClub.club_id,
    TournamentMatch.club_a_id/club_b_id, and TournamentClubStanding.club_id all FK to clubs.id
    with ON DELETE CASCADE in the real schema — SQLite's in-memory test DB never enforces this
    (no PRAGMA foreign_keys=ON), so the SQLite-backed tests elsewhere in this file would pass
    even if leave_club regressed back to unconditionally calling db.delete(club). This test
    builds a genuine Tournament/TournamentClub/TournamentMatch/TournamentClubStanding footprint
    for one club directly against real Postgres (see REAL_POSTGRES_URL above), calls the actual
    leave_club service function, and asserts every one of those rows is still there afterward —
    proving _disband_or_soft_disband never issues db.delete(club) on this path. Skips if real
    Postgres is unreachable.
    """
    from datetime import datetime, timezone

    from app.models.enums import TournamentStatus
    from app.models.tournament import Tournament, TournamentClub
    from app.models.tournament_match import TournamentMatch
    from app.models.tournament_standing import TournamentClubStanding

    engine = create_async_engine(REAL_POSTGRES_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except OSError as exc:
        await engine.dispose()
        pytest.skip(f"real dev Postgres not reachable at {REAL_POSTGRES_URL!r}: {exc!r}")
    except OperationalError as exc:
        await engine.dispose()
        pytest.skip(f"real dev Postgres not reachable at {REAL_POSTGRES_URL!r}: {exc!r}")

    RealSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]

    setup = RealSessionLocal()
    captain = club_id = captain_id = tournament_id = tc_id = standing_id = match_id = None
    try:
        captain = User(telegram_id=992_000_000_000 + uuid.uuid4().int % 1_000_000_000, username=f"soft_disband_{suffix}")
        setup.add(captain)
        await setup.flush()

        club = Club(
            name=f"Soft Disband Club {suffix}", club_type=ClubType.open, logo_shape=ClubLogoShape.shield,
            logo_color="#112233", captain_id=captain.id, invite_code=f"sd{suffix}"[:16], budget=0,
        )
        setup.add(club)
        await setup.flush()
        setup.add(ClubMember(club_id=club.id, user_id=captain.id, role=ClubRole.captain))

        tournament = Tournament(status=TournamentStatus.active, rounds_simulated=1)
        setup.add(tournament)
        await setup.flush()
        tc = TournamentClub(tournament_id=tournament.id, club_id=club.id, is_withdrawn=False)
        setup.add(tc)
        standing = TournamentClubStanding(tournament_id=tournament.id, club_id=club.id, points=3, goals_for=2, goals_against=0)
        setup.add(standing)
        match = TournamentMatch(
            tournament_id=tournament.id, round_number=1, club_a_id=club.id, club_b_id=club.id,
            score_a=2, score_b=0, event_log=[], simulated_at=datetime.now(timezone.utc),
        )
        setup.add(match)
        await setup.commit()

        club_id, captain_id, tournament_id = club.id, captain.id, tournament.id
        tc_id, standing_id, match_id = tc.id, standing.id, match.id

        async with RealSessionLocal() as worker:
            captain_row = await worker.get(User, captain_id)
            await leave_club(worker, captain_row)

        async with RealSessionLocal() as verify:
            club_after = await verify.get(Club, club_id)
            assert club_after is not None, "club row must NOT be hard-deleted when it has tournament history"
            assert club_after.is_disbanded is True

            members_after = (
                await verify.execute(select(ClubMember).where(ClubMember.club_id == club_id))
            ).scalars().all()
            assert members_after == []

            tc_after = await verify.get(TournamentClub, tc_id)
            assert tc_after is not None, "TournamentClub row must survive — ON DELETE CASCADE must not fire"
            assert tc_after.is_withdrawn is True

            match_after = await verify.get(TournamentMatch, match_id)
            assert match_after is not None, "TournamentMatch row must survive — ON DELETE CASCADE must not fire"

            standing_after = await verify.get(TournamentClubStanding, standing_id)
            assert standing_after is not None, "TournamentClubStanding row must survive — ON DELETE CASCADE must not fire"
    finally:
        # Self-cleaning against the shared dev Postgres instance. The club row was never hard-
        # deleted by the code under test, so clean it up explicitly here (this cascades
        # tournament_matches/tournament_clubs/tournament_club_standings/club_members via their
        # own ON DELETE CASCADE — which is exactly fine for throwaway test scaffolding that has
        # no other club depending on it, unlike the real disband path this test exists to guard).
        async with RealSessionLocal() as cleanup:
            if club_id is not None:
                club_row = await cleanup.get(Club, club_id)
                if club_row is not None:
                    await cleanup.delete(club_row)
            if tournament_id is not None:
                tournament_row = await cleanup.get(Tournament, tournament_id)
                if tournament_row is not None:
                    await cleanup.delete(tournament_row)
            await cleanup.commit()
            if captain is not None and captain_id is not None:
                user_row = await cleanup.get(User, captain_id)
                if user_row is not None:
                    await cleanup.delete(user_row)
                    await cleanup.commit()
        await setup.close()
        await engine.dispose()


async def test_club_has_tournament_columns_with_zero_defaults(client, db_session, bot_token):
    club, _ = await _create_club(client, bot_token, 820300, "ФК Тест")
    result = await db_session.execute(select(Club).where(Club.name == "ФК Тест"))
    club_row = result.scalar_one()
    assert club_row.cups_count == 0
    assert club_row.stars_count == 0
    assert club_row.last_tournament_applied_at is None


async def test_club_detail_and_summary_expose_cups_and_stars_count(client, db_session, bot_token):
    await _register(client, db_session, 820020, bot_token)
    create_resp = await client.post(
        "/api/v1/clubs", headers=telegram_headers(820020, bot_token),
        json={"name": "Звёздный клуб", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["cups_count"] == 0
    assert create_resp.json()["stars_count"] == 0

    club_id = create_resp.json()["id"]
    club_row = await db_session.get(Club, club_id)
    club_row.cups_count = 3
    club_row.stars_count = 7
    db_session.add(club_row)
    await db_session.commit()

    detail_resp = await client.get(f"/api/v1/clubs/{club_id}", headers=telegram_headers(820020, bot_token))
    assert detail_resp.json()["cups_count"] == 3
    assert detail_resp.json()["stars_count"] == 7

    list_resp = await client.get("/api/v1/clubs", headers=telegram_headers(820020, bot_token))
    listed = next(c for c in list_resp.json() if c["id"] == club_id)
    assert listed["cups_count"] == 3
    assert listed["stars_count"] == 7
