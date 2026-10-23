"""Club roles (vice-captain, treasurer, budget policy), club list filters and
the «новый участник» notification."""
import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.club import Club, ClubMember
from app.models.enums import ClubRole, NotificationType, Position
from app.models.notification import Notification
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest.fixture(autouse=True)
async def _seed(db_session):
    rate_limit_module._hits.clear()
    for position in (Position.GK, Position.GK, Position.LB, Position.LB, Position.CB, Position.CB, Position.RB,
                     Position.RB, Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM, Position.LW,
                     Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _register(client, db_session, telegram_id, bot_token):
    headers = telegram_headers(telegram_id, bot_token)
    assert (await client.post("/api/v1/auth/session", headers=headers)).status_code == 200
    return headers, await get_user_by_telegram_id(db_session, telegram_id)


async def _club(client, db_session, bot_token, base_id, members=3, club_type="open"):
    cap_h, captain = await _register(client, db_session, base_id, bot_token)
    resp = await client.post("/api/v1/clubs", headers=cap_h, json={
        "name": f"Клуб {base_id}", "club_type": club_type, "logo_shape": "shield", "logo_color": "#FF0000",
    })
    club_id = resp.json()["id"]
    people = []
    for i in range(1, members + 1):
        h, u = await _register(client, db_session, base_id + i, bot_token)
        if club_type == "open":
            assert (await client.post(f"/api/v1/clubs/{club_id}/join", headers=h)).status_code == 200
        people.append((h, u))
    return club_id, cap_h, captain, people


async def _role(client, headers, user_id, role):
    return await client.post(f"/api/v1/clubs/me/members/{user_id}/role", headers=headers, json={"role": role})


async def test_captain_assigns_single_holder_roles(client, db_session, bot_token):
    _club_id, cap_h, _captain, people = await _club(client, db_session, bot_token, 880000)
    (a_h, a), (_b_h, b), _ = people

    assert (await _role(client, a_h, b.id, "treasurer")).status_code == 403

    resp = await _role(client, cap_h, a.id, "vice_captain")
    assert resp.status_code == 200, resp.text
    roles = {m["user_id"]: m["role"] for m in resp.json()["members"]}
    assert roles[a.id] == "vice_captain"

    # Only one vice-captain: giving it to b demotes a.
    roles = {m["user_id"]: m["role"] for m in (await _role(client, cap_h, b.id, "vice_captain")).json()["members"]}
    assert roles[a.id] == "member" and roles[b.id] == "vice_captain"
    roles = {m["user_id"]: m["role"] for m in (await _role(client, cap_h, a.id, "treasurer")).json()["members"]}
    assert roles[a.id] == "treasurer"
    assert (await _role(client, cap_h, a.id, "captain")).status_code == 409
    notes = (await db_session.execute(select(Notification).where(
        Notification.user_id == a.id, Notification.type == NotificationType.club_role_changed,
    ))).scalars().all()
    assert len(notes) == 3


async def test_vice_captain_succeeds_the_captain_and_edits_emblem(client, db_session, bot_token):
    club_id, cap_h, _captain, people = await _club(client, db_session, bot_token, 880010)
    (a_h, a), (b_h, b), _ = people
    await _role(client, cap_h, a.id, "assistant")
    await _role(client, cap_h, b.id, "vice_captain")

    body = (await client.get("/api/v1/clubs/me/emblem", headers=b_h)).json()
    assert body["can_edit"] is True
    resp = await client.put("/api/v1/clubs/me/emblem", headers=b_h, json={"logo_shape": "crest", "logo_color": "#123456"})
    assert resp.status_code == 200
    assert (await client.put("/api/v1/clubs/me/emblem", headers=a_h,
                             json={"logo_shape": "crest", "logo_color": "#123456"})).status_code == 403

    # The longer-serving assistant (a) is passed over for the vice-captain.
    assert (await client.post("/api/v1/clubs/me/leave", headers=cap_h)).status_code == 200
    club = await db_session.get(Club, club_id)
    await db_session.refresh(club)
    assert club.captain_id == b.id


async def test_treasurer_spends_budget_and_policy_excludes_assistants(client, db_session, bot_token):
    club_id, cap_h, _captain, people = await _club(client, db_session, bot_token, 880020)
    (a_h, a), (t_h, t), (m_h, _m) = people
    await _role(client, cap_h, a.id, "assistant")
    await _role(client, cap_h, t.id, "treasurer")
    club = await db_session.get(Club, club_id)
    club.budget = 100_000
    await db_session.commit()

    await client.get("/api/v1/clubs/me/emblem", headers=cap_h)
    items = (await client.get("/api/v1/clubs/me/emblem", headers=t_h)).json()["items"]
    coin_items = [i["id"] for i in items if i["coins_price"] > 0]

    assert (await client.get("/api/v1/clubs/me", headers=t_h)).json()["can_spend_budget"] is True
    assert (await client.get("/api/v1/clubs/me", headers=m_h)).json()["can_spend_budget"] is False
    assert (await client.post(f"/api/v1/clubs/me/emblem/items/{coin_items[0]}/buy", headers=t_h)).status_code == 200
    assert (await client.post(f"/api/v1/clubs/me/emblem/items/{coin_items[1]}/buy", headers=a_h)).status_code == 200
    assert (await client.post(f"/api/v1/clubs/me/emblem/items/{coin_items[2]}/buy", headers=m_h)).status_code == 403

    # The treasurer has no squad powers.
    assert (await client.post(f"/api/v1/clubs/me/members/{_m.id}/kick", headers=t_h)).status_code == 403

    assert (await client.put("/api/v1/clubs/me/budget-policy", headers=a_h, json={"treasurer_only": True})).status_code == 403
    resp = await client.put("/api/v1/clubs/me/budget-policy", headers=cap_h, json={"treasurer_only": True})
    assert resp.status_code == 200 and resp.json()["budget_treasurer_only"] is True
    assert (await client.post(f"/api/v1/clubs/me/emblem/items/{coin_items[2]}/buy", headers=a_h)).status_code == 403
    assert (await client.post(f"/api/v1/clubs/me/emblem/items/{coin_items[2]}/buy", headers=t_h)).status_code == 200


async def test_captain_is_notified_when_someone_joins(client, db_session, bot_token):
    _club_id, _cap_h, captain, people = await _club(client, db_session, bot_token, 880030, members=2)
    notes = (await db_session.execute(select(Notification).where(
        Notification.user_id == captain.id, Notification.type == NotificationType.club_member_joined,
    ))).scalars().all()
    assert len(notes) == 2


async def test_club_list_filters(client, db_session, bot_token):
    open_id, cap_h, *_ = await _club(client, db_session, bot_token, 880040, members=1)
    closed_id, *_ = await _club(client, db_session, bot_token, 880050, members=0, club_type="closed")
    full_id, *_ = await _club(client, db_session, bot_token, 880060, members=10)
    closed = await db_session.get(Club, closed_id)
    closed.cups_count = 5
    await db_session.commit()

    ids = lambda resp: [c["id"] for c in resp.json()]  # noqa: E731
    assert ids(await client.get("/api/v1/clubs", headers=cap_h, params={"club_type": "closed"})) == [closed_id]
    open_ids = ids(await client.get("/api/v1/clubs", headers=cap_h, params={"club_type": "open"}))
    assert set(open_ids) == {open_id, full_id}
    with_space = ids(await client.get("/api/v1/clubs", headers=cap_h, params={"has_space": "true"}))
    assert full_id not in with_space and open_id in with_space
    assert ids(await client.get("/api/v1/clubs", headers=cap_h, params={"sort": "cups"}))[0] == closed_id
    assert ids(await client.get("/api/v1/clubs", headers=cap_h))[0] == full_id
    members = (await db_session.execute(select(ClubMember).where(ClubMember.club_id == full_id))).scalars().all()
    assert len(members) == 11 and sum(m.role == ClubRole.captain for m in members) == 1
