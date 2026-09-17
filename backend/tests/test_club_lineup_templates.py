from app.models.enums import Position
from app.schemas.club_squad import ClubLineupSetRequest
from app.services.club_squad_service import (
    CLUB_TEMPLATE_COUNT, activate_club_lineup_template, get_club_lineup, list_club_lineup_templates,
    rename_club_lineup_template, set_club_lineup,
)
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


async def _register_only(client, bot_token, telegram_id):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200


async def _create_club(client, bot_token, telegram_id, name):
    await _register_only(client, bot_token, telegram_id)
    headers = telegram_headers(telegram_id, bot_token)
    resp = await client.post(
        "/api/v1/clubs", headers=headers,
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 200
    return resp.json(), headers


async def test_five_club_lineup_templates_lazily_created(client, db_session, bot_token):
    await _seed_position_pool(db_session)
    club, headers = await _create_club(client, bot_token, 870001, "Клуб шаблонов")
    user = await get_user_by_telegram_id(db_session, 870001)

    templates = await list_club_lineup_templates(db_session, user)
    assert len(templates) == CLUB_TEMPLATE_COUNT
    assert [t.template_index for t in templates] == [1, 2, 3, 4, 5]
    assert [t.is_active for t in templates] == [True, False, False, False, False]
    # seed_starting_squad already filled template 1 with a complete XI.
    assert templates[0].is_complete is True
    assert templates[1].name == "Шаблон 2"
    assert templates[1].is_complete is False


async def test_rename_club_lineup_template(client, db_session, bot_token):
    await _seed_position_pool(db_session)
    club, headers = await _create_club(client, bot_token, 870002, "Клуб переименований")
    user = await get_user_by_telegram_id(db_session, 870002)

    result = await rename_club_lineup_template(db_session, user, 2, "Оборонительный")
    assert result.name == "Оборонительный"
    templates = await list_club_lineup_templates(db_session, user)
    assert templates[1].name == "Оборонительный"


async def test_activate_club_lineup_template_swaps_active_flag(client, db_session, bot_token):
    await _seed_position_pool(db_session)
    club, headers = await _create_club(client, bot_token, 870003, "Клуб переключений")
    user = await get_user_by_telegram_id(db_session, 870003)

    result = await activate_club_lineup_template(db_session, user, 3)
    assert result.template_index == 3
    assert result.is_active is True

    templates = await list_club_lineup_templates(db_session, user)
    assert templates[0].is_active is False  # template 1, previously active
    assert templates[2].is_active is True   # template 3, now active


async def test_activate_club_lineup_template_can_switch_back_to_a_lower_index(client, db_session, bot_token):
    """Regression test — see lineup_service's identical test docstring for
    why this specific direction matters (SQLAlchemy's UPDATE batching
    order vs. the partial unique index)."""
    await _seed_position_pool(db_session)
    club, headers = await _create_club(client, bot_token, 870006, "Клуб обратного переключения")
    user = await get_user_by_telegram_id(db_session, 870006)

    await activate_club_lineup_template(db_session, user, 3)
    result = await activate_club_lineup_template(db_session, user, 1)
    assert result.template_index == 1
    assert result.is_active is True


async def test_editing_non_active_template_does_not_disturb_active_one(client, db_session, bot_token):
    await _seed_position_pool(db_session)
    club, headers = await _create_club(client, bot_token, 870004, "Клуб независимых шаблонов")
    user = await get_user_by_telegram_id(db_session, 870004)

    before = await get_club_lineup(db_session, user)  # active = template 1, complete
    assert before.is_complete is True

    # Editing template 2 (no cards assigned) must not touch template 1's
    # own completeness/content.
    result = await set_club_lineup(db_session, user, ClubLineupSetRequest(slots=[]), template_index=2)
    assert result.template_index == 2
    assert result.is_complete is False

    after = await get_club_lineup(db_session, user)
    assert after.template_index == 1
    assert after.is_complete is True


async def test_get_club_lineup_with_no_args_returns_active_template(client, db_session, bot_token):
    await _seed_position_pool(db_session)
    club, headers = await _create_club(client, bot_token, 870005, "Клуб дефолта")
    user = await get_user_by_telegram_id(db_session, 870005)

    await activate_club_lineup_template(db_session, user, 4)
    result = await get_club_lineup(db_session, user)
    assert result.template_index == 4
    assert result.is_active is True
