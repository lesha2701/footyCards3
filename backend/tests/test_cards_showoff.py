"""Showing cards off: a rare print on the club wall, the «Редкие версии»
filter, «Золотая страница», the profile «Витрина» and a friend's album."""
from unittest.mock import patch

from sqlalchemy import select

from app.models.card_collection import CardCollection
from app.models.club import Club, ClubMember
from app.models.club_wall import ClubPost
from app.models.enums import CardSource, ClubLogoShape, ClubRole, ClubType, Rarity
from app.services import card_finish_service
from app.services.card_creation import create_user_card
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _login(client, bot_token, tg_id, db_session):
    headers = telegram_headers(tg_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    return headers, await get_user_by_telegram_id(db_session, tg_id)


async def test_a_rare_print_is_posted_on_the_club_wall(client, db_session, bot_token):
    _, user = await _login(client, bot_token, 760001, db_session)
    club = Club(
        name="Showoff FC", club_type=ClubType.open, logo_shape=ClubLogoShape.shield,
        logo_color="#123456", captain_id=user.id, invite_code="showoff1", budget=0,
    )
    db_session.add(club)
    await db_session.flush()
    db_session.add(ClubMember(club_id=club.id, user_id=user.id, role=ClubRole.captain))
    player = await create_player(db_session, rarity=Rarity.epic)
    with patch.object(card_finish_service._rng, "random", return_value=0.0):
        await create_user_card(db_session, user.id, player.id, CardSource.pack)
    with patch.object(card_finish_service._rng, "random", return_value=0.99):
        await create_user_card(db_session, user.id, player.id, CardSource.pack)
    await db_session.commit()
    posts = (await db_session.execute(select(ClubPost).where(ClubPost.club_id == club.id))).scalars().all()
    assert len(posts) == 1
    assert player.display_name in posts[0].text and "С автографом" in posts[0].text


async def test_finish_filter_golden_page_showcase_and_friend_album(client, db_session, bot_token):
    headers, user = await _login(client, bot_token, 760002, db_session)
    other_headers, _ = await _login(client, bot_token, 760003, db_session)
    collection = CardCollection(name="Showoff page")
    db_session.add(collection)
    await db_session.flush()
    p1 = await create_player(db_session, rarity=Rarity.rare, collection_id=collection.id)
    p2 = await create_player(db_session, rarity=Rarity.rare, collection_id=collection.id)
    c1 = await create_user_card(db_session, user.id, p1.id, CardSource.admin_grant)
    c2 = await create_user_card(db_session, user.id, p2.id, CardSource.admin_grant)
    c1.finish = "gold"
    await db_session.commit()

    # The filter keeps the rare prints only.
    items = (await client.get("/api/v1/collection/cards?finish=true", headers=headers)).json()["items"]
    assert [i["id"] for i in items] == [c1.id]

    # One of two footballers in a rare print: not yet a «Золотая страница».
    page = (await client.get(f"/api/v1/collection/album/{collection.id}", headers=headers)).json()
    assert page["finished_count"] == 1 and page["total_count"] == 2
    c2.finish = "night"
    await db_session.commit()
    page = (await client.get(f"/api/v1/collection/album/{collection.id}", headers=headers)).json()
    assert page["finished_count"] == 2

    # «Витрина»: own cards only, at most three, shown on the public profile.
    r = await client.put("/api/v1/collection/showcase", json={"card_ids": [c2.id, c1.id]}, headers=headers)
    assert r.status_code == 200 and [c["id"] for c in r.json()] == [c2.id, c1.id]
    prof = (await client.get(f"/api/v1/users/{user.id}", headers=other_headers)).json()
    assert [c["id"] for c in prof["showcase"]] == [c2.id, c1.id]
    assert prof["showcase"][0]["finish"] == "night"
    r = await client.put("/api/v1/collection/showcase", json={"card_ids": [c1.id]}, headers=other_headers)
    assert r.status_code == 404
    r = await client.put("/api/v1/collection/showcase", json={"card_ids": [1, 2, 3, 4]}, headers=headers)
    assert r.status_code == 409

    # A friend leafs through the album.
    overview = (await client.get(f"/api/v1/users/{user.id}/album", headers=other_headers)).json()
    assert any(c["id"] == collection.id and c["owned_count"] == 2 for c in overview["collections"])
    friend_page = (await client.get(f"/api/v1/users/{user.id}/album/{collection.id}", headers=other_headers)).json()
    assert friend_page["owned_count"] == 2 and friend_page["finished_count"] == 2
