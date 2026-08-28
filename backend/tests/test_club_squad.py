import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.exceptions import ConflictError
from app.models.club import Club
from app.models.club_lineup import ClubLineup, ClubLineupCard
from app.models.enums import ClubLogoShape, ClubType, Position
from app.models.user import User
from app.schemas.club import ClubCreate
from app.schemas.club_squad import ClubLineupSetRequest, ClubLineupSlotIn
from app.services import club_service
from app.services.club_squad_service import set_club_lineup
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

# See test_club_packs.py's REAL_POSTGRES_URL comment for why this test opens its own
# independent connection to the real dev Postgres instance rather than using the pytest
# suite's `client`/`db_session` fixtures (hardcoded to in-memory SQLite, single shared
# connection, can't reproduce genuine multi-connection unique-constraint race timing).
REAL_POSTGRES_URL = os.environ.get("REAL_POSTGRES_URL", "postgresql+asyncpg://postgres:1234@postgres:5432/footycards")


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """club_service.create_club seeds a starting squad on every club
    creation (Task 4) — give every test in this file enough active players
    per formation category (GK/DEF/MID/FWD) to draw from. Unlike
    test_clubs.py, this file has no other autouse fixture doing this —
    autouse fixtures are file-scoped in this codebase's test setup, so it
    must be repeated here (fresh SQLite schema per test, see conftest.py's
    `_fresh_schema`)."""
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
    assert resp.status_code == 200
    return resp.json(), headers


