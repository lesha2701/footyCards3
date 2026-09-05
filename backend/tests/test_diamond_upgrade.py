from typing import Optional

from sqlalchemy import select

from app.models.card import UserCard
from app.models.diamond_upgrade import DiamondUpgradeTier
from app.models.enums import CardSource, Position, Rarity
from app.services.lineup_service import FORMATION_SLOTS, calculate_base_strength
from app.services.player_stats_service import effective_card_stats
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def _admin_auth(client, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    token = session_resp.json()["admin_token"]
    return {"Authorization": f"Bearer {token}"}


async def _seed_tier(
    db_session, min_rating, max_rating,
    common: Optional[int] = 10, rare: Optional[int] = 5, epic: Optional[int] = 3, legendary: Optional[int] = 1,
) -> DiamondUpgradeTier:
    tier = DiamondUpgradeTier(
        min_rating=min_rating, max_rating=max_rating,
        common_cost=common, rare_cost=rare, epic_cost=epic, legendary_cost=legendary, is_active=True,
    )
    db_session.add(tier)
    await db_session.commit()
    await db_session.refresh(tier)
    return tier


async def _give_card(db_session, owner_id: int, player_id: int, serial_number: int) -> UserCard:
    card = UserCard(owner_id=owner_id, player_id=player_id, source=CardSource.seed, serial_number=serial_number)
    db_session.add(card)
    await db_session.commit()
    await db_session.refresh(card)
    return card


async def _give_n_cards(db_session, owner_id: int, player_id: int, n: int) -> list[int]:
    return [(await _give_card(db_session, owner_id, player_id, i)).id for i in range(1, n + 1)]


async def test_feed_exact_multiple_gains_rating_and_consumes_all(client, db_session, bot_token):
    user = await _register(client, db_session, 950001, bot_token)
    user_id = user.id
    diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=60, attack_rating=60, defense_rating=60)
    common_player = await create_player(db_session, rarity=Rarity.common, rating=65)
    diamond_card = await _give_card(db_session, user_id, diamond_player.id, 1)
    material_ids = await _give_n_cards(db_session, user_id, common_player.id, 10)
    await _seed_tier(db_session, 60, 70)

    headers = telegram_headers(950001, bot_token)
    resp = await client.post(
        "/api/v1/collection/diamond-upgrade/feed",
        headers=headers,
        json={"diamond_card_id": diamond_card.id, "material_card_ids": material_ids},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rating_gained"] == 1
    assert body["cards_consumed"] == 10
    assert body["cards_returned"] == 0
    assert body["diamond_card"]["player"]["rating"] == 61

    db_session.expire_all()
    remaining = (await db_session.execute(select(UserCard).where(UserCard.owner_id == user_id))).scalars().all()
    # Only the diamond card is left — all 10 material cards were consumed.
    assert len(remaining) == 1
    assert remaining[0].id == diamond_card.id
    assert remaining[0].diamond_rating_bonus == 1


async def test_feed_leftover_cards_are_not_consumed(client, db_session, bot_token):
    user = await _register(client, db_session, 950002, bot_token)
    user_id = user.id
    diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=60)
    common_player = await create_player(db_session, rarity=Rarity.common, rating=65)
    diamond_card = await _give_card(db_session, user_id, diamond_player.id, 1)
    material_ids = await _give_n_cards(db_session, user_id, common_player.id, 25)
    await _seed_tier(db_session, 60, 70)

    headers = telegram_headers(950002, bot_token)
    resp = await client.post(
        "/api/v1/collection/diamond-upgrade/feed",
        headers=headers,
        json={"diamond_card_id": diamond_card.id, "material_card_ids": material_ids},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rating_gained"] == 2
    assert body["cards_consumed"] == 20
    assert body["cards_returned"] == 5

    db_session.expire_all()
    remaining = (await db_session.execute(select(UserCard).where(UserCard.owner_id == user_id))).scalars().all()
    assert len(remaining) == 1 + 5


async def test_feed_below_cost_is_rejected(client, db_session, bot_token):
    user = await _register(client, db_session, 950003, bot_token)
    user_id = user.id
    diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=60)
    common_player = await create_player(db_session, rarity=Rarity.common, rating=65)
    diamond_card = await _give_card(db_session, user_id, diamond_player.id, 1)
    material_ids = await _give_n_cards(db_session, user_id, common_player.id, 5)
    await _seed_tier(db_session, 60, 70)

    headers = telegram_headers(950003, bot_token)
    resp = await client.post(
        "/api/v1/collection/diamond-upgrade/feed",
        headers=headers,
        json={"diamond_card_id": diamond_card.id, "material_card_ids": material_ids},
    )
    assert resp.status_code == 409

    db_session.expire_all()
    remaining = (await db_session.execute(select(UserCard).where(UserCard.owner_id == user_id))).scalars().all()
    assert len(remaining) == 1 + 5


