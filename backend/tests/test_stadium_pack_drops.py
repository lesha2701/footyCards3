"""Stadium pack-drop integration — mirrors test_packs.py's/test_club_packs.py's
existing coach_drop_chance test coverage exactly, substituting Stadium for Coach.
See pack_service.roll_and_create_cards / club_pack_service.open_club_pack for the
shared-roll (coach checked first, then stadium) coin-flip this exercises."""

import pytest
import pytest_asyncio

import app.core.rate_limit as rate_limit_module
from app.core.exceptions import ConflictError
from app.models.club_pack import ClubPack, ClubPackRarityProbability
from app.models.enums import Position, Rarity
from app.models.stadium import Stadium
from tests.factories import create_pack, create_player
from tests.utils import telegram_headers


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    # Mirrors test_packs.py's identical fixture — open_pack is rate-limited
    # per user.id via an in-memory, process-global window that SQLite's
    # fresh-per-test DB does not reset.
    rate_limit_module._hits.clear()
    yield


async def _register(client, bot_token, telegram_id):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200


async def _create_club(client, bot_token, telegram_id, name):
    await _register(client, bot_token, telegram_id)
    headers = telegram_headers(telegram_id, bot_token)
    resp = await client.post(
        "/api/v1/clubs", headers=headers,
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    return resp.json(), headers


# --- Personal packs -------------------------------------------------------


async def test_open_pack_with_stadium_drop_chance_can_yield_a_stadium(client, db_session, bot_token):
    stadium = Stadium(display_name="Personal Slot Test Stadium", rarity=Rarity.common, is_active=True, is_pack_droppable=True, boost_pct=0.05)
    db_session.add(stadium)
    pack = await create_pack(
        db_session, "stadium-slot-personal-pack", price=50, card_count=5,
        probabilities={Rarity.common: 1.0}, coach_drop_chance=0.0, stadium_drop_chance=1.0,
    )

    await _register(client, bot_token, 830700)
    headers = telegram_headers(830700, bot_token)

    resp = await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={"idempotency_key": "stadium-slot-key-1"})
    assert resp.status_code == 200
    body = resp.json()
    # stadium_drop_chance=1.0, coach_drop_chance=0.0 -> every slot must resolve to a stadium.
    assert len(body["cards"]) == 0
    assert len(body.get("coach_cards", [])) == 0
    assert len(body["stadium_cards"]) == 5
    assert all(item["card"]["stadium"]["display_name"] == "Personal Slot Test Stadium" for item in body["stadium_cards"])
    assert all(item["card"]["stadium"]["id"] == stadium.id for item in body["stadium_cards"])
    # First copy of each is new; duplicates within the same opening are not.
    assert sum(1 for item in body["stadium_cards"] if item["is_new"]) == 1


async def test_open_pack_idempotent_replay_returns_same_stadium_cards(client, db_session, bot_token):
    """get_opening_result (the idempotent-replay path) must serialize
    stadium_cards identically to the fresh-open path."""
    stadium = Stadium(display_name="Replay Stadium", rarity=Rarity.common, is_active=True, is_pack_droppable=True)
    db_session.add(stadium)
    pack = await create_pack(
        db_session, "stadium-replay-pack", price=50, card_count=2,
        probabilities={Rarity.common: 1.0}, coach_drop_chance=0.0, stadium_drop_chance=1.0,
    )

    await _register(client, bot_token, 830701)
    headers = telegram_headers(830701, bot_token)

    first = await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={"idempotency_key": "stadium-replay-key"})
    second = await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={"idempotency_key": "stadium-replay-key"})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["opening_id"] == second.json()["opening_id"]
    assert len(first.json()["stadium_cards"]) == len(second.json()["stadium_cards"]) == 2
    assert [c["card"]["id"] for c in first.json()["stadium_cards"]] == [c["card"]["id"] for c in second.json()["stadium_cards"]]


