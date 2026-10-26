"""«Артефакты» (services/artifact_service.py): putting copies on / taking
them off / swapping, and the card rating bonus (e.g. Maldini's armband:
+3 to the owner's Maldini cards) reaching every mode through the card row."""
import pytest

import app.core.rate_limit as rate_limit_module
from app.models.card import UserCard
from app.models.enums import CardSource, Rarity
from app.models.monetization import Artifact
from app.services import artifact_service
from app.services.card_creation import create_user_card
from app.services.game_config_service import get_config
from app.services.player_stats_service import card_rating_bonus
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1/artifacts"


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _setup(client, db_session, bot_token, telegram_id=880001, slots=2):
    headers = telegram_headers(telegram_id, bot_token)
    assert (await client.post("/api/v1/auth/session", headers=headers)).status_code == 200
    user = await get_user_by_telegram_id(db_session, telegram_id)
    config = await get_config(db_session)
    config.artifacts_enabled = True
    config.artifact_slots = slots
    config.artifact_max_stat = 6
    await db_session.commit()
    return user, headers


async def _artifact(db_session, name, **fields):
    artifact = Artifact(name=name, target="my_player", effect=fields.pop("effect", "defense"),
                        effect_value=fields.pop("effect_value", 2), **fields)
    db_session.add(artifact)
    await db_session.commit()
    return artifact


async def _grant(db_session, user_id, artifact_id):
    row = await artifact_service.grant(db_session, user_id, artifact_id, "admin")
    await db_session.commit()
    return row.id


def _equipped(body) -> dict[int, bool]:
    return {c["copy_id"]: c["equipped"] for c in body["shelf"]}


async def test_take_off_put_on_and_swap(client, db_session, bot_token):
    user, headers = await _setup(client, db_session, bot_token)
    copies = [await _grant(db_session, user.id, (await _artifact(db_session, f"A{i}")).id) for i in range(3)]
    first, second, third = copies

    # Full slots: the third is on the shelf and can't go on yet.
    resp = await client.post(f"{API}/copies/{third}/active", headers=headers, json={"equipped": True})
    assert resp.status_code == 409 and "не больше 2" in resp.json()["error"]["message"]

    resp = await client.post(f"{API}/copies/{first}/active", headers=headers, json={"equipped": False})
    assert resp.status_code == 200 and _equipped(resp.json()) == {first: False, second: True, third: False}

    resp = await client.post(f"{API}/copies/{third}/active", headers=headers, json={"equipped": True})
    assert resp.status_code == 200 and _equipped(resp.json()) == {first: False, second: True, third: True}
    assert resp.json()["effects"]["my_player"] == [{"effect": "defense", "value": 4, "label": "+4 к защите"}]


async def test_card_bonus_reaches_the_card_and_follows_the_artifact(client, db_session, bot_token):
    user, headers = await _setup(client, db_session, bot_token, telegram_id=880011, slots=1)
    maldini = await create_player(db_session, rarity=Rarity.legendary, rating=90)
    card = await create_user_card(db_session, user.id, maldini.id, CardSource.seed)
    await db_session.commit()
    armband = await _artifact(db_session, "Повязка", card_player_id=maldini.id, card_rating_bonus=3)

    copy_id = await _grant(db_session, user.id, armband.id)  # a free slot: goes on at once
    await db_session.refresh(card)
    assert card.artifact_rating_bonus == 3 and card_rating_bonus(card) == 3

    # The collection shows the boosted rating.
    cards = (await client.get("/api/v1/collection/cards", headers=headers)).json()["items"]
    assert [c["player"]["rating"] for c in cards if c["id"] == card.id] == [93]

    # A card of that player obtained later gets it too.
    second = await create_user_card(db_session, user.id, maldini.id, CardSource.seed)
    await db_session.commit()
    assert card_rating_bonus(second) == 3

    # Off the slot -> gone from every card.
    resp = await client.post(f"{API}/copies/{copy_id}/active", headers=headers, json={"equipped": False})
    assert resp.status_code == 200
    for c in (card, second):
        await db_session.refresh(c)
        assert card_rating_bonus(c) == 0