async def test_feed_a_rarity_with_no_cost_set_is_rejected(client, db_session, bot_token):
    user = await _register(client, db_session, 950012, bot_token)
    user_id = user.id
    diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=60)
    legendary_player = await create_player(db_session, rarity=Rarity.legendary, rating=90)
    diamond_card = await _give_card(db_session, user_id, diamond_player.id, 1)
    material_ids = await _give_n_cards(db_session, user_id, legendary_player.id, 5)
    # legendary_cost left unset ("—" in the admin UI) — this rarity can't level up this band.
    await _seed_tier(db_session, 60, 70, common=10, rare=5, epic=3, legendary=None)

    headers = telegram_headers(950012, bot_token)
    resp = await client.post(
        "/api/v1/collection/diamond-upgrade/feed",
        headers=headers,
        json={"diamond_card_id": diamond_card.id, "material_card_ids": material_ids},
    )
    assert resp.status_code == 409

    db_session.expire_all()
    remaining = (await db_session.execute(select(UserCard).where(UserCard.owner_id == user_id))).scalars().all()
    assert len(remaining) == 1 + 5


async def test_feed_mixed_rarity_material_is_rejected(client, db_session, bot_token):
    user = await _register(client, db_session, 950004, bot_token)
    user_id = user.id
    diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=60)
    common_player = await create_player(db_session, rarity=Rarity.common, rating=65)
    rare_player = await create_player(db_session, rarity=Rarity.rare, rating=75)
    diamond_card = await _give_card(db_session, user_id, diamond_player.id, 1)
    common_ids = await _give_n_cards(db_session, user_id, common_player.id, 9)
    rare_id = (await _give_card(db_session, user_id, rare_player.id, 1)).id
    await _seed_tier(db_session, 60, 70)

    headers = telegram_headers(950004, bot_token)
    resp = await client.post(
        "/api/v1/collection/diamond-upgrade/feed",
        headers=headers,
        json={"diamond_card_id": diamond_card.id, "material_card_ids": [*common_ids, rare_id]},
    )
    assert resp.status_code == 409


async def test_diamond_card_cannot_be_used_as_material(client, db_session, bot_token):
    user = await _register(client, db_session, 950005, bot_token)
    user_id = user.id
    diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=60)
    other_diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=60)
    diamond_card = await _give_card(db_session, user_id, diamond_player.id, 1)
    other_diamond_card = await _give_card(db_session, user_id, other_diamond_player.id, 1)
    await _seed_tier(db_session, 60, 70)

    headers = telegram_headers(950005, bot_token)
    resp = await client.post(
        "/api/v1/collection/diamond-upgrade/feed",
        headers=headers,
        json={"diamond_card_id": diamond_card.id, "material_card_ids": [other_diamond_card.id]},
    )
    assert resp.status_code == 409


