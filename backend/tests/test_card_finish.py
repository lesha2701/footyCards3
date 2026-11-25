"""«Редкие версии»: a pack card may come out gold / autographed / night."""
from unittest.mock import patch

from app.models.enums import CardSource, Rarity
from app.services import card_finish_service
from app.services.card_creation import create_user_card
from app.services.card_finish_service import pick_finish
from app.models.user import User
from tests.factories import create_player


def test_pick_finish_stacks_the_chances_rarest_first():
    # autograph 5‰, night 10‰, gold 20‰
    assert pick_finish(0.004, 20, 5, 10) == "autograph"
    assert pick_finish(0.010, 20, 5, 10) == "night"
    assert pick_finish(0.030, 20, 5, 10) == "gold"
    assert pick_finish(0.040, 20, 5, 10) is None
    assert pick_finish(0.0, 0, 0, 0) is None


async def test_only_pack_cards_roll_a_finish(db_session):
    user = User(telegram_id=750099, first_name="T")
    db_session.add(user)
    await db_session.flush()
    player = await create_player(db_session, rarity=Rarity.rare)
    with patch.object(card_finish_service.random, "random", return_value=0.0):
        from_pack = await create_user_card(db_session, user.id, player.id, CardSource.pack)
        from_trade = await create_user_card(db_session, user.id, player.id, CardSource.admin_grant)
    assert from_pack.finish == "autograph"
    assert from_trade.finish is None
    with patch.object(card_finish_service.random, "random", return_value=0.99):
        plain = await create_user_card(db_session, user.id, player.id, CardSource.pack)
    assert plain.finish is None


async def test_a_finished_copy_is_listed_on_its_own(client, db_session, bot_token):
    from tests.factories import get_user_by_telegram_id
    from tests.utils import telegram_headers

    headers = telegram_headers(750001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750001)
    player = await create_player(db_session, rarity=Rarity.epic)
    plain = await create_user_card(db_session, user.id, player.id, CardSource.admin_grant)
    gold = await create_user_card(db_session, user.id, player.id, CardSource.admin_grant)
    gold.finish = "gold"
    await db_session.commit()
    items = (await client.get("/api/v1/collection/cards", headers=headers)).json()["items"]
    mine = sorted((i["id"], i["finish"]) for i in items if i["player"]["id"] == player.id)
    assert mine == sorted([(plain.id, None), (gold.id, "gold")])
