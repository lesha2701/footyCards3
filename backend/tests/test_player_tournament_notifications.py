from sqlalchemy import select

from app.config import get_settings
from app.models.enums import NotificationType
from app.models.notification import Notification
from app.models.personal_squad import PersonalSquad, PersonalSquadCard
from app.services.player_tournament_notification_service import send_lineup_reminders
from app.services.player_tournament_queue_service import apply_to_tournament
from tests.player_tournament_helpers import make_ready_user

INTERNAL_HEADERS = {"X-Internal-Secret": get_settings().internal_api_secret}


async def _tournament(client, db_session, bot_token, base):
    users = [await make_ready_user(client, db_session, bot_token, base + i) for i in range(16)]
    for u in users:
        await apply_to_tournament(db_session, u)
    return users


async def _empty_squads(db_session, user_id):
    squad_ids = (await db_session.execute(select(PersonalSquad.id).where(PersonalSquad.user_id == user_id))).scalars().all()
    for row in (await db_session.execute(select(PersonalSquadCard).where(PersonalSquadCard.squad_id.in_(squad_ids)))).scalars().all():
        await db_session.delete(row)
    await db_session.commit()


async def test_reminds_only_players_with_incomplete_squad(client, db_session, bot_token):
    users = await _tournament(client, db_session, bot_token, 870000)
    first_id = users[0].id
    await _empty_squads(db_session, first_id)

    count = await send_lineup_reminders(db_session, slot_key="2026-09-25T10:00")
    assert count == 1
    rows = (await db_session.execute(
        select(Notification).where(Notification.type == NotificationType.player_tournament_reminder)
    )).scalars().all()
    assert [n.user_id for n in rows] == [first_id]


async def test_reminder_slot_key_is_idempotent(client, db_session, bot_token):
    users = await _tournament(client, db_session, bot_token, 871000)
    await _empty_squads(db_session, users[0].id)
    assert await send_lineup_reminders(db_session, slot_key="2026-09-25T15:00") == 1
    assert await send_lineup_reminders(db_session, slot_key="2026-09-25T15:00") == 0


async def test_internal_endpoints_require_secret_and_return_shape(client, db_session, bot_token):
    await _tournament(client, db_session, bot_token, 872000)
    for path in ("lineup-reminders", "simulate-round"):
        url = f"/api/v1/internal/player-tournaments/{path}?slot_key=2026-09-25T20:00"
        assert (await client.post(url)).status_code == 401
        assert (await client.post(url, headers={"X-Internal-Secret": "wrong"})).status_code == 401

    resp = await client.post(
        "/api/v1/internal/player-tournaments/lineup-reminders?slot_key=2026-09-25T20:00", headers=INTERNAL_HEADERS
    )
    assert resp.status_code == 200
    assert isinstance(resp.json()["users_notified"], int)

    resp = await client.post(
        "/api/v1/internal/player-tournaments/simulate-round?slot_key=2026-09-25T20:00", headers=INTERNAL_HEADERS
    )
    assert resp.status_code == 200
    assert isinstance(resp.json()["matches_simulated"], int)
