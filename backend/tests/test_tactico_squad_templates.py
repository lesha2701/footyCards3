from app.models.card import UserCard
from app.models.enums import CardSource
from app.services.card_creation import create_user_card
from app.services.tactico_service import (
    SQUAD_TEMPLATE_COUNT, activate_squad_template, get_squad, list_squad_templates, rename_squad_template, set_squad,
)
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _build_squad_cards(db_session, user_id: int, count: int = 11) -> list[int]:
    ids = []
    for _ in range(count):
        player = await create_player(db_session)
        card = await create_user_card(db_session, user_id, player.id, CardSource.seed)
        await db_session.commit()
        ids.append(card.id)
    return ids


async def test_five_squad_templates_lazily_created(client, db_session, bot_token):
    headers = telegram_headers(860001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 860001)

    templates = await list_squad_templates(db_session, user)
    assert len(templates) == SQUAD_TEMPLATE_COUNT
    assert [t.template_index for t in templates] == [1, 2, 3, 4, 5]
    assert [t.is_active for t in templates] == [True, False, False, False, False]
    assert templates[1].name == "Шаблон 2"


async def test_editing_inactive_squad_template_does_not_lock_cards(client, db_session, bot_token):
    headers = telegram_headers(860002, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 860002)

    card_ids = await _build_squad_cards(db_session, user.id)
    await set_squad(db_session, user, card_ids, template_index=2)

    for card_id in card_ids:
        card = await db_session.get(UserCard, card_id)
        assert card.is_in_tactico_squad is False


async def test_editing_active_squad_template_locks_cards(client, db_session, bot_token):
    headers = telegram_headers(860003, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 860003)

    card_ids = await _build_squad_cards(db_session, user.id)
    await set_squad(db_session, user, card_ids)  # template_index=None -> active (1)

    for card_id in card_ids:
        card = await db_session.get(UserCard, card_id)
        assert card.is_in_tactico_squad is True


async def test_same_card_can_be_saved_into_two_squad_templates(client, db_session, bot_token):
    headers = telegram_headers(860004, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 860004)

    card_ids = await _build_squad_cards(db_session, user.id)
    await set_squad(db_session, user, card_ids, template_index=1)
    result = await set_squad(db_session, user, card_ids, template_index=2)
    assert result.is_complete is True


async def test_activate_squad_template_moves_lock_to_new_cards_only(client, db_session, bot_token):
    headers = telegram_headers(860005, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 860005)

    ids_1 = await _build_squad_cards(db_session, user.id)
    await set_squad(db_session, user, ids_1, template_index=1)
    ids_2 = await _build_squad_cards(db_session, user.id)
    await set_squad(db_session, user, ids_2, template_index=2)

    await activate_squad_template(db_session, user, 2)

    for card_id in ids_1:
        card = await db_session.get(UserCard, card_id)
        assert card.is_in_tactico_squad is False
    for card_id in ids_2:
        card = await db_session.get(UserCard, card_id)
        assert card.is_in_tactico_squad is True


async def test_activate_squad_template_can_switch_back_to_a_lower_index(client, db_session, bot_token):
    """Regression test — see lineup_service's identical test docstring for
    why this specific direction matters (SQLAlchemy's UPDATE batching
    order vs. the partial unique index)."""
    headers = telegram_headers(860009, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 860009)

    await activate_squad_template(db_session, user, 3)
    result = await activate_squad_template(db_session, user, 1)
    assert result.template_index == 1
    assert result.is_active is True


async def test_activate_squad_template_keeps_shared_card_locked(client, db_session, bot_token):
    headers = telegram_headers(860006, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 860006)

    ids_1 = await _build_squad_cards(db_session, user.id)
    await set_squad(db_session, user, ids_1, template_index=1)
    ids_2 = await _build_squad_cards(db_session, user.id, count=10) + [ids_1[0]]
    await set_squad(db_session, user, ids_2, template_index=2)

    await activate_squad_template(db_session, user, 2)

    shared = await db_session.get(UserCard, ids_1[0])
    assert shared.is_in_tactico_squad is True


async def test_rename_squad_template(client, db_session, bot_token):
    headers = telegram_headers(860007, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 860007)

    result = await rename_squad_template(db_session, user, 3, "Резерв")
    assert result.name == "Резерв"
    templates = await list_squad_templates(db_session, user)
    assert templates[2].name == "Резерв"


async def test_get_squad_with_no_args_returns_active_template(client, db_session, bot_token):
    headers = telegram_headers(860008, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 860008)

    await activate_squad_template(db_session, user, 4)
    result = await get_squad(db_session, user)
    assert result.template_index == 4
    assert result.is_active is True