async def test_get_club_lineup_is_complete_after_creation(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820300, "Клуб с готовым составом")
    resp = await client.get("/api/v1/clubs/me/lineup", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_complete"] is True
    assert body["team_strength"] is not None
    assert len(body["slots"]) == 11
    assert all(s["card"] is not None for s in body["slots"])


async def test_list_club_cards_includes_bench(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820301, "Клуб со скамейкой")
    resp = await client.get("/api/v1/clubs/me/cards", headers=headers)
    assert resp.status_code == 200
    cards = resp.json()
    assert len(cards) == 15
    assert sum(1 for c in cards if not c["is_in_lineup"]) == 4


CATEGORY_POSITIONS_FOR_TEST = {
    "GK": {"GK"}, "DEF": {"LB", "CB", "RB"}, "MID": {"CDM", "CM", "CAM", "LM", "RM"}, "FWD": {"LW", "ST", "RW"},
}


def _category_for_position(position: str) -> str:
    return next(category for category, positions in CATEGORY_POSITIONS_FOR_TEST.items() if position in positions)


async def test_set_club_lineup_swaps_a_bench_card_into_a_slot(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820302, "Клуб с заменой")
    cards = (await client.get("/api/v1/clubs/me/cards", headers=headers)).json()
    bench_card = next(c for c in cards if not c["is_in_lineup"])
    bench_category = _category_for_position(bench_card["player"]["position"])
    lineup = (await client.get("/api/v1/clubs/me/lineup", headers=headers)).json()

    # Every club is seeded with exactly one bench card per category and one
    # starter per formation slot within that same category, so there is
    # always at least one legal target slot — same category, any slot.
    matching_slot = next(s for s in lineup["slots"] if s["category"] == bench_category)
    slots_payload = [
        {"slot_code": s["slot_code"], "club_card_id": bench_card["id"] if s["slot_code"] == matching_slot["slot_code"] else s["card"]["id"]}
        for s in lineup["slots"]
    ]
    resp = await client.put("/api/v1/clubs/me/lineup", headers=headers, json={"slots": slots_payload})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_complete"] is True

    # Regression check for the identity-map staleness bug fixed alongside
    # this test: the PUT response itself (not just a subsequent GET) must
    # reflect the just-swapped card in its slot. With expire_on_commit=False
    # (see database.py), a re-read missing populate_existing=True can
    # silently return the session's pre-swap cached ClubLineup object.
    put_slot = next(s for s in body["slots"] if s["slot_code"] == matching_slot["slot_code"])
    assert put_slot["card"]["id"] == bench_card["id"]


async def test_non_manager_cannot_set_lineup(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820303, "Клуб без прав")
    await _register_only(client, bot_token, 820304)
    member_headers = telegram_headers(820304, bot_token)
    await client.post(f"/api/v1/clubs/{club['id']}/join", headers=member_headers)

    lineup = (await client.get("/api/v1/clubs/me/lineup", headers=member_headers)).json()
    slots_payload = [{"slot_code": s["slot_code"], "club_card_id": s["card"]["id"]} for s in lineup["slots"]]
    resp = await client.put("/api/v1/clubs/me/lineup", headers=member_headers, json={"slots": slots_payload})
    assert resp.status_code == 403


async def test_set_lineup_concurrent_saves_no_unhandled_integrity_error():
    """Genuine concurrency regression test for an unhandled IntegrityError observed in
    production as a 500 on PUT /clubs/me/lineup: set_club_lineup's with_for_update(of=ClubLineup)
    lock serializes overlapping saves once each one's SELECT resolves, but two truly concurrent
    submissions (asyncio.gather) didn't reliably reproduce the crash — it took a wider fan-out to
    expose reliably, matching how the reported bug surfaced under real load (a slow/hanging save
    inviting repeated taps). With 6 concurrent identical saves against real Postgres, some
    interleave around the delete-then-recreate of club_lineup_cards and collide on
    uq_club_lineup_card_once. Before the fix this raised a raw IntegrityError (500); after, the
    loser(s) get a clean ConflictError (409) instead. Skips if real Postgres is unreachable.
    """
    engine = create_async_engine(REAL_POSTGRES_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except OSError as exc:
        await engine.dispose()
        pytest.skip(f"real dev Postgres not reachable at {REAL_POSTGRES_URL!r}: {exc!r}")
    except OperationalError as exc:
        await engine.dispose()
        pytest.skip(f"real dev Postgres not reachable at {REAL_POSTGRES_URL!r}: {exc!r}")

    RealSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]

    setup = RealSessionLocal()
    captain = club_id = None
    try:
        captain = User(telegram_id=991_300_000_000 + uuid.uuid4().int % 1_000_000_000, username=f"lineup_race_{suffix}", balance=10000)
        setup.add(captain)
        await setup.flush()
        await setup.commit()

        detail = await club_service.create_club(
            setup, captain,
            ClubCreate(name=f"Lineup Race Club {suffix}", description="", club_type=ClubType.open, logo_shape=ClubLogoShape.shield, logo_color="#abcdef"),
        )
        club_id = detail.id
        await setup.close()
        setup = None

        async with RealSessionLocal() as verify:
            lineup = (await verify.execute(select(ClubLineup).where(ClubLineup.club_id == club_id))).scalar_one()
            cards = (await verify.execute(select(ClubLineupCard).where(ClubLineupCard.club_lineup_id == lineup.id))).scalars().all()
            slot_to_card = {c.slot_code: c.club_card_id for c in cards}

        payload = ClubLineupSetRequest(slots=[ClubLineupSlotIn(slot_code=code, club_card_id=cid) for code, cid in slot_to_card.items()])

        concurrency = 6
        sessions = [RealSessionLocal() for _ in range(concurrency)]
        try:
            captains = [await s.get(User, captain.id) for s in sessions]
            results = await asyncio.gather(
                *[set_club_lineup(sessions[i], captains[i], payload) for i in range(concurrency)],
                return_exceptions=True,
            )
        finally:
            for s in sessions:
                await s.close()

        successes = [r for r in results if not isinstance(r, BaseException)]
        failures = [r for r in results if isinstance(r, BaseException)]
        assert successes, f"expected at least one winner, got results: {results!r}"
        for f in failures:
            assert isinstance(f, ConflictError), f"every loser must raise ConflictError (409), not an unhandled exception: {f!r}"

        async with RealSessionLocal() as final_verify:
            final_lineup = (await final_verify.execute(select(ClubLineup).where(ClubLineup.club_id == club_id))).scalar_one()
            final_cards = (
                await final_verify.execute(select(ClubLineupCard).where(ClubLineupCard.club_lineup_id == final_lineup.id))
            ).scalars().all()
            assert len(final_cards) == 11, "lineup must end with exactly 11 cards, not duplicated or partially deleted"
    finally:
        async with RealSessionLocal() as cleanup:
            if club_id is not None:
                club_row = await cleanup.get(Club, club_id)
                if club_row is not None:
                    await cleanup.delete(club_row)
            await cleanup.commit()
            if captain is not None:
                user_row = await cleanup.get(User, captain.id)
                if user_row is not None:
                    await cleanup.delete(user_row)
            await cleanup.commit()
        if setup is not None:
            await setup.close()
        await engine.dispose()
