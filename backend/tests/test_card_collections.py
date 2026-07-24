from app.models.card_collection import CardCollection
from app.models.enums import Rarity
from app.services.pack_service import pick_random_player
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _admin_headers(client, bot_token):
    headers = telegram_headers(999000001, bot_token)
    resp = await client.post("/api/v1/auth/session", headers=headers)
    admin_token = resp.json()["admin_token"]
    return {"Authorization": f"Bearer {admin_token}"}


async def test_admin_card_collection_crud(client, db_session, bot_token):
    headers = await _admin_headers(client, bot_token)

    create_resp = await client.post(
        "/api/v1/admin/card-collections", headers=headers,
        json={"name": "World Cup 2026", "description": "Retro cards", "is_active": True, "sort_order": 1},
    )
    assert create_resp.status_code == 200
    collection_id = create_resp.json()["id"]

    list_resp = await client.get("/api/v1/admin/card-collections", headers=headers)
    assert any(c["id"] == collection_id for c in list_resp.json())

    update_resp = await client.put(
        f"/api/v1/admin/card-collections/{collection_id}", headers=headers, json={"description": "Updated"}
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["description"] == "Updated"

    toggle_resp = await client.post(f"/api/v1/admin/card-collections/{collection_id}/toggle-active", headers=headers)
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["is_active"] is False


async def test_public_collections_endpoint_returns_only_active(client, db_session, bot_token):
    db_session.add(CardCollection(name="Active One", is_active=True))
    db_session.add(CardCollection(name="Disabled One", is_active=False))
    await db_session.commit()

    headers = telegram_headers(870001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.get("/api/v1/collections", headers=headers)
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert "Active One" in names
    assert "Disabled One" not in names


async def test_inactive_collection_excluded_from_pack_rolls(client, db_session, bot_token):
    collection = CardCollection(name="Paused Set", is_active=False)
    db_session.add(collection)
    await db_session.flush()

    excluded_player = await create_player(db_session, rarity=Rarity.common, collection_id=collection.id)
    included_player = await create_player(db_session, rarity=Rarity.common)
    await db_session.commit()

    for _ in range(30):
        player = await pick_random_player(db_session, Rarity.common)
        assert player.id != excluded_player.id
    assert included_player.id is not None


async def test_collection_filter_on_collection_cards_endpoint(client, db_session, bot_token):
    from app.models.enums import CardSource
    from app.services.card_creation import create_user_card

    collection = CardCollection(name="Legends", is_active=True)
    db_session.add(collection)
    await db_session.flush()

    tagged_player = await create_player(db_session, rarity=Rarity.rare, collection_id=collection.id)
    other_player = await create_player(db_session, rarity=Rarity.rare)
    await db_session.commit()

    headers = telegram_headers(870002, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 870002)

    await create_user_card(db_session, user.id, tagged_player.id, CardSource.seed)
    await create_user_card(db_session, user.id, other_player.id, CardSource.seed)
    await db_session.commit()

    resp = await client.get(f"/api/v1/collection/cards?collection_id={collection.id}", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["player"]["id"] == tagged_player.id


async def test_collection_name_propagates_through_nested_user_card_schema(client, db_session, bot_token):
    from app.models.enums import CardSource
    from app.services.card_creation import create_user_card

    collection = CardCollection(name="Icons", is_active=True)
    db_session.add(collection)
    await db_session.flush()

    tagged_player = await create_player(db_session, rarity=Rarity.rare, collection_id=collection.id)
    other_player = await create_player(db_session, rarity=Rarity.rare)
    await db_session.commit()

    headers = telegram_headers(870003, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 870003)

    await create_user_card(db_session, user.id, tagged_player.id, CardSource.seed)
    await create_user_card(db_session, user.id, other_player.id, CardSource.seed)
    await db_session.commit()

    resp = await client.get("/api/v1/collection/cards", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]

    tagged_item = next(i for i in items if i["player"]["id"] == tagged_player.id)
    other_item = next(i for i in items if i["player"]["id"] == other_player.id)
    assert tagged_item["player"]["collection_name"] == "Icons"
    assert other_item["player"]["collection_name"] is None