async def test_feed_without_a_configured_tier_is_rejected(client, db_session, bot_token):
    user = await _register(client, db_session, 950006, bot_token)
    user_id = user.id
    diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=60)
    common_player = await create_player(db_session, rarity=Rarity.common, rating=65)
    diamond_card = await _give_card(db_session, user_id, diamond_player.id, 1)
    material_ids = await _give_n_cards(db_session, user_id, common_player.id, 10)
    # No tier seeded at all.

    headers = telegram_headers(950006, bot_token)
    resp = await client.post(
        "/api/v1/collection/diamond-upgrade/feed",
        headers=headers,
        json={"diamond_card_id": diamond_card.id, "material_card_ids": material_ids},
    )
    assert resp.status_code == 409


async def test_rating_gain_is_capped_at_99_when_the_soft_cap_is_disabled(client, db_session, bot_token):
    """Above 95 the upgrade path is the fixed same-player-duplicates
    extension band (95-98 is the "any diamond" band, 98-99 is this one),
    not the admin tier table — 10 material cards per +1 rating, clamped to 99."""
    admin_headers = await _admin_auth(client, bot_token)
    resp = await client.put(
        "/api/v1/admin/games/config", headers=admin_headers, json={"diamond_rating_cap_enabled": False},
    )
    assert resp.status_code == 200

    user = await _register(client, db_session, 950007, bot_token)
    user_id = user.id
    diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=98)
    diamond_card = await _give_card(db_session, user_id, diamond_player.id, 999)
    # 20 duplicate diamond cards of the same player, cost 10 each -> would be +2 uncapped, must clamp to +1 (98 -> 99).
    material_ids = await _give_n_cards(db_session, user_id, diamond_player.id, 20)

    headers = telegram_headers(950007, bot_token)
    resp = await client.post(
        "/api/v1/collection/diamond-upgrade/feed",
        headers=headers,
        json={"diamond_card_id": diamond_card.id, "material_card_ids": material_ids},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rating_gained"] == 1
    assert body["cards_consumed"] == 10
    assert body["cards_returned"] == 10
    assert body["diamond_card"]["player"]["rating"] == 99


async def test_extension_band_95_to_98_accepts_any_other_diamond_card(client, db_session, bot_token):
    admin_headers = await _admin_auth(client, bot_token)
    await client.put("/api/v1/admin/games/config", headers=admin_headers, json={"diamond_rating_cap_enabled": False})

    user = await _register(client, db_session, 950017, bot_token)
    user_id = user.id
    diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=95)
    other_diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=60)
    diamond_card = await _give_card(db_session, user_id, diamond_player.id, 1)
    material_ids = await _give_n_cards(db_session, user_id, other_diamond_player.id, 10)

    headers = telegram_headers(950017, bot_token)
    resp = await client.post(
        "/api/v1/collection/diamond-upgrade/feed",
        headers=headers,
        json={"diamond_card_id": diamond_card.id, "material_card_ids": material_ids},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rating_gained"] == 1
    assert body["cards_consumed"] == 10
    assert body["diamond_card"]["player"]["rating"] == 96


async def test_extension_band_95_to_98_rejects_non_diamond_material(client, db_session, bot_token):
    admin_headers = await _admin_auth(client, bot_token)
    await client.put("/api/v1/admin/games/config", headers=admin_headers, json={"diamond_rating_cap_enabled": False})

    user = await _register(client, db_session, 950018, bot_token)
    user_id = user.id
    diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=95)
    legendary_player = await create_player(db_session, rarity=Rarity.legendary, rating=90)
    diamond_card = await _give_card(db_session, user_id, diamond_player.id, 1)
    material_ids = await _give_n_cards(db_session, user_id, legendary_player.id, 10)
    await _seed_tier(db_session, 90, 100, legendary=1)

    headers = telegram_headers(950018, bot_token)
    resp = await client.post(
        "/api/v1/collection/diamond-upgrade/feed",
        headers=headers,
        json={"diamond_card_id": diamond_card.id, "material_card_ids": material_ids},
    )
    assert resp.status_code == 409