async def test_open_pack_with_diamond_rarity_never_yields_a_stadium(client, db_session, bot_token):
    """`Stadium` has a DB check constraint forbidding `Rarity.diamond`, so even with
    stadium_drop_chance=1.0 a diamond-rarity slot must always resolve to a player —
    mirrors the identical coach diamond-rejection test."""
    stadium = Stadium(display_name="Should Never Appear Stadium", rarity=Rarity.common, is_active=True, is_pack_droppable=True)
    db_session.add(stadium)
    await create_player(db_session, rarity=Rarity.diamond, rating=95)
    pack = await create_pack(
        db_session, "diamond-stadium-personal-pack", price=50, card_count=5,
        probabilities={Rarity.diamond: 1.0}, coach_drop_chance=0.0, stadium_drop_chance=1.0,
    )

    await _register(client, bot_token, 830702)
    headers = telegram_headers(830702, bot_token)

    resp = await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={"idempotency_key": "diamond-stadium-key-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["stadium_cards"]) == 0
    assert len(body["cards"]) == 5
    assert all(item["card"]["player"]["rarity"] == "diamond" for item in body["cards"])


async def test_open_pack_shared_roll_splits_between_coach_and_stadium(client, db_session, bot_token):
    """The single shared `roll = random.random()` (checked coach first, then
    stadium) means coach_drop_chance=0.5, stadium_drop_chance=0.5 must cover
    every slot between the two — never a player — since the two chances sum
    to 1.0 and the roll is always < 1.0. A large card_count makes a false
    pass (every slot landing on the same kind) astronomically unlikely,
    mirroring test_club_packs.py's identical mid-range split test."""
    from app.models.coach import Coach, CoachBoost
    from app.models.enums import CoachBoostType

    coach = Coach(display_name="Shared Roll Coach", rarity=Rarity.common, is_active=True, is_pack_droppable=True)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=1.0)]
    db_session.add(coach)
    stadium = Stadium(display_name="Shared Roll Stadium", rarity=Rarity.common, is_active=True, is_pack_droppable=True)
    db_session.add(stadium)
    pack = await create_pack(
        db_session, "shared-roll-pack", price=50, card_count=40,
        probabilities={Rarity.common: 1.0}, coach_drop_chance=0.5, stadium_drop_chance=0.5,
    )

    await _register(client, bot_token, 830703)
    headers = telegram_headers(830703, bot_token)

    resp = await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={"idempotency_key": "shared-roll-key-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["cards"]) == 0, "coach_drop_chance + stadium_drop_chance == 1.0 must never leave room for a player"
    assert len(body["coach_cards"]) > 0
    assert len(body["stadium_cards"]) > 0
    assert len(body["coach_cards"]) + len(body["stadium_cards"]) == 40


async def test_pick_random_stadium_fallback_never_yields_a_higher_rarity(db_session):
    """Mirrors test_pick_random_coach_fallback_never_yields_a_higher_rarity:
    pick_random_stadium's "no stadium of the exact requested rarity" fallback
    must only ever draw a stadium at or below the requested rarity, never
    reach upward to a rarer (structurally more valuable) one."""
    from app.services.pack_service import pick_random_stadium

    stadium = Stadium(display_name="Only Legendary Stadium", rarity=Rarity.legendary, is_active=True, is_pack_droppable=True)
    db_session.add(stadium)
    await db_session.commit()

    with pytest.raises(ConflictError):
        await pick_random_stadium(db_session, Rarity.common)


# --- Club packs -------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    # Mirrors test_club_packs.py's identical fixture: club_service.create_club
    # seeds a starting squad on every club creation, so every club test here
    # needs enough active players per formation category to draw from.
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def test_open_club_pack_with_stadium_drop_chance_can_yield_a_stadium(client, db_session, bot_token):
    stadium = Stadium(display_name="Club Slot Test Stadium", rarity=Rarity.common, is_active=True, is_pack_droppable=True)
    db_session.add(stadium)

    pack = ClubPack(slug="stadium-slot-club-pack", name="Stadium Slot Pack", price=50, card_count=5, coach_drop_chance=0.0, stadium_drop_chance=1.0)
    pack.rarity_probabilities = [ClubPackRarityProbability(rarity=Rarity.common, probability=1.0)]
    db_session.add(pack)
    await db_session.commit()
    await db_session.refresh(pack)

    club, headers = await _create_club(client, bot_token, 830710, "Клуб со стадионными слотами")
    await client.post("/api/v1/clubs/me/daily-claim", headers=headers)

    resp = await client.post(f"/api/v1/clubs/me/packs/{pack.id}/open", headers=headers, json={"idempotency_key": "club-stadium-slot-key-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["cards"]) == 5
    assert all(item["kind"] == "stadium" for item in body["cards"])
    assert all(item["stadium_card"]["stadium"]["display_name"] == "Club Slot Test Stadium" for item in body["cards"])
    assert all(item["card"] is None and item["coach_card"] is None for item in body["cards"])


async def test_open_club_pack_with_diamond_rarity_never_yields_a_stadium(client, db_session, bot_token):
    stadium = Stadium(display_name="Should Never Be Drawn Stadium", rarity=Rarity.common, is_active=True, is_pack_droppable=True)
    db_session.add(stadium)
    await create_player(db_session, rarity=Rarity.diamond, position=Position.ST)

    pack = ClubPack(slug="diamond-stadium-club-pack", name="Diamond Stadium Pack", price=50, card_count=5, coach_drop_chance=0.0, stadium_drop_chance=1.0)
    pack.rarity_probabilities = [ClubPackRarityProbability(rarity=Rarity.diamond, probability=1.0)]
    db_session.add(pack)
    await db_session.commit()
    await db_session.refresh(pack)

    club, headers = await _create_club(client, bot_token, 830711, "Клуб с бриллиантовыми стадионами")
    await client.post("/api/v1/clubs/me/daily-claim", headers=headers)

    resp = await client.post(f"/api/v1/clubs/me/packs/{pack.id}/open", headers=headers, json={"idempotency_key": "club-diamond-stadium-key-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["cards"]) == 5
    assert all(item["kind"] == "player" for item in body["cards"])
    assert all(item["card"]["player"]["rarity"] == "diamond" for item in body["cards"])
    assert all(item["stadium_card"] is None for item in body["cards"])


async def test_open_club_pack_shared_roll_splits_between_coach_and_stadium(client, db_session, bot_token):
    from app.models.coach import Coach, CoachBoost
    from app.models.enums import CoachBoostType

    coach = Coach(display_name="Club Shared Roll Coach", rarity=Rarity.common, is_active=True, is_pack_droppable=True)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=1.0)]
    db_session.add(coach)
    stadium = Stadium(display_name="Club Shared Roll Stadium", rarity=Rarity.common, is_active=True, is_pack_droppable=True)
    db_session.add(stadium)

    pack = ClubPack(slug="club-shared-roll-pack", name="Club Shared Roll Pack", price=50, card_count=40, coach_drop_chance=0.5, stadium_drop_chance=0.5)
    pack.rarity_probabilities = [ClubPackRarityProbability(rarity=Rarity.common, probability=1.0)]
    db_session.add(pack)
    await db_session.commit()
    await db_session.refresh(pack)

    club, headers = await _create_club(client, bot_token, 830712, "Клуб с общим броском")
    await client.post("/api/v1/clubs/me/daily-claim", headers=headers)

    resp = await client.post(f"/api/v1/clubs/me/packs/{pack.id}/open", headers=headers, json={"idempotency_key": "club-shared-roll-key-1"})
    assert resp.status_code == 200
    body = resp.json()
    kinds = [item["kind"] for item in body["cards"]]
    assert "player" not in kinds, "coach_drop_chance + stadium_drop_chance == 1.0 must never leave room for a player"
    assert set(kinds) == {"coach", "stadium"}, f"expected both bonus kinds among 40 slots, got {set(kinds)}"
