from datetime import datetime, timedelta, timezone
from itertools import count

from sqlalchemy import func, select

from app.models.badge import Badge, UserBadge
from app.models.notification import Notification
from app.models.stars_patron import StarsPatronAward
from app.models.stars_payment_receipt import StarsPaymentReceipt
from app.models.trophy import TrophyDefinition, UserTrophy
from app.models.user import User
from app.services import stars_patron_service
from app.services.game_config_service import get_config
from tests.utils import telegram_headers

_charge = count(1)


async def _user(db, telegram_id: int) -> User:
    user = User(telegram_id=telegram_id, first_name=f"U{telegram_id}", balance=0)
    db.add(user)
    await db.commit()
    return user


async def _paid(db, user: User, stars: int, days_ago: int = 7) -> None:
    n = next(_charge)
    db.add(StarsPaymentReceipt(
        telegram_payment_charge_id=f"charge-{n}", payload_token=f"tok-{n}", telegram_user_id=user.telegram_id,
        total_amount=stars, status="delivered", delivered_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    ))
    await db.commit()


async def _setup(db) -> Badge:
    badge = Badge(name="Преторианец", icon="🛡️")
    db.add(badge)
    db.add_all([
        TrophyDefinition(code=stars_patron_service.WEEK_TROPHY, name="Покровитель недели", icon="👑"),
        TrophyDefinition(code=stars_patron_service.PRAETORIAN_TROPHY, name="Преторианец", icon="🛡️"),
    ])
    await db.commit()
    config = await get_config(db)
    config.stars_praetorian_badge_id = badge.id
    config.stars_patron_week_min = 100
    config.stars_patron_week_coins = 700
    config.stars_patron_week_card_rarity = ""
    await db.commit()
    return badge


async def _trophies(db, user_id: int, code: str) -> int:
    return (await db.execute(
        select(func.count()).select_from(UserTrophy).join(TrophyDefinition)
        .where(UserTrophy.user_id == user_id, TrophyDefinition.code == code)
    )).scalar_one()


async def _notes(db, user_id: int) -> list[Notification]:
    return list((await db.execute(select(Notification).where(Notification.user_id == user_id))).scalars().all())


async def test_week_top_buyers_are_thanked_once(db_session):
    await _setup(db_session)
    top, second, small, this_week = [await _user(db_session, t) for t in (81001, 81002, 81003, 81004)]
    await _paid(db_session, top, 500)
    await _paid(db_session, top, 300)
    await _paid(db_session, second, 400)
    await _paid(db_session, small, 50)
    await _paid(db_session, this_week, 5000, days_ago=0)

    assert await stars_patron_service.settle_last_week(db_session) is True
    assert await _trophies(db_session, top.id, stars_patron_service.WEEK_TROPHY) == 1
    await db_session.refresh(second)
    assert second.balance == 700
    assert "Покровитель недели" in (await _notes(db_session, top.id))[0].title
    assert len(await _notes(db_session, second.id)) == 1
    assert await _notes(db_session, small.id) == [] and await _notes(db_session, this_week.id) == []

    assert await stars_patron_service.settle_last_week(db_session) is False
    assert await _trophies(db_session, top.id, stars_patron_service.WEEK_TROPHY) == 1
    places = (await db_session.execute(select(StarsPatronAward.place).order_by(StarsPatronAward.place))).scalars().all()
    assert places == [0, 1, 2]


async def test_quiet_week_is_settled_once_with_a_marker(db_session):
    await _setup(db_session)
    assert await stars_patron_service.settle_last_week(db_session) is True
    assert await stars_patron_service.settle_last_week(db_session) is False
    rows = (await db_session.execute(select(StarsPatronAward))).scalars().all()
    assert [(r.place, r.user_id) for r in rows] == [(0, None)]


async def test_praetorian_at_the_bar_once_and_worn(db_session):
    badge = await _setup(db_session)
    user = await _user(db_session, 81010)
    await _paid(db_session, user, 6000, days_ago=40)
    assert await stars_patron_service.check_praetorian(db_session, user.id) is False

    await _paid(db_session, user, 4000, days_ago=1)
    assert await stars_patron_service.check_praetorian(db_session, user.id) is True
    await db_session.refresh(user)
    assert user.active_badge_id == badge.id
    assert await _trophies(db_session, user.id, stars_patron_service.PRAETORIAN_TROPHY) == 1
    assert "Преторианец" in (await _notes(db_session, user.id))[0].title

    user_id = user.id
    assert await stars_patron_service.check_praetorian(db_session, user_id) is False
    owned = (await db_session.execute(select(func.count()).select_from(UserBadge).where(UserBadge.user_id == user_id))).scalar_one()
    assert owned == 1


async def test_earlier_big_buyer_gets_it_on_the_daily_login(client, db_session, bot_token):
    await _setup(db_session)
    headers = telegram_headers(81020, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = (await db_session.execute(select(User).where(User.telegram_id == 81020))).scalar_one()
    await _paid(db_session, user, 12000, days_ago=90)
    user.last_seen_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()

    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    assert await _trophies(db_session, user.id, stars_patron_service.PRAETORIAN_TROPHY) == 1


async def test_letter_shows_in_the_game_once(client, db_session, bot_token):
    await _setup(db_session)
    headers = telegram_headers(81030, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = (await db_session.execute(select(User).where(User.telegram_id == 81030))).scalar_one()
    await _paid(db_session, user, 10000, days_ago=40)
    await stars_patron_service.check_praetorian(db_session, user.id)

    letters = (await client.get("/api/v1/stars-patron/letters", headers=headers)).json()
    assert len(letters) == 1 and "Преторианец" in letters[0]["title"]
    assert (await client.post(f"/api/v1/stars-patron/letters/{letters[0]['id']}/seen", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/stars-patron/letters", headers=headers)).json() == []
    other = telegram_headers(81031, bot_token)
    await client.post("/api/v1/auth/session", headers=other)
    assert (await client.post(f"/api/v1/stars-patron/letters/{letters[0]['id']}/seen", headers=other)).status_code == 404
