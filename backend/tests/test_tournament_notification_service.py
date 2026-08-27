from sqlalchemy import select

from app.models.club import ClubMember
from app.models.club_card_availability import ClubCardAvailability
from app.models.enums import Position
from app.models.notification import Notification
from app.services.tournament_notification_service import notify_club_members, send_lineup_reminders
from app.services.tournament_queue_service import apply_to_tournament
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _seed_position_pool(db_session):
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _create_club_with_full_squad(client, db_session, bot_token, telegram_id, name):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    captain = await get_user_by_telegram_id(db_session, telegram_id)

    create_resp = await client.post(
        "/api/v1/clubs", headers=telegram_headers(telegram_id, bot_token),
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert create_resp.status_code == 200

    resp2 = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id + 500000, bot_token))
    assert resp2.status_code == 200
    join_resp = await client.post(
        f"/api/v1/clubs/{create_resp.json()['id']}/join", headers=telegram_headers(telegram_id + 500000, bot_token)
    )
    assert join_resp.status_code == 200

    return create_resp.json()["id"], captain


async def test_notify_club_members_notifies_every_member(client, db_session, bot_token):
    await _seed_position_pool(db_session)
    club_id, captain = await _create_club_with_full_squad(client, db_session, bot_token, 850001, "Клуб уведомлений")

    from app.models.enums import NotificationType

    await notify_club_members(db_session, club_id, NotificationType.club_match, "Заголовок", "Текст")
    await db_session.commit()

    member_count = (
        await db_session.execute(select(ClubMember).where(ClubMember.club_id == club_id))
    ).scalars().all()
    notifications = (await db_session.execute(select(Notification).where(Notification.type == NotificationType.club_match))).scalars().all()
    assert len(notifications) == len(member_count) == 2


async def test_send_lineup_reminders_notifies_club_with_suspended_starter(client, db_session, bot_token):
    from app.models.club import Club

    await _seed_position_pool(db_session)
    club_ids_and_captains = []
    for i in range(8):
        await _create_club_with_full_squad(client, db_session, bot_token, 850100 + i * 2, f"Резерв {i}")
        club = (await db_session.execute(select(Club).where(Club.name == f"Резерв {i}"))).scalar_one()
        captain = await get_user_by_telegram_id(db_session, 850100 + i * 2)
        club_ids_and_captains.append((club, captain))

    tournament_id = None
    for club, captain in club_ids_and_captains:
        result = await apply_to_tournament(db_session, captain)
        if result.tournament_id is not None:
            tournament_id = result.tournament_id
    assert tournament_id is not None

    from app.models.club_lineup import ClubLineup, ClubLineupCard

    first_club = club_ids_and_captains[0][0]
    lineup = (await db_session.execute(select(ClubLineup).where(ClubLineup.club_id == first_club.id))).scalar_one()
    lineup_card = (await db_session.execute(select(ClubLineupCard).where(ClubLineupCard.club_lineup_id == lineup.id))).scalars().first()
    db_session.add(ClubCardAvailability(club_card_id=lineup_card.club_card_id, rounds_remaining=1))
    await db_session.commit()

    notified = await send_lineup_reminders(db_session)
    assert notified == 1

    from app.models.enums import NotificationType

    notifications = (
        await db_session.execute(select(Notification).where(Notification.type == NotificationType.club_lineup_reminder))
    ).scalars().all()
    assert len(notifications) == 2  # 2 members of the affected club


async def test_send_lineup_reminders_skips_clubs_with_no_suspension(client, db_session, bot_token):
    from app.models.club import Club

    await _seed_position_pool(db_session)
    tournament_id = None
    for i in range(8):
        await _create_club_with_full_squad(client, db_session, bot_token, 850200 + i * 2, f"Чистые {i}")
        captain = await get_user_by_telegram_id(db_session, 850200 + i * 2)
        result = await apply_to_tournament(db_session, captain)
        if result.tournament_id is not None:
            tournament_id = result.tournament_id
    assert tournament_id is not None

    notified = await send_lineup_reminders(db_session)
    assert notified == 0
