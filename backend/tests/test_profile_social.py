"""Profile & cards social layer: safe «Продать дубликаты», friends' trade
matches, «Где взять», «Респект», the profile feed, profile sharing and the
admin gift-transfer stats."""
from datetime import datetime, timezone

from app.models.card import UserCard
from app.models.card_collection import CardCollection
from app.models.enums import CardSource, GiftKind, Rarity
from app.models.career import Friendship
from app.models.gift import Gift, GiftTransfer
from app.models.pack import StarsInvoice
from app.services.card_creation import create_user_card
from app.services.game_config_service import get_config
from tests.factories import create_gift_set, create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _login(client, bot_token, tg_id, db_session):
    headers = telegram_headers(tg_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    return headers, await get_user_by_telegram_id(db_session, tg_id)


async def _befriend(db_session, a, b):
    low, high = sorted((a.id, b.id))
    db_session.add(Friendship(requester_id=a.id, addressee_id=b.id, user_low=low, user_high=high, status="accepted"))
    await db_session.commit()


async def test_selling_duplicates_never_sells_a_rare_print(client, db_session, bot_token):
    headers, user = await _login(client, bot_token, 770001, db_session)
    player = await create_player(db_session, rarity=Rarity.rare)
    plain = [await create_user_card(db_session, user.id, player.id, CardSource.admin_grant) for _ in range(3)]
    plain[2].finish = "gold"
    await db_session.commit()
    gold_id = plain[2].id
    body = (await client.post("/api/v1/collection/cards/sell-duplicates", headers=headers, json={"preview": False})).json()
    assert body["sold_count"] == 2  # the gold copy is the keeper; both plain spares go
    left = {c["id"] for c in (await client.get("/api/v1/collection/cards", headers=headers)).json()["items"]}
    assert gold_id in left


async def test_friend_matches_and_where_to_get(client, db_session, bot_token):
    headers, me = await _login(client, bot_token, 770010, db_session)
    _, friend = await _login(client, bot_token, 770011, db_session)
    await _befriend(db_session, me, friend)
    collection = CardCollection(name="Social page")
    db_session.add(collection)
    await db_session.flush()
    mine = await create_player(db_session, rarity=Rarity.rare, collection_id=collection.id)
    theirs = await create_player(db_session, rarity=Rarity.epic, collection_id=collection.id)
    for _ in range(2):
        await create_user_card(db_session, me.id, mine.id, CardSource.admin_grant)
        await create_user_card(db_session, friend.id, theirs.id, CardSource.admin_grant)
    config = await get_config(db_session)
    config.trade_send_min_account_age_days = 0
    config.trade_send_min_active_days = 0
    await create_pack(db_session, "social-theme", 100, 3, {Rarity.common: 1.0}, player_pool=f"collection:{collection.id}")
    await db_session.commit()

    matches = (await client.get("/api/v1/trades/finder/friends", headers=headers)).json()
    assert len(matches) == 1 and matches[0]["mutual"] is True
    assert [c["player"]["id"] for c in matches[0]["they_have"]] == [theirs.id]
    assert [c["player"]["id"] for c in matches[0]["they_want"]] == [mine.id]

    sources = (await client.get(f"/api/v1/trades/finder/sources/{theirs.id}", headers=headers)).json()
    assert [p["name"] for p in sources["packs"]] == ["Social-Theme"]
    assert [f["user"]["id"] for f in sources["friends"]] == [friend.id]
    assert sources["market_lots"] == 0


async def test_respect_once_a_day_feed_and_profile_share(client, db_session, bot_token):
    headers, me = await _login(client, bot_token, 770020, db_session)
    other_headers, other = await _login(client, bot_token, 770021, db_session)
    player = await create_player(db_session, rarity=Rarity.legendary)
    card = await create_user_card(db_session, other.id, player.id, CardSource.admin_grant)
    card.finish = "autograph"
    await db_session.commit()

    social = (await client.get(f"/api/v1/users/{other.id}/social", headers=headers)).json()
    assert social["respects"] == 0 and social["can_respect"] and not social["respected_today"]
    assert social["feed"][0]["kind"] == "finish" and player.display_name in social["feed"][0]["text"]
    r = await client.post(f"/api/v1/users/{other.id}/respect", headers=headers)
    assert r.status_code == 200 and r.json()["respects"] == 1 and r.json()["respected_today"]
    assert (await client.post(f"/api/v1/users/{other.id}/respect", headers=headers)).status_code == 409
    assert (await client.post(f"/api/v1/users/{me.id}/respect", headers=headers)).status_code == 409

    shared = await client.post("/api/v1/share/prepare", headers=other_headers, json={"kind": "profile"})
    assert shared.status_code == 200, shared.text
    assert shared.json()["image_url"].startswith("/static/share/profile_")


async def test_admin_gift_transfer_stats(client, db_session, bot_token):
    _, sender = await _login(client, bot_token, 770030, db_session)
    _, receiver = await _login(client, bot_token, 770031, db_session)
    admin_headers = telegram_headers(999000001, bot_token)
    token = (await client.post("/api/v1/auth/session", headers=admin_headers)).json()["admin_token"]
    gift_set = await create_gift_set(db_session, name="Статистика", kind=GiftKind.collectible, coins_price=1, stars_price=0)
    now = datetime.now(timezone.utc)
    gift = Gift(gift_set_id=gift_set.id, recipient_id=receiver.id, serial_number=3, claimed_at=now)
    db_session.add(gift)
    await db_session.flush()
    db_session.add(GiftTransfer(batch="b1", gift_id=gift.id, from_user_id=sender.id, to_user_id=receiver.id,
                                status="done", completed_at=now))
    db_session.add(StarsInvoice(user_id=sender.id, payload_token="stats-tok", stars_amount=10,
                                shop_product="gift_batch:b1", completed_at=now))
    await db_session.commit()
    stats = (await client.get("/api/v1/admin/gifts/transfer-stats", headers={"Authorization": f"Bearer {token}"})).json()
    assert stats["stars"] == 10 and stats["copies"] == 1 and stats["senders"] == 1
    assert stats["top_sets"] == [{"name": "Статистика", "copies": 1}]


async def test_hall_of_fame_shows_showcase_trophies_and_counts(client, db_session, bot_token):
    from app.models.trophy import TrophyDefinition, UserTrophy

    headers, me = await _login(client, bot_token, 770040, db_session)
    _, other = await _login(client, bot_token, 770041, db_session)
    empty = (await client.get(f"/api/v1/users/{other.id}/hall", headers=headers)).json()
    assert empty["frames"] == [] and empty["cabinet"] == [] and empty["pedestals"] == []

    player = await create_player(db_session, rarity=Rarity.epic)
    card = await create_user_card(db_session, other.id, player.id, CardSource.admin_grant)
    card.finish = "gold"
    other.showcase_card_ids = [card.id]
    trophy = TrophyDefinition(code="champion", name="Чемпион", description="Первое место")
    db_session.add(trophy)
    await db_session.flush()
    db_session.add(UserTrophy(user_id=other.id, trophy_definition_id=trophy.id, message="Спасибо!"))
    await db_session.commit()

    hall = (await client.get(f"/api/v1/users/{other.id}/hall", headers=headers)).json()
    assert [f["id"] for f in hall["frames"]] == [card.id]
    assert hall["cabinet"][0]["kind"] == "trophy" and hall["cabinet"][0]["code"] == "champion"
    assert hall["cabinet"][0]["description"] == "Спасибо!"
    assert hall["totals"]["trophies"] == 1 and hall["totals"]["rare_prints"] == 1
    assert (await client.get("/api/v1/users/999999/hall", headers=headers)).status_code == 404
