"""«Стена клуба»: posts, announcements via the bot, pins, unread counter."""
import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.enums import NotificationType, Position
from app.models.notification import Notification
from app.services.game_config_service import get_config
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


async def _club(client, db_session, bot_token, base_id):
    cap_h, captain = await _register(client, db_session, base_id, bot_token)
    club_id = (await client.post("/api/v1/clubs", headers=cap_h, json={
        "name": f"Клуб {base_id}", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000",
    })).json()["id"]
    people = []
    for i in (1, 2):
        h, u = await _register(client, db_session, base_id + i, bot_token)
        await client.post(f"/api/v1/clubs/{club_id}/join", headers=h)
        people.append((h, u))
    return cap_h, captain, people


async def test_members_post_and_see_unread(client, db_session, bot_token):
    cap_h, _captain, [(a_h, a), (b_h, _b)] = await _club(client, db_session, bot_token, 890000)
    resp = await client.post("/api/v1/clubs/me/wall", headers=a_h, json={"text": "  Всем привет!  "})
    assert resp.status_code == 200, resp.text
    post = resp.json()["posts"][0]
    assert post["text"] == "Всем привет!" and post["user_id"] == a.id and post["role"] == "member"
    assert post["can_delete"] is True and resp.json()["can_announce"] is False

    assert (await client.get("/api/v1/clubs/me", headers=b_h)).json()["wall_unread"] == 1
    assert (await client.get("/api/v1/clubs/me", headers=a_h)).json()["wall_unread"] == 0  # own post
    wall = (await client.get("/api/v1/clubs/me/wall", headers=b_h)).json()
    assert wall["posts"][0]["can_delete"] is False
    assert (await client.get("/api/v1/clubs/me", headers=b_h)).json()["wall_unread"] == 0

    # Only the author or a manager deletes.
    assert (await client.delete(f"/api/v1/clubs/me/wall/{post['id']}", headers=b_h)).status_code == 403
    assert (await client.delete(f"/api/v1/clubs/me/wall/{post['id']}", headers=cap_h)).json()["posts"] == []
    assert (await client.post("/api/v1/clubs/me/wall", headers=a_h, json={"text": "   "})).status_code == 409


async def test_announcement_notifies_members_with_cooldown(client, db_session, bot_token):
    cap_h, captain, [(a_h, a), (_b_h, b)] = await _club(client, db_session, bot_token, 890010)
    assert (await client.post("/api/v1/clubs/me/wall", headers=a_h, json={"text": "Слушайте все", "announce": True})).status_code == 403

    resp = await client.post("/api/v1/clubs/me/wall", headers=cap_h, json={"text": "Турнир в 20:00!", "announce": True})
    assert resp.status_code == 200
    assert resp.json()["posts"][0]["is_announcement"] is True
    assert resp.json()["announce_cooldown_seconds"] > 0
    notes = (await db_session.execute(select(Notification).where(
        Notification.type == NotificationType.club_announcement,
    ))).scalars().all()
    assert {n.user_id for n in notes} == {a.id, b.id}
    assert "Турнир в 20:00!" in notes[0].body

    again = await client.post("/api/v1/clubs/me/wall", headers=cap_h, json={"text": "Ещё раз", "announce": True})
    assert again.status_code == 409
    config = await get_config(db_session)
    config.club_announcement_cooldown_minutes = 0
    await db_session.commit()
    assert (await client.post("/api/v1/clubs/me/wall", headers=cap_h, json={"text": "Ещё раз", "announce": True})).status_code == 200


async def test_pinned_post_stays_on_top(client, db_session, bot_token):
    cap_h, _captain, [(a_h, _a), _] = await _club(client, db_session, bot_token, 890020)
    first = (await client.post("/api/v1/clubs/me/wall", headers=cap_h, json={"text": "Правила клуба"})).json()["posts"][0]
    await client.post("/api/v1/clubs/me/wall", headers=a_h, json={"text": "Привет"})
    assert (await client.post(f"/api/v1/clubs/me/wall/{first['id']}/pin", headers=a_h)).status_code == 403
    wall = (await client.post(f"/api/v1/clubs/me/wall/{first['id']}/pin", headers=cap_h)).json()
    assert wall["posts"][0]["id"] == first["id"] and wall["posts"][0]["is_pinned"] is True
