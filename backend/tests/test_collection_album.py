from sqlalchemy import func, select

from app.models.card import UserCard
from app.models.card_collection import CardCollection, UserCollectionReward
from app.models.enums import CardSource, Rarity
from app.services.card_creation import create_user_card
from tests.factories import create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _register(client, db_session, telegram_id, bot_token):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, telegram_id)
    return user, headers


async def _admin_headers(client, bot_token):
    headers = telegram_headers(999000001, bot_token)
    resp = await client.post("/api/v1/auth/session", headers=headers)
    admin_token = resp.json()["admin_token"]
    return {"Authorization": f"Bearer {admin_token}"}


async def test_album_overview_lists_active_collections_with_progress(client, db_session, bot_token):
    user, headers = await _register(client, db_session, 880020, bot_token)

    collection = CardCollection(name="Overview Set", is_active=True, reward_coins=100)
    db_session.add(collection)
    await db_session.flush()

    owned_player = await create_player(db_session, rarity=Rarity.common, collection_id=collection.id)
    await create_player(db_session, rarity=Rarity.common, collection_id=collection.id)
    await create_user_card(db_session, user.id, owned_player.id, CardSource.seed)
    await db_session.commit()

    resp = await client.get("/api/v1/collection/album", headers=headers)
    assert resp.status_code == 200
    entry = next(c for c in resp.json()["collections"] if c["id"] == collection.id)
    assert entry["owned_count"] == 1
    assert entry["total_count"] == 2
    assert entry["is_complete"] is False
    assert entry["reward_coins"] == 100
    assert entry["reward_claimed"] is False


async def test_album_overview_includes_other_players_bucket(client, db_session, bot_token):
    _, headers = await _register(client, db_session, 880021, bot_token)
    await create_player(db_session, rarity=Rarity.common)  # collection_id=None by default

    resp = await client.get("/api/v1/collection/album", headers=headers)
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()["collections"]]
    assert -1 in ids


async def test_album_detail_shows_missing_players_without_card_data(client, db_session, bot_token):
    _, headers = await _register(client, db_session, 880022, bot_token)

    collection = CardCollection(name="Detail Set", is_active=True)
    db_session.add(collection)
    await db_session.flush()
    missing_player = await create_player(
        db_session, rarity=Rarity.common, collection_id=collection.id, display_name="Missing Guy"
    )
    await db_session.commit()

    resp = await client.get(f"/api/v1/collection/album/{collection.id}", headers=headers)
    assert resp.status_code == 200
    slot = next(s for s in resp.json()["players"] if s["player"]["id"] == missing_player.id)
    assert slot["owned"] is False
    assert slot["card"] is None
    assert slot["player"]["display_name"] == "Missing Guy"


async def test_album_search_filters_players_in_detail(client, db_session, bot_token):
    _, headers = await _register(client, db_session, 880023, bot_token)

    collection = CardCollection(name="Search Set", is_active=True)
    db_session.add(collection)
    await db_session.flush()
    await create_player(db_session, rarity=Rarity.common, collection_id=collection.id, display_name="Findme Player")
    await create_player(db_session, rarity=Rarity.common, collection_id=collection.id, display_name="Other Player")
    await db_session.commit()

    resp = await client.get(f"/api/v1/collection/album/{collection.id}?search=findme", headers=headers)
    assert resp.status_code == 200
    names = [s["player"]["display_name"] for s in resp.json()["players"]]
    assert names == ["Findme Player"]


async def test_album_search_filters_collections_in_overview(client, db_session, bot_token):
    _, headers = await _register(client, db_session, 880024, bot_token)

    collection_a = CardCollection(name="Alpha Set", is_active=True)
    collection_b = CardCollection(name="Beta Set", is_active=True)
    db_session.add_all([collection_a, collection_b])
    await db_session.flush()
    await create_player(db_session, rarity=Rarity.common, collection_id=collection_a.id, display_name="Unique Match Name")
    await create_player(db_session, rarity=Rarity.common, collection_id=collection_b.id, display_name="Nothing Related")
    await db_session.commit()

    resp = await client.get("/api/v1/collection/album", headers=headers, params={"search": "unique match"})
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()["collections"]]
    assert collection_a.id in ids
    assert collection_b.id not in ids


