from app.models.coach import Coach, CoachBoost
from app.models.enums import CoachBoostType, Rarity
from app.models.user_coach_card import UserCoachCard
from app.schemas.lineup import LineupCoachSetRequest
from app.services.lineup_service import set_lineup_coach
from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers


async def test_captain_can_equip_and_clear_personal_coach(client, db_session, bot_token):
    headers = telegram_headers(840200, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 840200)

    coach = Coach(display_name="Arena Equip Test Coach", rarity=Rarity.epic)
    coach.boosts = [
        CoachBoost(boost_type=CoachBoostType.ATTACK_CENTRAL, magnitude=4.0),
        CoachBoost(boost_type=CoachBoostType.DEFENCE_CENTRAL, magnitude=4.0),
    ]
    db_session.add(coach)
    await db_session.flush()
    card = UserCoachCard(user_id=user.id, coach_id=coach.id, serial_number=1, source="pack")
    db_session.add(card)
    await db_session.commit()

    result = await set_lineup_coach(db_session, user, LineupCoachSetRequest(user_coach_card_id=card.id))
    assert result.coach is not None
    assert result.coach.display_name == "Arena Equip Test Coach"

    cleared = await set_lineup_coach(db_session, user, LineupCoachSetRequest(user_coach_card_id=None))
    assert cleared.coach is None


async def test_cannot_equip_another_users_coach_card(client, db_session, bot_token):
    import pytest

    from app.core.exceptions import ConflictError

    headers = telegram_headers(840201, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 840201)

    other_headers = telegram_headers(840202, bot_token)
    await client.post("/api/v1/auth/session", headers=other_headers)
    other_user = await get_user_by_telegram_id(db_session, 840202)

    coach = Coach(display_name="Foreign Personal Coach", rarity=Rarity.common)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=2.0)]
    db_session.add(coach)
    await db_session.flush()
    foreign_card = UserCoachCard(user_id=other_user.id, coach_id=coach.id, serial_number=1, source="pack")
    db_session.add(foreign_card)
    await db_session.commit()

    with pytest.raises(ConflictError):
        await set_lineup_coach(db_session, user, LineupCoachSetRequest(user_coach_card_id=foreign_card.id))
