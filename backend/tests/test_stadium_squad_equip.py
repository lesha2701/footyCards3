from app.models.enums import CardSource, Rarity
from app.models.stadium import Stadium
from app.models.user_stadium_card import UserStadiumCard
from app.schemas.lineup import LineupSetRequest, LineupSlotIn, LineupStadiumSetRequest
from app.services.card_creation import create_user_card
from app.services.lineup_service import FORMATION_SLOTS, calculate_base_strength, set_lineup, set_lineup_stadium
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


async def test_equip_stadium_on_lineup_boosts_team_strength(client, db_session, bot_token):
    headers = telegram_headers(840300, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 840300)

    stadium = Stadium(display_name="Arena Equip Test Stadium", rarity=Rarity.epic, boost_pct=0.05)
    db_session.add(stadium)
    await db_session.flush()
    card = UserStadiumCard(user_id=user.id, stadium_id=stadium.id, serial_number=1, source=CardSource.pack)
    db_session.add(card)
    await db_session.commit()

    slots = await _build_full_squad(db_session, user.id)
    baseline = await set_lineup(db_session, user, LineupSetRequest(slots=slots))
    assert baseline.is_complete is True
    assert baseline.team_strength is not None
    baseline_strength = baseline.team_strength

    result = await set_lineup_stadium(db_session, user, LineupStadiumSetRequest(user_stadium_card_id=card.id))
    assert result.stadium is not None
    assert result.stadium.display_name == "Arena Equip Test Stadium"
    assert result.stadium.boost_pct == 0.05

    # calculate_base_strength with vs. without the stadium's stadium_multiplier
    # must produce a higher number for the same cards (rounding may make the
    # +5% delta on the *displayed* team_strength collapse to 0 for some card
    # sets, so the direct calculate_base_strength comparison below is the
    # real assertion; the >= check on the served team_strength is a sanity
    # check that equipping never makes it go down).
    assert result.team_strength >= baseline_strength

    cleared = await set_lineup_stadium(db_session, user, LineupStadiumSetRequest(user_stadium_card_id=None))
    assert cleared.stadium is None
    assert cleared.team_strength == baseline_strength


async def test_calculate_base_strength_stadium_multiplier_increases_strength(client, db_session, bot_token):
    headers = telegram_headers(840301, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 840301)

    player = await create_player(db_session, rating=80, position=FORMATION_SLOTS[0].ideal_position)
    card = await create_user_card(db_session, user.id, player.id, CardSource.seed)
    await db_session.commit()

    cards_with_slots = [(card, FORMATION_SLOTS[0])]
    without_stadium = calculate_base_strength(cards_with_slots)
    with_stadium = calculate_base_strength(cards_with_slots, stadium_multiplier=1.05)
    assert with_stadium > without_stadium


async def test_cannot_equip_another_users_stadium_card(client, db_session, bot_token):
    import pytest

    from app.core.exceptions import ConflictError

    headers = telegram_headers(840302, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 840302)

    other_headers = telegram_headers(840303, bot_token)
    await client.post("/api/v1/auth/session", headers=other_headers)
    other_user = await get_user_by_telegram_id(db_session, 840303)

    stadium = Stadium(display_name="Foreign Personal Stadium", rarity=Rarity.common, boost_pct=0.02)
    db_session.add(stadium)
    await db_session.flush()
    foreign_card = UserStadiumCard(user_id=other_user.id, stadium_id=stadium.id, serial_number=1, source=CardSource.pack)
    db_session.add(foreign_card)
    await db_session.commit()

    with pytest.raises(ConflictError):
        await set_lineup_stadium(db_session, user, LineupStadiumSetRequest(user_stadium_card_id=foreign_card.id))


async def test_list_user_stadium_cards_returns_owned_stadiums(client, db_session, bot_token):
    from app.services.lineup_service import list_user_stadium_cards

    headers = telegram_headers(840304, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    stadium = Stadium(display_name="List Test Stadium", rarity=Rarity.legendary, boost_pct=0.1)
    db_session.add(stadium)
    await db_session.flush()
    user = await get_user_by_telegram_id(db_session, 840304)
    db_session.add(UserStadiumCard(user_id=user.id, stadium_id=stadium.id, serial_number=1, source=CardSource.pack))
    await db_session.commit()

    resp = await client.get("/api/v1/lineups/stadium-cards", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["stadium"]["display_name"] == "List Test Stadium"
