"""«Академия» prestige (services/path_prestige_service.py): tiers bought with
duplicates of the same player (5 units) or spare copies of other «Академия»
players (1 unit), rewards, «Икона» number, talent reforge, soft bonuses,
sale price, leaderboard and showcase."""
import pytest
from sqlalchemy import func, select

import app.core.rate_limit as rate_limit_module
from app.models.card import UserCard
from app.models.card_path import CardPath, PathPrestigeLedger
from app.models.enums import CardSource, Position, Rarity
from app.models.game_config import GameConfig
from app.services import path_service
from app.services.card_creation import create_user_card
from app.services.path_talent_effects import talent_snapshot
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _config(db_session, **overrides) -> GameConfig:
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
    for key, value in overrides.items():
        setattr(config, key, value)
    await db_session.commit()
    return config


async def _login(client, db_session, bot_token, telegram_id, balance=10_000):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, telegram_id)
    user.balance = balance
    await db_session.commit()
    return headers, user


async def _academy(db_session, talent="fighter", position=Position.ST):
    return await create_player(db_session, rarity=Rarity.diamond, rating=60, position=position, path_talent_code=talent)


async def _copies(db_session, user_id, player, n):
    cards = [await create_user_card(db_session, user_id, player.id, CardSource.seed) for _ in range(n)]
    await db_session.commit()
    return cards


async def _exists(db_session, card_id) -> bool:
    return (await db_session.execute(select(UserCard.id).where(UserCard.id == card_id))).scalar_one_or_none() is not None


async def _card(db_session, card_id) -> UserCard:
    return (await db_session.execute(
        select(UserCard).where(UserCard.id == card_id).execution_options(populate_existing=True)
    )).scalar_one()


def _url(card_id, op="prestige"):
    return f"/api/v1/path/cards/{card_id}/{op}"


async def test_tier_up_with_a_duplicate_of_the_same_player_pays_the_reward(client, db_session, bot_token):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 980001, balance=1_000)
    target, dupe = await _copies(db_session, user.id, await _academy(db_session), 2)
    resp = await client.post(_url(target.id), headers=headers, json={"idempotency_key": "p1"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["prestige"]["tier"] == 1 and body["prestige"]["tier_name"] == "Бронза"
    assert body["granted"] == {"coins": 300, "attempts": 1}
    assert not await _exists(db_session, dupe.id)
    await db_session.refresh(user)
    assert user.balance == 1_300
    path = (await db_session.execute(select(CardPath).where(CardPath.user_card_id == target.id))).scalar_one()
    assert path.bought_attempts == 1
    replay = await client.post(_url(target.id), headers=headers, json={"idempotency_key": "p1"})
    assert replay.status_code == 200 and replay.json()["prestige"]["tier"] == 1
    assert (await db_session.execute(select(func.count(PathPrestigeLedger.id)))).scalar_one() == 1


async def test_other_academy_players_count_five_to_one_and_each_keeps_a_copy(client, db_session, bot_token):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 980002)
    (target,) = await _copies(db_session, user.id, await _academy(db_session), 1)
    others = [await _copies(db_session, user.id, await _academy(db_session, "captain", Position.CM), 3) for _ in range(2)]
    # Two other players × 2 spares = 4 units < 5 needed: refused, nothing burnt.
    resp = await client.post(_url(target.id), headers=headers, json={})
    assert resp.status_code == 409 and resp.json()["error"]["details"]["need_units"] == 5
    third = await _copies(db_session, user.id, await _academy(db_session, "composure"), 2)
    resp = await client.post(_url(target.id), headers=headers, json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["prestige"]["tier"] == 1
    for copies in others + [third]:
        left = [c for c in copies if await _exists(db_session, c.id)]
        assert len(left) >= 1  # the keeper (lowest serial) always stays
        assert await _exists(db_session, copies[0].id)
    burnt = (await db_session.execute(select(PathPrestigeLedger.consumed_card_ids))).scalar_one()
    assert len(burnt) == 5


async def test_mixed_material_and_waste_is_refused(client, db_session, bot_token):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 980003)
    target, dupe1, dupe2 = await _copies(db_session, user.id, await _academy(db_session), 3)
    target_row = await _card(db_session, target.id)
    target_row.prestige = 1
    await db_session.commit()
    other = await _copies(db_session, user.id, await _academy(db_session, "captain", Position.CM), 6)
    # Silver needs 2 dupes = 10 units: 1 dupe + 5 spares fits exactly.
    resp = await client.post(_url(target.id), headers=headers,
                             json={"material_card_ids": [dupe1.id] + [c.id for c in other[1:6]]})
    assert resp.status_code == 200, resp.text
    assert resp.json()["prestige"]["tier"] == 2
    # Gold needs 3 dupes = 15 units; dupe2 (5) alone is short, and asking for more than needed is refused.
    short = await client.post(_url(target.id), headers=headers, json={"material_card_ids": [dupe2.id]})
    assert short.status_code == 409


async def test_copies_with_progress_or_locks_are_never_material(client, db_session, bot_token):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 980004)
    target, grown, locked = await _copies(db_session, user.id, await _academy(db_session), 3)
    (await _card(db_session, grown.id)).path_level = 2
    (await _card(db_session, locked.id)).is_in_lineup = True
    await db_session.commit()
    resp = await client.post(_url(target.id), headers=headers, json={})
    assert resp.status_code == 409
    assert await _exists(db_session, grown.id) and await _exists(db_session, locked.id)