async def test_pack_open_completes_collection_grants_reward_once(client, db_session, bot_token):
    collection = CardCollection(name="Solo Set", is_active=True, reward_coins=150)
    db_session.add(collection)
    await db_session.flush()

    await create_player(db_session, rarity=Rarity.common, collection_id=collection.id)
    pack = await create_pack(db_session, "solo-pack", price=0, card_count=1, probabilities={Rarity.common: 1.0})

    user, headers = await _register(client, db_session, 880001, bot_token)
    balance_before = user.balance

    resp = await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["collection_rewards"]) == 1
    grant = body["collection_rewards"][0]
    assert grant["collection_id"] == collection.id
    assert grant["reward_coins"] == 150

    await db_session.refresh(user)
    assert user.balance == balance_before + 150

    rows = (
        await db_session.execute(select(UserCollectionReward).where(UserCollectionReward.user_id == user.id))
    ).scalars().all()
    assert len(rows) == 1

    # A second pack yielding the same (already-owned) player must not re-grant.
    pack2 = await create_pack(db_session, "solo-pack-2", price=0, card_count=1, probabilities={Rarity.common: 1.0})
    resp2 = await client.post(f"/api/v1/packs/{pack2.id}/open", headers=headers, json={})
    assert resp2.status_code == 200
    assert resp2.json()["collection_rewards"] == []

    await db_session.refresh(user)
    assert user.balance == balance_before + 150


async def test_collection_reward_grants_bonus_pack(client, db_session, bot_token):
    await create_player(db_session, rarity=Rarity.common)  # sole common player -> deterministic bonus roll
    bonus_pack = await create_pack(
        db_session, "bonus-reward-pack", price=0, card_count=2, probabilities={Rarity.common: 1.0}
    )

    collection = CardCollection(name="Reward Set", is_active=True, reward_coins=0, reward_pack_id=bonus_pack.id)
    db_session.add(collection)
    await db_session.flush()

    await create_player(db_session, rarity=Rarity.rare, collection_id=collection.id)
    trigger_pack = await create_pack(db_session, "trigger-pack", price=0, card_count=1, probabilities={Rarity.rare: 1.0})
    await db_session.commit()

    user, headers = await _register(client, db_session, 880002, bot_token)

    resp = await client.post(f"/api/v1/packs/{trigger_pack.id}/open", headers=headers, json={})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["collection_rewards"]) == 1
    grant = body["collection_rewards"][0]
    assert grant["granted_pack"] is not None
    assert len(grant["granted_pack"]["cards"]) == 2

    total_cards = (
        await db_session.execute(select(func.count(UserCard.id)).where(UserCard.owner_id == user.id))
    ).scalar_one()
    assert total_cards == 3  # 1 from the trigger pack + 2 from the bonus pack


async def test_trade_accept_completes_collection_for_receiver(client, db_session, bot_token):
    sender, sender_headers = await _register(client, db_session, 880010, bot_token)
    receiver, receiver_headers = await _register(client, db_session, 880011, bot_token)

    collection = CardCollection(name="Trade Set", is_active=True, reward_coins=75)
    db_session.add(collection)
    await db_session.flush()

    target_player = await create_player(db_session, rarity=Rarity.rare, collection_id=collection.id)
    sender_card = await create_user_card(db_session, sender.id, target_player.id, CardSource.seed)
    await db_session.commit()

    create_resp = await client.post(
        "/api/v1/trades/offers", headers=sender_headers,
        json={"receiver_id": receiver.id, "offered_card_ids": [sender_card.id], "requested_card_ids": []},
    )
    assert create_resp.status_code == 200
    offer_id = create_resp.json()["id"]

    receiver_balance_before = receiver.balance
    accept_resp = await client.post(f"/api/v1/trades/offers/{offer_id}/accept", headers=receiver_headers)
    assert accept_resp.status_code == 200

    await db_session.refresh(receiver)
    assert receiver.balance == receiver_balance_before + 75

    rows = (
        await db_session.execute(select(UserCollectionReward).where(UserCollectionReward.user_id == receiver.id))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].collection_id == collection.id


async def test_admin_bulk_set_collection_players(client, db_session, bot_token):
    headers = await _admin_headers(client, bot_token)

    collection_a = CardCollection(name="Set A", is_active=True)
    db_session.add(collection_a)
    await db_session.flush()

    p1 = await create_player(db_session, rarity=Rarity.common, collection_id=collection_a.id)
    p2 = await create_player(db_session, rarity=Rarity.common, collection_id=collection_a.id)
    p3 = await create_player(db_session, rarity=Rarity.common)
    await db_session.commit()

    resp = await client.put(
        f"/api/v1/admin/card-collections/{collection_a.id}/players", headers=headers,
        json={"player_ids": [p2.id, p3.id]},
    )
    assert resp.status_code == 200
    ids = {p["id"] for p in resp.json()}
    assert ids == {p2.id, p3.id}

    await db_session.refresh(p1)
    await db_session.refresh(p2)
    await db_session.refresh(p3)
    assert p1.collection_id is None
    assert p2.collection_id == collection_a.id
    assert p3.collection_id == collection_a.id


async def test_admin_bulk_set_collection_players_rejects_unknown_player_id(client, db_session, bot_token):
    headers = await _admin_headers(client, bot_token)
    collection = CardCollection(name="Set C", is_active=True)
    db_session.add(collection)
    await db_session.commit()

    resp = await client.put(
        f"/api/v1/admin/card-collections/{collection.id}/players", headers=headers,
        json={"player_ids": [999999]},
    )
    assert resp.status_code == 404
