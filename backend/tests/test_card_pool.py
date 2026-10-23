from app.models.enums import CardSource
from app.services.card_pool_service import load_top_copies
from app.services.card_creation import create_user_card
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def test_top_copies_keep_the_strongest_and_the_included(client, db_session, bot_token):
    await client.post("/api/v1/auth/session", headers=telegram_headers(970001, bot_token))
    user = await get_user_by_telegram_id(db_session, 970001)
    many = await create_player(db_session, rating=80)
    other = await create_player(db_session, rating=70)
    copies = [await create_user_card(db_session, user.id, many.id, CardSource.seed) for _ in range(6)]
    copies[4].star_rating_bonus = 3  # the strongest copy
    lone = await create_user_card(db_session, user.id, other.id, CardSource.seed)
    await db_session.commit()

    ids = {c.id for c in await load_top_copies(db_session, user.id, per_player=2)}
    assert len(ids) == 3 and copies[4].id in ids and lone.id in ids

    ids = {c.id for c in await load_top_copies(db_session, user.id, per_player=1, include=[copies[5].id])}
    assert ids == {copies[4].id, copies[5].id, lone.id}

    copies[4].is_locked_by_admin = True
    await db_session.commit()
    ids = {c.id for c in await load_top_copies(db_session, user.id, per_player=1, unlocked_only=True)}
    assert copies[4].id not in ids and len(ids) == 2
