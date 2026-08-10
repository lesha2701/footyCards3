from sqlalchemy import select

from app.models.card import UserCard
from app.models.card_upgrade import CardUpgradeRule
from app.models.enums import CardSource, Rarity
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def _seed_rule(db_session, from_rarity, to_rarity, chance, cost) -> CardUpgradeRule:
    rule = CardUpgradeRule(from_rarity=from_rarity, to_rarity=to_rarity, success_chance=chance, coin_cost=cost, is_active=True)
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)
    return rule


async def _give_card(db_session, owner_id: int, player_id: int, serial_number: int = 1) -> UserCard:
    """Plain insert, bypassing app.services.card_creation.create_user_card —
    that helper takes a row lock (with_for_update) meant for concurrent
    request handling, which doesn't play well with a test calling it
    directly on the test's own long-lived session."""
    card = UserCard(owner_id=owner_id, player_id=player_id, source=CardSource.seed, serial_number=serial_number)
    db_session.add(card)
    await db_session.commit()
    await db_session.refresh(card)
    return card


async def test_upgrade_success_replaces_card_and_debits_coins(client, db_session, bot_token):
    user = await _register(client, db_session, 900001, bot_token)
    user_id = user.id
    common_player = await create_player(db_session, rarity=Rarity.common)
    common_player_id = common_player.id
    await create_player(db_session, rarity=Rarity.rare, rating=80)
    card = await _give_card(db_session, user_id, common_player_id)
    card_id = card.id
    await _seed_rule(db_session, Rarity.common, Rarity.rare, chance=1.0, cost=50)

    headers = telegram_headers(900001, bot_token)
    resp = await client.post(
        f"/api/v1/collection/cards/{card_id}/upgrade", headers=headers, json={"to_rarity": "rare"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["new_card"]["player"]["rarity"] == "rare"
    assert body["new_balance"] == 500 - 50

    # the staked card must be gone, replaced by exactly one new (rare) card —
    # not checked by card_id, since SQLite may recycle a deleted rowid for
    # the replacement row, unlike Postgres' never-reused SERIAL sequence.
    db_session.expire_all()
    cards = (await db_session.execute(select(UserCard).where(UserCard.owner_id == user_id))).scalars().all()
    assert len(cards) == 1
    assert cards[0].player_id != common_player_id


async def test_upgrade_failure_loses_card_and_coins(client, db_session, bot_token):
    user = await _register(client, db_session, 900002, bot_token)
    user_id = user.id
    common_player = await create_player(db_session, rarity=Rarity.common)
    card = await _give_card(db_session, user_id, common_player.id)
    card_id = card.id
    await _seed_rule(db_session, Rarity.common, Rarity.rare, chance=0.0, cost=50)

    headers = telegram_headers(900002, bot_token)
    resp = await client.post(
        f"/api/v1/collection/cards/{card_id}/upgrade", headers=headers, json={"to_rarity": "rare"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert body["new_card"] is None
    assert body["new_balance"] == 500 - 50

    db_session.expire_all()
    cards = (await db_session.execute(select(UserCard).where(UserCard.owner_id == user_id))).scalars().all()
    assert len(cards) == 0


async def test_upgrade_insufficient_balance_leaves_card_untouched(client, db_session, bot_token):
    user = await _register(client, db_session, 900003, bot_token)
    common_player = await create_player(db_session, rarity=Rarity.common)
    card = await _give_card(db_session, user.id, common_player.id)
    card_id = card.id
    await _seed_rule(db_session, Rarity.common, Rarity.legendary, chance=1.0, cost=999999)

    headers = telegram_headers(900003, bot_token)
    resp = await client.post(
        f"/api/v1/collection/cards/{card_id}/upgrade", headers=headers, json={"to_rarity": "legendary"}
    )
    assert resp.status_code == 400

    db_session.expire_all()
    still_there = await db_session.get(UserCard, card_id)
    assert still_there is not None
    await db_session.refresh(user)
    assert user.balance == 500


async def test_upgrade_locked_card_is_rejected(client, db_session, bot_token):
    user = await _register(client, db_session, 900004, bot_token)
    common_player = await create_player(db_session, rarity=Rarity.common)
    card = await _give_card(db_session, user.id, common_player.id)
    card_id = card.id
    card.is_locked_in_trade = True
    db_session.add(card)
    await db_session.commit()
    await _seed_rule(db_session, Rarity.common, Rarity.rare, chance=1.0, cost=50)

    headers = telegram_headers(900004, bot_token)
    resp = await client.post(
        f"/api/v1/collection/cards/{card_id}/upgrade", headers=headers, json={"to_rarity": "rare"}
    )
    assert resp.status_code == 409


async def test_upgrade_card_locked_in_tactico_squad_is_rejected(client, db_session, bot_token):
    user = await _register(client, db_session, 900008, bot_token)
    common_player = await create_player(db_session, rarity=Rarity.common)
    card = await _give_card(db_session, user.id, common_player.id)
    card_id = card.id
    card.is_in_tactico_squad = True
    db_session.add(card)
    await db_session.commit()
    await _seed_rule(db_session, Rarity.common, Rarity.rare, chance=1.0, cost=50)

    headers = telegram_headers(900008, bot_token)
    resp = await client.post(
        f"/api/v1/collection/cards/{card_id}/upgrade", headers=headers, json={"to_rarity": "rare"}
    )
    assert resp.status_code == 409


async def test_upgrade_to_lower_or_equal_rarity_is_rejected(client, db_session, bot_token):
    user = await _register(client, db_session, 900005, bot_token)
    rare_player = await create_player(db_session, rarity=Rarity.rare, rating=80)
    card = await _give_card(db_session, user.id, rare_player.id)
    card_id = card.id

    headers = telegram_headers(900005, bot_token)
    resp = await client.post(
        f"/api/v1/collection/cards/{card_id}/upgrade", headers=headers, json={"to_rarity": "common"}
    )
    assert resp.status_code == 409


async def test_upgrade_without_configured_rule_is_rejected(client, db_session, bot_token):
    user = await _register(client, db_session, 900006, bot_token)
    common_player = await create_player(db_session, rarity=Rarity.common)
    card = await _give_card(db_session, user.id, common_player.id)
    card_id = card.id
    # no CardUpgradeRule seeded for common -> epic

    headers = telegram_headers(900006, bot_token)
    resp = await client.post(
        f"/api/v1/collection/cards/{card_id}/upgrade", headers=headers, json={"to_rarity": "epic"}
    )
    assert resp.status_code == 409


async def test_upgrade_idempotency_key_prevents_double_charge(client, db_session, bot_token):
    user = await _register(client, db_session, 900007, bot_token)
    common_player = await create_player(db_session, rarity=Rarity.common)
    await create_player(db_session, rarity=Rarity.rare, rating=80)
    card = await _give_card(db_session, user.id, common_player.id)
    card_id = card.id
    await _seed_rule(db_session, Rarity.common, Rarity.rare, chance=1.0, cost=50)

    headers = telegram_headers(900007, bot_token)
    payload = {"to_rarity": "rare", "idempotency_key": "upg-abc"}
    first = await client.post(f"/api/v1/collection/cards/{card_id}/upgrade", headers=headers, json=payload)
    second = await client.post(f"/api/v1/collection/cards/{card_id}/upgrade", headers=headers, json=payload)

    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["new_card"]["id"] == second.json()["new_card"]["id"]
    assert first.json()["new_balance"] == second.json()["new_balance"] == 450

    await db_session.refresh(user)
    assert user.balance == 450