async def test_extension_band_98_to_99_rejects_a_different_players_diamond_cards(client, db_session, bot_token):
    admin_headers = await _admin_auth(client, bot_token)
    await client.put("/api/v1/admin/games/config", headers=admin_headers, json={"diamond_rating_cap_enabled": False})

    user = await _register(client, db_session, 950019, bot_token)
    user_id = user.id
    diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=98)
    other_diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=60)
    diamond_card = await _give_card(db_session, user_id, diamond_player.id, 1)
    material_ids = await _give_n_cards(db_session, user_id, other_diamond_player.id, 10)

    headers = telegram_headers(950019, bot_token)
    resp = await client.post(
        "/api/v1/collection/diamond-upgrade/feed",
        headers=headers,
        json={"diamond_card_id": diamond_card.id, "material_card_ids": material_ids},
    )
    assert resp.status_code == 409


async def test_diamond_material_below_95_is_still_rejected_even_with_cap_disabled(client, db_session, bot_token):
    admin_headers = await _admin_auth(client, bot_token)
    await client.put("/api/v1/admin/games/config", headers=admin_headers, json={"diamond_rating_cap_enabled": False})

    user = await _register(client, db_session, 950020, bot_token)
    user_id = user.id
    diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=60)
    other_diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=60)
    diamond_card = await _give_card(db_session, user_id, diamond_player.id, 1)
    other_diamond_card = await _give_card(db_session, user_id, other_diamond_player.id, 1)
    await _seed_tier(db_session, 60, 70)

    headers = telegram_headers(950020, bot_token)
    resp = await client.post(
        "/api/v1/collection/diamond-upgrade/feed",
        headers=headers,
        json={"diamond_card_id": diamond_card.id, "material_card_ids": [other_diamond_card.id]},
    )
    assert resp.status_code == 409