async def test_traded_card_drops_the_old_owners_bonus(client, db_session, bot_token):
    user, _headers = await _setup(client, db_session, bot_token, telegram_id=880021)
    other, _ = await _setup(client, db_session, bot_token, telegram_id=880022)
    maldini = await create_player(db_session, rarity=Rarity.legendary, rating=90)
    card = await create_user_card(db_session, user.id, maldini.id, CardSource.seed)
    await db_session.commit()
    armband = await _artifact(db_session, "Повязка", card_player_id=maldini.id, card_rating_bonus=3)
    await _grant(db_session, user.id, armband.id)
    await db_session.refresh(card)
    assert card_rating_bonus(card) == 3

    # Even before any recompute, the bonus only counts for the owner it was computed for.
    card.owner_id = other.id
    assert card_rating_bonus(card) == 0


async def test_switching_artifacts_off_in_admin_removes_card_bonuses(client, db_session, bot_token):
    user, _headers = await _setup(client, db_session, bot_token, telegram_id=880031)
    maldini = await create_player(db_session, rarity=Rarity.legendary, rating=90)
    card = await create_user_card(db_session, user.id, maldini.id, CardSource.seed)
    await db_session.commit()
    armband = await _artifact(db_session, "Повязка", card_player_id=maldini.id, card_rating_bonus=3)
    await _grant(db_session, user.id, armband.id)

    admin_headers = telegram_headers(999000001, bot_token)
    token = (await client.post("/api/v1/auth/session", headers=admin_headers)).json()["admin_token"]
    resp = await client.put(
        "/api/v1/admin/games/config", headers={"Authorization": f"Bearer {token}"}, json={"artifacts_enabled": False},
    )
    assert resp.status_code == 200
    refreshed = await db_session.get(UserCard, card.id, populate_existing=True)
    assert refreshed.artifact_rating_bonus == 0


async def test_gifts_only_bought_with_stars_for_a_friend(client, db_session, bot_token):
    from sqlalchemy import select

    from app.core.exceptions import ConflictError, ForbiddenError
    from app.models.career import Friendship
    from app.models.monetization import UserArtifact

    user, headers = await _setup(client, db_session, bot_token, 880051)
    friend, _ = await _setup(client, db_session, bot_token, 880052)
    stranger, _ = await _setup(client, db_session, bot_token, 880053)
    artifact = await _artifact(db_session, "Gift", stars_price=49, coins_price=5000, is_active=True)

    # An owned copy can't be passed on any more (coins → friend bypassed the trade rules).
    copy_id = await _grant(db_session, user.id, artifact.id)
    resp = await client.post(f"/api/v1/artifacts/copies/{copy_id}/gift", headers=headers, json={"recipient_id": friend.id})
    assert resp.status_code == 403

    try:
        await artifact_service.stars_gift_order(db_session, user, artifact.id, friend.id)
        raise AssertionError("not friends yet")
    except ForbiddenError:
        pass
    low, high = sorted((user.id, friend.id))
    db_session.add(Friendship(requester_id=user.id, addressee_id=friend.id, user_low=low, user_high=high, status="accepted"))
    await db_session.commit()
    product, stars, _, _ = await artifact_service.stars_gift_order(db_session, user, artifact.id, friend.id)
    assert product == f"artifact_gift:{artifact.id}:{friend.id}" and stars == 49
    assert (await artifact_service.validate_stars_gift(db_session, user.id, f"{artifact.id}:{stranger.id}", 49))[0] is False
    try:
        await artifact_service.stars_gift_order(db_session, user, artifact.id, user.id)
        raise AssertionError("self gift")
    except ConflictError:
        pass

    await artifact_service.deliver_stars_gift(db_session, user, f"{artifact.id}:{friend.id}")
    await db_session.commit()
    rows = (await db_session.execute(select(UserArtifact).where(UserArtifact.user_id == friend.id))).scalars().all()
    assert len(rows) == 1 and rows[0].gifted_by_id == user.id and rows[0].source == "gift"
