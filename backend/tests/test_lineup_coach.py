from app.models.coach import Coach, CoachBoost
from app.models.enums import CardSource, CoachBoostType, Rarity
from app.models.user_coach_card import UserCoachCard
from app.schemas.lineup import LineupCoachSetRequest, LineupSetRequest, LineupSlotIn
from app.services.card_creation import create_user_card
from app.services.coach_boost_service import arena_rarity_team_strength_bonus
from app.services.lineup_service import FORMATION_SLOTS, set_lineup, set_lineup_coach
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _build_full_squad(db_session, user_id: int) -> list[LineupSlotIn]:
    slots = []
    for slot in FORMATION_SLOTS:
        player = await create_player(db_session, rating=80, position=slot.ideal_position)
        card = await create_user_card(db_session, user_id, player.id, CardSource.seed)
        await db_session.commit()
        slots.append(LineupSlotIn(slot_code=slot.code, user_card_id=card.id))
    return slots


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

    slots = await _build_full_squad(db_session, user.id)
    baseline = await set_lineup(db_session, user, LineupSetRequest(slots=slots))
    assert baseline.is_complete is True
    assert baseline.team_strength is not None
    baseline_strength = baseline.team_strength

    result = await set_lineup_coach(db_session, user, LineupCoachSetRequest(user_coach_card_id=card.id))
    assert result.coach is not None
    assert result.coach.display_name == "Arena Equip Test Coach"
    # Epic coach -> arena_rarity_team_strength_bonus(epic) == 6; team_strength
    # must go up by exactly that, not some other amount from a stale/wrong
    # mapping or a bonus applied twice.
    expected_bonus = arena_rarity_team_strength_bonus(coach)
    assert expected_bonus == 6
    assert result.team_strength == baseline_strength + expected_bonus

    cleared = await set_lineup_coach(db_session, user, LineupCoachSetRequest(user_coach_card_id=None))
    assert cleared.coach is None
    assert cleared.team_strength == baseline_strength


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


async def test_list_user_coach_cards_returns_owned_coaches_with_boosts(client, db_session, bot_token):
    headers = telegram_headers(840203, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    coach = Coach(display_name="List Test Coach", rarity=Rarity.legendary)
    coach.boosts = [
        CoachBoost(boost_type=CoachBoostType.ATTACK_CENTRAL, magnitude=8.0),
        CoachBoost(boost_type=CoachBoostType.DEFENCE_CENTRAL, magnitude=8.0),
        CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=8.0),
    ]
    db_session.add(coach)
    await db_session.flush()
    user = await get_user_by_telegram_id(db_session, 840203)
    db_session.add(UserCoachCard(user_id=user.id, coach_id=coach.id, serial_number=1, source="pack"))
    await db_session.commit()

    resp = await client.get("/api/v1/lineups/coach-cards", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert len(body[0]["coach"]["boosts"]) == 3
