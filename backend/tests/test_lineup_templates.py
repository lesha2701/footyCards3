from app.models.card import UserCard
from app.models.enums import CardSource
from app.schemas.lineup import LineupSetRequest, LineupSlotIn
from app.services.card_creation import create_user_card
from app.services.lineup_service import (
    FORMATION_SLOTS, TEMPLATE_COUNT, activate_template, get_active_lineup, list_templates, rename_template, set_lineup,
)
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


async def test_five_templates_lazily_created_on_first_read(client, db_session, bot_token):
    headers = telegram_headers(850001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 850001)

    templates = await list_templates(db_session, user)
    assert len(templates) == TEMPLATE_COUNT
    assert [t.template_index for t in templates] == [1, 2, 3, 4, 5]
    assert [t.is_active for t in templates] == [True, False, False, False, False]
    assert templates[1].name == "Шаблон 2"


async def test_editing_inactive_template_does_not_lock_cards(client, db_session, bot_token):
    headers = telegram_headers(850002, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 850002)

    slots = await _build_full_squad(db_session, user.id)
    await set_lineup(db_session, user, LineupSetRequest(slots=slots), template_index=2)

    for slot in slots:
        card = await db_session.get(UserCard, slot.user_card_id)
        assert card.is_in_lineup is False


async def test_editing_active_template_locks_cards(client, db_session, bot_token):
    headers = telegram_headers(850003, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 850003)

    slots = await _build_full_squad(db_session, user.id)
    await set_lineup(db_session, user, LineupSetRequest(slots=slots))  # template_index=None -> active (1)

    for slot in slots:
        card = await db_session.get(UserCard, slot.user_card_id)
        assert card.is_in_lineup is True


async def test_same_card_can_be_saved_into_two_templates(client, db_session, bot_token):
    headers = telegram_headers(850004, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 850004)

    slots = await _build_full_squad(db_session, user.id)
    await set_lineup(db_session, user, LineupSetRequest(slots=slots), template_index=1)
    result = await set_lineup(db_session, user, LineupSetRequest(slots=slots), template_index=2)
    assert result.is_complete is True


async def test_activate_template_moves_lock_to_new_cards_only(client, db_session, bot_token):
    headers = telegram_headers(850005, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 850005)

    slots_1 = await _build_full_squad(db_session, user.id)
    await set_lineup(db_session, user, LineupSetRequest(slots=slots_1), template_index=1)

    slots_2 = await _build_full_squad(db_session, user.id)
    await set_lineup(db_session, user, LineupSetRequest(slots=slots_2), template_index=2)

    await activate_template(db_session, user, 2)

    for slot in slots_1:
        card = await db_session.get(UserCard, slot.user_card_id)
        assert card.is_in_lineup is False
    for slot in slots_2:
        card = await db_session.get(UserCard, slot.user_card_id)
        assert card.is_in_lineup is True


async def test_activate_template_can_switch_back_to_a_lower_index(client, db_session, bot_token):
    """Regression test: activating a lower-index template while a
    higher-index one is active previously raised UniqueViolationError on
    uq_lineup_one_active_per_user — SQLAlchemy doesn't guarantee the two
    is_active UPDATEs in one flush execute in db.add() order, so clearing
    the old row and setting the new one active could land in the wrong
    order and collide with the partial unique index mid-transaction."""
    headers = telegram_headers(850009, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 850009)

    await activate_template(db_session, user, 3)
    result = await activate_template(db_session, user, 1)
    assert result.template_index == 1
    assert result.is_active is True


async def test_activate_template_keeps_shared_card_locked_throughout(client, db_session, bot_token):
    headers = telegram_headers(850006, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 850006)

    slots_1 = await _build_full_squad(db_session, user.id)
    await set_lineup(db_session, user, LineupSetRequest(slots=slots_1), template_index=1)

    # Template 2 reuses slots_1's goalkeeper (shared card) plus a fresh XI
    # for the rest.
    slots_2 = await _build_full_squad(db_session, user.id)
    slots_2[0] = slots_1[0]
    await set_lineup(db_session, user, LineupSetRequest(slots=slots_2), template_index=2)

    await activate_template(db_session, user, 2)

    shared_card = await db_session.get(UserCard, slots_1[0].user_card_id)
    assert shared_card.is_in_lineup is True


async def test_rename_template(client, db_session, bot_token):
    headers = telegram_headers(850007, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 850007)

    result = await rename_template(db_session, user, 3, "Оборонительный")
    assert result.name == "Оборонительный"
    templates = await list_templates(db_session, user)
    assert templates[2].name == "Оборонительный"


async def test_get_active_lineup_with_no_args_still_returns_active_template(client, db_session, bot_token):
    headers = telegram_headers(850008, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 850008)

    await activate_template(db_session, user, 3)
    result = await get_active_lineup(db_session, user)
    assert result.template_index == 3
    assert result.is_active is True
