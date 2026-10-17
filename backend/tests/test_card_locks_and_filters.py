"""The owner's «замок» on cards, squad copies in the Forge / diamond feeding,
and the saved default card filter."""
from sqlalchemy import select

from app.models.card import UserCard
from app.models.card_upgrade import CardUpgradeRule
from app.models.diamond_upgrade import DiamondUpgradeTier
from app.models.enums import CardSource, Rarity
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1/collection"


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def _give(db_session, owner_id, player_id, serial, **flags) -> UserCard:
    card = UserCard(owner_id=owner_id, player_id=player_id, source=CardSource.seed, serial_number=serial, **flags)
    db_session.add(card)
    await db_session.commit()
    await db_session.refresh(card)
    return card


async def _card(db_session, card_id):
    return (
        await db_session.execute(
            select(UserCard).where(UserCard.id == card_id).execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def test_lock_protects_from_every_kind_of_sale(client, db_session, bot_token):
    user = await _register(client, db_session, 880001, bot_token)
    player = await create_player(db_session, rarity=Rarity.common)
    keep = await _give(db_session, user.id, player.id, 1)
    spare = await _give(db_session, user.id, player.id, 2)
    headers = telegram_headers(880001, bot_token)

    resp = await client.patch(f"{API}/cards/lock", headers=headers, json={"card_ids": [keep.id, spare.id], "locked": True})
    assert resp.status_code == 200 and resp.json() == {"card_ids": [keep.id, spare.id], "locked": True}

    one = await client.post(f"{API}/cards/sell", headers=headers, json={"user_card_id": spare.id})
    assert one.status_code == 409 and one.json()["error"]["details"]["reason"] == "user_locked"
    bulk = await client.post(f"{API}/cards/bulk-sell", headers=headers, json={"user_card_ids": [spare.id]})
    assert bulk.status_code == 409
    dupes = await client.post(f"{API}/cards/sell-duplicates", headers=headers, json={"preview": True})
    assert dupes.json()["sold_count"] == 0

    await client.patch(f"{API}/cards/lock", headers=headers, json={"card_ids": [spare.id], "locked": False})
    assert (await client.post(f"{API}/cards/sell", headers=headers, json={"user_card_id": spare.id})).status_code == 200
    assert await _card(db_session, keep.id) is not None


async def test_cannot_lock_someone_elses_card(client, db_session, bot_token):
    owner = await _register(client, db_session, 880002, bot_token)
    await _register(client, db_session, 880003, bot_token)
    player = await create_player(db_session, rarity=Rarity.common)
    card = await _give(db_session, owner.id, player.id, 1)

    resp = await client.patch(
        f"{API}/cards/lock", headers=telegram_headers(880003, bot_token), json={"card_ids": [card.id], "locked": True},
    )
    assert resp.status_code == 404
    assert (await _card(db_session, card.id)).is_user_locked is False


async def test_locked_and_squad_copies_are_listed_as_their_own_tiles(client, db_session, bot_token):
    user = await _register(client, db_session, 880004, bot_token)
    player = await create_player(db_session, rarity=Rarity.rare)
    await _give(db_session, user.id, player.id, 1)
    await _give(db_session, user.id, player.id, 2)
    squad = await _give(db_session, user.id, player.id, 3, is_in_lineup=True)
    locked = await _give(db_session, user.id, player.id, 4, is_user_locked=True)

    items = (await client.get(f"{API}/cards", headers=telegram_headers(880004, bot_token))).json()["items"]
    ids = {i["id"] for i in items}
    # Two plain copies collapse into one tile; the squad and locked copies stand alone.
    assert len(items) == 3
    assert squad.id in ids and locked.id in ids
    by_id = {i["id"]: i for i in items}
    assert by_id[squad.id]["is_in_lineup"] is True
    assert by_id[locked.id]["is_user_locked"] is True


async def test_album_shows_the_copy_that_plays(client, db_session, bot_token):
    user = await _register(client, db_session, 880005, bot_token)
    player = await create_player(db_session, rarity=Rarity.common)
    await _give(db_session, user.id, player.id, 1)
    squad = await _give(db_session, user.id, player.id, 2, is_in_lineup=True)

    detail = (await client.get("/api/v1/collection/album/-1", headers=telegram_headers(880005, bot_token))).json()
    slot = next(s for s in detail["players"] if s["player"]["id"] == player.id)
    assert slot["card"]["id"] == squad.id and slot["card"]["is_in_lineup"] is True
    assert slot["duplicate_count"] == 2


async def _rule(db_session):
    db_session.add(CardUpgradeRule(
        from_rarity=Rarity.common, to_rarity=Rarity.rare, success_chance=1.0, coin_cost=0, is_active=True,
        extra_card_bonus=0, max_success_chance=1.0,
    ))
    await db_session.commit()


async def test_forge_needs_confirmation_for_squad_cards_and_refuses_locked_ones(client, db_session, bot_token):
    user = await _register(client, db_session, 880006, bot_token)
    await _rule(db_session)
    common = await create_player(db_session, rarity=Rarity.common)
    await create_player(db_session, rarity=Rarity.rare, rating=80)
    squad = await _give(db_session, user.id, common.id, 1, is_in_lineup=True)
    locked = await _give(db_session, user.id, common.id, 2, is_user_locked=True)
    headers = telegram_headers(880006, bot_token)

    resp = await client.post(f"{API}/upgrade", headers=headers, json={"user_card_ids": [locked.id], "to_rarity": "rare"})
    assert resp.status_code == 409 and resp.json()["error"]["details"]["reason"] == "user_locked"

    resp = await client.post(f"{API}/upgrade", headers=headers, json={"user_card_ids": [squad.id], "to_rarity": "rare"})
    assert resp.status_code == 409
    assert resp.json()["error"]["details"] == {"reason": "in_squad", "card_ids": [squad.id]}
    assert await _card(db_session, squad.id) is not None

    resp = await client.post(
        f"{API}/upgrade", headers=headers,
        json={"user_card_ids": [squad.id], "to_rarity": "rare", "confirm_leave_squad": True},
    )
    assert resp.status_code == 200 and resp.json()["success"] is True
    assert await _card(db_session, squad.id) is None


async def test_diamond_feeding_works_on_a_squad_card_but_never_burns_a_locked_one(client, db_session, bot_token):
    user = await _register(client, db_session, 880007, bot_token)
    diamond = await create_player(db_session, rarity=Rarity.diamond, rating=60, attack_rating=60, defense_rating=60)
    common = await create_player(db_session, rarity=Rarity.common, rating=65)
    target = await _give(db_session, user.id, diamond.id, 1, is_in_lineup=True)
    materials = [(await _give(db_session, user.id, common.id, i)).id for i in range(1, 11)]
    db_session.add(DiamondUpgradeTier(
        min_rating=60, max_rating=70, common_cost=10, rare_cost=5, epic_cost=3, legendary_cost=1, is_active=True,
    ))
    await db_session.commit()
    headers = telegram_headers(880007, bot_token)

    locked_material = await _card(db_session, materials[0])
    locked_material.is_user_locked = True
    await db_session.commit()
    resp = await client.post(
        f"{API}/diamond-upgrade/feed", headers=headers, json={"diamond_card_id": target.id, "material_card_ids": materials},
    )
    assert resp.status_code == 409
    assert await _card(db_session, materials[0]) is not None

    locked_material.is_user_locked = False
    await db_session.commit()
    resp = await client.post(
        f"{API}/diamond-upgrade/feed", headers=headers, json={"diamond_card_id": target.id, "material_card_ids": materials},
    )
    assert resp.status_code == 200
    assert resp.json()["diamond_card"]["player"]["rating"] == 61


def test_can_burn_respects_squads_trades_and_the_owner_lock():
    assert UserCard(is_locked_by_admin=False, is_locked_in_trade=False, is_in_lineup=False,
                    is_in_tactico_squad=False, is_user_locked=False).can_burn()
    for flag in ("is_locked_by_admin", "is_locked_in_trade", "is_in_lineup", "is_in_tactico_squad", "is_user_locked"):
        fields = dict(is_locked_by_admin=False, is_locked_in_trade=False, is_in_lineup=False,
                      is_in_tactico_squad=False, is_user_locked=False)
        fields[flag] = True
        assert not UserCard(**fields).can_burn(), flag


async def test_filter_options_and_saved_default(client, db_session, bot_token):
    user = await _register(client, db_session, 880008, bot_token)
    a = await create_player(db_session, rarity=Rarity.common, country="Бразилия", club="Сантос")
    b = await create_player(db_session, rarity=Rarity.rare, country="Аргентина", club="Ривер")
    await _give(db_session, user.id, a.id, 1)
    await _give(db_session, user.id, a.id, 2)
    await _give(db_session, user.id, b.id, 1)
    headers = telegram_headers(880008, bot_token)

    options = (await client.get(f"{API}/filter-options", headers=headers)).json()
    assert options == {"countries": ["Бразилия", "Аргентина"], "clubs": ["Сантос", "Ривер"]}

    assert (await client.get(f"{API}/filter-default", headers=headers)).json() is None
    saved = await client.put(
        f"{API}/filter-default", headers=headers,
        json={"rarity": "rare", "country": "Аргентина", "position": "NOPE", "sort_by": "rating"},
    )
    assert saved.status_code == 200
    # Unknown values are dropped, unset ones stay unset.
    assert saved.json() == {"rarity": "rare", "country": "Аргентина", "club": None, "position": None,
                            "sort_by": "rating", "has_skill": None}
    assert (await client.get(f"{API}/filter-default", headers=headers)).json()["country"] == "Аргентина"

    cleared = await client.put(f"{API}/filter-default", headers=headers, json={})
    assert cleared.json() is None
