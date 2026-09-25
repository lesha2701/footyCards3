from app.models.card import UserCard
from app.models.enums import CardSource
from app.services.club_formation_service import get_formation_slots
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def make_user(client, db_session, bot_token, telegram_id):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def give_cards_for_formation(db_session, user, formation="4-3-3", rating=70):
    """Creates one UserCard per slot of `formation`, returns [(slot, card)]."""
    pairs = []
    for slot in get_formation_slots(formation):
        player = await create_player(db_session, position=slot.ideal_position, rating=rating)
        card = UserCard(owner_id=user.id, player_id=player.id, source=CardSource.seed)
        db_session.add(card)
        pairs.append((slot, card))
    await db_session.commit()
    for _slot, card in pairs:
        await db_session.refresh(card)
    return pairs


async def make_ready_user(client, db_session, bot_token, telegram_id, rating=70):
    """User with a complete 11/11 active squad (4-3-3)."""
    # Imported lazily: these modules are created in a later task.
    from app.schemas.personal_squad import PersonalSquadSetRequest, PersonalSquadSlotIn
    from app.services import personal_squad_service

    user = await make_user(client, db_session, bot_token, telegram_id)
    pairs = await give_cards_for_formation(db_session, user, rating=rating)
    await personal_squad_service.set_squad_cards(
        db_session, user,
        PersonalSquadSetRequest(slots=[PersonalSquadSlotIn(slot_code=s.code, user_card_id=c.id) for s, c in pairs]),
    )
    return user