async def test_top_tier_gets_an_icon_number_and_one_reforge(client, db_session, bot_token):
    config = await _config(db_session, path_prestige_dupes=[1, 1])
    headers, user = await _login(client, db_session, bot_token, 980005)
    first = await _copies(db_session, user.id, await _academy(db_session), 3)
    second = await _copies(db_session, user.id, await _academy(db_session, "big_matches"), 3)
    for card in (first[0], second[0]):
        for _ in range(2):
            assert (await client.post(_url(card.id), headers=headers, json={})).status_code == 200
    a, b = await _card(db_session, first[0].id), await _card(db_session, second[0].id)
    assert (a.prestige, a.prestige_icon_number) == (2, 1) and (b.prestige, b.prestige_icon_number) == (2, 2)

    state = (await client.get(f"/api/v1/path/cards/{a.id}", headers=headers)).json()
    assert state["prestige"]["can_reforge"] and "fighter" not in {o["code"] for o in state["prestige"]["reforge_options"]}
    resp = await client.post(_url(a.id, "reforge"), headers=headers, json={"talent_code": "composure"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["talent"]["code"] == "composure"
    again = await client.post(_url(a.id, "reforge"), headers=headers, json={"talent_code": "second_wind"})
    assert again.status_code == 409

    a = await _card(db_session, a.id)
    a.path_stage = 2
    await db_session.commit()
    await db_session.refresh(a, ["player"])
    catalog = await path_service.load_catalog(db_session)
    assert talent_snapshot(a, catalog, config, "arena")["code"] == "composure"


async def test_reforge_needs_the_top_tier(client, db_session, bot_token):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 980006)
    (card,) = await _copies(db_session, user.id, await _academy(db_session), 1)
    resp = await client.post(_url(card.id, "reforge"), headers=headers, json={"talent_code": "composure"})
    assert resp.status_code == 409


async def test_prestige_adds_experience_and_free_attempts(client, db_session, bot_token):
    await _config(db_session, path_daily_free_arena=1)
    _headers, user = await _login(client, db_session, bot_token, 980007)
    (card,) = await _copies(db_session, user.id, await _academy(db_session), 1)
    row = await _card(db_session, card.id)
    row.prestige = 4  # 4 × 5% capped at 15%, +4 free attempts
    await db_session.commit()
    results = []
    for i in range(6):
        res = await path_service.award_match(
            db_session, user_id=user.id, source_type="arena", source_id=str(i),
            entries=[path_service.MatchEntry(card.id, "win")],
        )
        await db_session.commit()
        results.append(res[0])
    assert [r.status for r in results] == ["awarded"] * 5 + ["no_attempts"]
    assert results[0].xp == 20 + 3  # 20 × 15%


async def test_prestige_raises_the_sale_price_and_needs_confirmation(client, db_session, bot_token):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 980008, balance=0)
    player = await _academy(db_session)
    card, _spare = await _copies(db_session, user.id, player, 2)
    row = await _card(db_session, card.id)
    row.prestige = 2
    await db_session.commit()
    resp = await client.post("/api/v1/collection/cards/sell", headers=headers, json={"user_card_id": card.id})
    assert resp.status_code == 409 and resp.json()["error"]["details"]["requires_path_loss_confirmation"]
    resp = await client.post("/api/v1/collection/cards/sell", headers=headers,
                             json={"user_card_id": card.id, "confirm_skill_loss": True})
    assert resp.status_code == 200 and resp.json()["coins_earned"] == player.quick_sell_price * 2


async def test_leaderboard_and_showcase(client, db_session, bot_token):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 980009)
    cards = await _copies(db_session, user.id, await _academy(db_session), 2)
    (await _card(db_session, cards[0].id)).prestige = 3
    await db_session.commit()
    ranking = await client.get("/api/v1/leaderboard/ranking", headers=headers, params={"metric": "academy_prestige"})
    assert ranking.status_code == 200, ranking.text
    assert ranking.json()["top"][0]["user_id"] == user.id and ranking.json()["top"][0]["value"] == 3
    showcase = await client.get(f"/api/v1/path/showcase/{user.id}", headers=headers)
    assert showcase.status_code == 200
    assert [c["id"] for c in showcase.json()] == [cards[0].id] and showcase.json()[0]["prestige"] == 3