async def test_material_cards_endpoint_returns_other_diamonds_for_the_95_to_98_band(client, db_session, bot_token):
    admin_headers = await _admin_auth(client, bot_token)
    await client.put("/api/v1/admin/games/config", headers=admin_headers, json={"diamond_rating_cap_enabled": False})

    user = await _register(client, db_session, 950021, bot_token)
    user_id = user.id
    diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=95)
    other_diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=60)
    diamond_card = await _give_card(db_session, user_id, diamond_player.id, 1)
    other_diamond_card = await _give_card(db_session, user_id, other_diamond_player.id, 1)

    headers = telegram_headers(950021, bot_token)
    resp = await client.get(
        "/api/v1/collection/diamond-upgrade/material-cards",
        headers=headers,
        params={"diamond_card_id": diamond_card.id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "any_diamond"
    assert body["cost"] == 10
    assert body["ceiling"] == 98
    assert [c["id"] for c in body["cards"]] == [other_diamond_card.id]


async def test_material_cards_endpoint_returns_only_same_player_cards_for_the_98_to_99_band(client, db_session, bot_token):
    admin_headers = await _admin_auth(client, bot_token)
    await client.put("/api/v1/admin/games/config", headers=admin_headers, json={"diamond_rating_cap_enabled": False})

    user = await _register(client, db_session, 950022, bot_token)
    user_id = user.id
    diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=98)
    other_diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=60)
    diamond_card = await _give_card(db_session, user_id, diamond_player.id, 1)
    duplicate_card = await _give_card(db_session, user_id, diamond_player.id, 2)
    await _give_card(db_session, user_id, other_diamond_player.id, 1)

    headers = telegram_headers(950022, bot_token)
    resp = await client.get(
        "/api/v1/collection/diamond-upgrade/material-cards",
        headers=headers,
        params={"diamond_card_id": diamond_card.id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "same_player_diamond"
    assert body["cost"] == 10
    assert body["ceiling"] == 99
    assert [c["id"] for c in body["cards"]] == [duplicate_card.id]


async def test_material_cards_endpoint_returns_empty_for_the_admin_tier_band(client, db_session, bot_token):
    user = await _register(client, db_session, 950023, bot_token)
    user_id = user.id
    diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=60)
    diamond_card = await _give_card(db_session, user_id, diamond_player.id, 1)

    headers = telegram_headers(950023, bot_token)
    resp = await client.get(
        "/api/v1/collection/diamond-upgrade/material-cards",
        headers=headers,
        params={"diamond_card_id": diamond_card.id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "admin_tier"
    assert body["cards"] == []


async def test_feed_is_rejected_at_the_default_95_rating_cap(client, db_session, bot_token):
    user = await _register(client, db_session, 950013, bot_token)
    user_id = user.id
    diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=95)
    legendary_player = await create_player(db_session, rarity=Rarity.legendary, rating=90)
    diamond_card = await _give_card(db_session, user_id, diamond_player.id, 1)
    material_ids = await _give_n_cards(db_session, user_id, legendary_player.id, 5)
    await _seed_tier(db_session, 90, 100, legendary=1)

    headers = telegram_headers(950013, bot_token)
    resp = await client.post(
        "/api/v1/collection/diamond-upgrade/feed",
        headers=headers,
        json={"diamond_card_id": diamond_card.id, "material_card_ids": material_ids},
    )
    assert resp.status_code == 409

    db_session.expire_all()
    remaining = (await db_session.execute(select(UserCard).where(UserCard.owner_id == user_id))).scalars().all()
    assert len(remaining) == 1 + 5


async def test_feed_gain_clamps_to_the_default_95_rating_cap(client, db_session, bot_token):
    user = await _register(client, db_session, 950014, bot_token)
    user_id = user.id
    diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=94)
    legendary_player = await create_player(db_session, rarity=Rarity.legendary, rating=90)
    diamond_card = await _give_card(db_session, user_id, diamond_player.id, 1)
    # 10 legendary cards, cost 1 each -> would be +10 uncapped, must clamp to +1 (94 -> 95).
    material_ids = await _give_n_cards(db_session, user_id, legendary_player.id, 10)
    await _seed_tier(db_session, 90, 100, legendary=1)

    headers = telegram_headers(950014, bot_token)
    resp = await client.post(
        "/api/v1/collection/diamond-upgrade/feed",
        headers=headers,
        json={"diamond_card_id": diamond_card.id, "material_card_ids": material_ids},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rating_gained"] == 1
    assert body["cards_consumed"] == 1
    assert body["cards_returned"] == 9
    assert body["diamond_card"]["player"]["rating"] == 95


async def test_a_card_already_above_the_cap_is_never_downgraded_but_cannot_feed_further(client, db_session, bot_token):
    """Mirrors a card that reached 99 before this cap existed (or after the
    cap was lowered) — feeding must refuse further gains without ever
    reducing diamond_rating_bonus."""
    user = await _register(client, db_session, 950015, bot_token)
    user_id = user.id
    diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=60)
    legendary_player = await create_player(db_session, rarity=Rarity.legendary, rating=90)
    diamond_card = await _give_card(db_session, user_id, diamond_player.id, 1)
    diamond_card_id = diamond_card.id
    diamond_card.diamond_rating_bonus = 39  # 60 + 39 = 99, already above the default 95 cap
    db_session.add(diamond_card)
    await db_session.commit()

    material_ids = await _give_n_cards(db_session, user_id, legendary_player.id, 5)
    await _seed_tier(db_session, 90, 100, legendary=1)

    headers = telegram_headers(950015, bot_token)
    resp = await client.post(
        "/api/v1/collection/diamond-upgrade/feed",
        headers=headers,
        json={"diamond_card_id": diamond_card_id, "material_card_ids": material_ids},
    )
    assert resp.status_code == 409

    db_session.expire_all()
    refreshed = await db_session.get(UserCard, diamond_card_id)
    assert refreshed.diamond_rating_bonus == 39


async def test_diamond_upgrade_cap_endpoint_reflects_config(client, db_session, bot_token):
    user_headers = telegram_headers(950016, bot_token)
    await client.post("/api/v1/auth/session", headers=user_headers)

    resp = await client.get("/api/v1/collection/diamond-upgrade-cap", headers=user_headers)
    assert resp.status_code == 200
    assert resp.json()["cap"] == 95

    admin_headers = await _admin_auth(client, bot_token)
    await client.put("/api/v1/admin/games/config", headers=admin_headers, json={"diamond_rating_cap_enabled": False})

    resp = await client.get("/api/v1/collection/diamond-upgrade-cap", headers=user_headers)
    assert resp.status_code == 200
    assert resp.json()["cap"] == 99


async def test_multiple_tiers_pick_the_band_matching_current_rating(client, db_session, bot_token):
    """Mirrors the real admin setup: 60-70 (10/5/3/1), 70-80 (15/8/5/2),
    80-90 (20/10/7/3) — a card at rating 75 must be charged the 70-80 band's
    costs, not 60-70's, and exactly that many cards must be required."""
    user = await _register(client, db_session, 950009, bot_token)
    user_id = user.id
    diamond_player = await create_player(db_session, rarity=Rarity.diamond, rating=75)
    epic_player = await create_player(db_session, rarity=Rarity.epic, rating=80)
    diamond_card = await _give_card(db_session, user_id, diamond_player.id, 1)
    await _seed_tier(db_session, 60, 70, common=10, rare=5, epic=3, legendary=1)
    await _seed_tier(db_session, 70, 80, common=15, rare=8, epic=5, legendary=2)
    await _seed_tier(db_session, 80, 90, common=20, rare=10, epic=7, legendary=3)

    headers = telegram_headers(950009, bot_token)

    # One short of the 70-80 band's epic cost (5) must be rejected...
    short_ids = await _give_n_cards(db_session, user_id, epic_player.id, 4)
    resp = await client.post(
        "/api/v1/collection/diamond-upgrade/feed",
        headers=headers,
        json={"diamond_card_id": diamond_card.id, "material_card_ids": short_ids},
    )
    assert resp.status_code == 409

    # ...but exactly 5 (the 70-80 band's epic cost, not 60-70's 3 or 80-90's 7) succeeds.
    extra_id = (await _give_card(db_session, user_id, epic_player.id, 5)).id
    resp = await client.post(
        "/api/v1/collection/diamond-upgrade/feed",
        headers=headers,
        json={"diamond_card_id": diamond_card.id, "material_card_ids": [*short_ids, extra_id]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rating_gained"] == 1
    assert body["cards_consumed"] == 5
    assert body["diamond_card"]["player"]["rating"] == 76


def test_effective_card_stats_scales_rating_and_stats_proportionally():
    diamond_player = type(
        "P", (), {"rating": 60, "attack_rating": 60, "defense_rating": 60, "rarity": Rarity.diamond}
    )()
    rating, attack, defense = effective_card_stats(diamond_player, 10)
    assert rating == 70
    # ratio 70/60 applied to both base stats (60 -> 70).
    assert attack == 70
    assert defense == 70


def test_leveled_up_diamond_card_raises_card_arena_team_strength():
    diamond_player = type(
        "P", (), {
            "rating": 60, "attack_rating": 60, "defense_rating": 60, "rarity": Rarity.diamond,
            "position": Position.ST, "club": "FC", "country": "Land",
        }
    )()
    card_base = type("C", (), {"player": diamond_player, "diamond_rating_bonus": 0})()
    card_leveled = type("C", (), {"player": diamond_player, "diamond_rating_bonus": 10})()

    slot = next(s for s in FORMATION_SLOTS if s.ideal_position == Position.ST)
    strength_base = calculate_base_strength([(card_base, slot)])
    strength_leveled = calculate_base_strength([(card_leveled, slot)])
    assert strength_leveled > strength_base


async def test_get_tiers_endpoint_returns_seeded_tiers(client, db_session, bot_token):
    await _register(client, db_session, 950008, bot_token)
    await _seed_tier(db_session, 60, 70)

    headers = telegram_headers(950008, bot_token)
    resp = await client.get("/api/v1/collection/diamond-upgrade-tiers", headers=headers)
    assert resp.status_code == 200
    tiers = resp.json()
    assert len(tiers) == 1
    assert tiers[0]["min_rating"] == 60
    assert tiers[0]["common_cost"] == 10
