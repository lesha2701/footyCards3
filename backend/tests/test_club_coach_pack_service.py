import pytest_asyncio

from app.models.coach import Coach, CoachBoost
from app.models.enums import CoachBoostType, Position, Rarity
from app.services.pack_service import pick_random_coach
from tests.factories import create_player
from tests.utils import telegram_headers


async def test_pick_random_coach_respects_rarity_and_droppable_flags(db_session):
    droppable = Coach(display_name="Droppable", rarity=Rarity.common, is_active=True, is_pack_droppable=True)
    droppable.boosts = [CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=2.0)]
    not_droppable = Coach(display_name="Retired", rarity=Rarity.common, is_active=True, is_pack_droppable=False)
    not_droppable.boosts = [CoachBoost(boost_type=CoachBoostType.BALL_CONTROL, magnitude=1.0)]
    db_session.add_all([droppable, not_droppable])
    await db_session.commit()

    for _ in range(10):
        picked = await pick_random_coach(db_session, Rarity.common)
        assert picked.id == droppable.id


# --- Router-level tests for open_club_coach_pack, mirroring test_club_packs.py's
# fixture/setup pattern exactly (admin auth, club creation via the API, funding via
# the daily claim) since there's no admin router yet (that's a later task) to create
# club coach packs through the API — this file seeds them directly via the ORM instead.


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """club_service.create_club seeds a starting squad on every club creation, so give
    every test in this file enough active players per formation category (GK/DEF/MID/FWD)
    to draw from — copied verbatim from test_club_packs.py's own autouse fixture, since
    autouse fixtures are file-scoped in this codebase's test setup."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _register_only(client, bot_token, telegram_id):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200


async def _create_club(client, bot_token, telegram_id, name):
    await _register_only(client, bot_token, telegram_id)
    headers = telegram_headers(telegram_id, bot_token)
    resp = await client.post(
        "/api/v1/clubs", headers=headers,
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    return resp.json(), headers


async def _seed_coach_pack(db_session, slug: str, price: int, card_count: int = 1, coach_count: int = 1):
    from app.models.club_coach_pack import ClubCoachPack, ClubCoachPackRarityProbability

    for i in range(coach_count):
        coach = Coach(display_name=f"Coach {slug} {i}", rarity=Rarity.common, is_active=True, is_pack_droppable=True)
        coach.boosts = [CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=1.0)]
        db_session.add(coach)

    pack = ClubCoachPack(slug=slug, name=f"Pack {slug}", price=price, card_count=card_count, is_active=True)
    pack.rarity_probabilities = [ClubCoachPackRarityProbability(rarity=Rarity.common, probability=1.0)]
    db_session.add(pack)
    await db_session.commit()
    await db_session.refresh(pack)
    return pack


async def test_open_club_coach_pack_debits_budget_and_grants_coach(client, db_session, bot_token):
    pack = await _seed_coach_pack(db_session, "coach-test-pack", price=100, card_count=2, coach_count=2)

    club, headers = await _create_club(client, bot_token, 830400, "Клуб с тренерами")
    # Fund the club via the daily claim (200 coins by default) — enough for one 100-coin pack.
    await client.post("/api/v1/clubs/me/daily-claim", headers=headers)

    open_resp = await client.post(
        f"/api/v1/clubs/me/coach-packs/{pack.id}/open", headers=headers, json={"idempotency_key": "coach-key-1"}
    )
    assert open_resp.status_code == 200
    body = open_resp.json()
    assert body["new_budget"] == 100  # 200 - 100
    assert len(body["cards"]) == 2
    # Not asserting on `is_new` here: with only 2 coaches in the pool and 2
    # independent (with-replacement) draws, both cards can legitimately land
    # on the same coach — `pick_random_coach` doesn't guarantee distinct
    # picks within one opening, matching pick_random_player's own behavior.
    assert all(card["card"]["coach"]["id"] is not None for card in body["cards"])


async def test_open_club_coach_pack_idempotency_key_prevents_double_charge(client, db_session, bot_token):
    pack = await _seed_coach_pack(db_session, "coach-idem-pack", price=50, card_count=1)

    club, headers = await _create_club(client, bot_token, 830401, "Клуб с идемпотентностью тренеров")
    await client.post("/api/v1/clubs/me/daily-claim", headers=headers)

    first = await client.post(f"/api/v1/clubs/me/coach-packs/{pack.id}/open", headers=headers, json={"idempotency_key": "same-coach-key"})
    second = await client.post(f"/api/v1/clubs/me/coach-packs/{pack.id}/open", headers=headers, json={"idempotency_key": "same-coach-key"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["new_budget"] == second.json()["new_budget"]
    # Compare card ids (not the full payload) — `acquired_at` can legitimately
    # round-trip with/without a trailing "Z" between the freshly-created,
    # still-in-memory object on the first request (tz-aware) and the one
    # re-read from the (SQLite, in this test suite) DB on the idempotent-
    # replay path (naive) — a pre-existing SQLite-only quirk, not a bug in
    # the replay logic itself, matching test_club_packs.py's own idempotency
    # test which likewise avoids comparing full card payloads.
    assert [c["card"]["id"] for c in first.json()["cards"]] == [c["card"]["id"] for c in second.json()["cards"]]

    club_detail = await client.get("/api/v1/clubs/me", headers=headers)
    assert club_detail.json()["budget"] == 150  # only debited once: 200 - 50, not 200 - 100
