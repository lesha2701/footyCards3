import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.club import Club, ClubMember
from app.models.club_pack import ClubPack, ClubPackRarityProbability
from app.models.enums import ClubLogoShape, ClubRole, ClubType, Position, Rarity
from app.models.user import User
from app.services.club_pack_service import open_club_pack
from tests.factories import create_player
from tests.utils import telegram_headers

# The pytest suite's own `client`/`db_session` fixtures (tests/conftest.py) hardcode
# DATABASE_URL to in-memory SQLite for every test, unconditionally overwriting whatever
# real DATABASE_URL the process actually started with (verified: even inside the
# `docker compose exec backend pytest ...` container, whose env really does point at the
# dev Postgres instance, `tests.conftest.engine.url` is still `sqlite+aiosqlite://`).
# A genuine two-independent-connection race additionally can't be reproduced against that
# SQLite DB at all: it uses a single shared StaticPool connection, so two "concurrent"
# AsyncSessions end up fighting over one physical DBAPI connection and raise an unrelated
# greenlet/threading error instead of exercising Postgres's real unique-constraint timing.
# So this test opens its own independent connection straight to the real dev Postgres
# instance (matching docker-compose.yml's/.env.example's default credentials, overridable
# via REAL_POSTGRES_URL) and skips gracefully if that instance isn't reachable — this is
# the same "verify manually against real Postgres" real-DB check CLAUDE.md calls for with
# row-locking-sensitive changes, just written as a permanent, self-cleaning regression test.
REAL_POSTGRES_URL = os.environ.get("REAL_POSTGRES_URL", "postgresql+asyncpg://postgres:1234@postgres:5432/footycards")


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """club_service.create_club seeds a starting squad on every club
    creation (Task 4) — give every test in this file enough active players
    per formation category (GK/DEF/MID/FWD) to draw from. autouse fixtures
    are file-scoped in this codebase's test setup (see test_clubs.py and
    test_club_squad.py precedent), so it must be repeated here rather than
    relying on the per-test inline `create_player` calls below, which only
    seed generic ST/common players for the pack's own rarity rolls and are
    not enough to cover every formation slot's required positions (fresh
    SQLite schema per test, see conftest.py's `_fresh_schema`)."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _admin_auth(client, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    return {"Authorization": f"Bearer {session_resp.json()['admin_token']}"}


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


async def test_open_club_pack_debits_budget_and_mints_cards(client, db_session, bot_token):
    admin_auth = await _admin_auth(client, bot_token)
    for _ in range(5):
        await create_player(db_session)
    pack_resp = await client.post(
        "/api/v1/admin/club-packs", headers=admin_auth,
        json={
            "slug": "club-test-pack", "name": "Тестовый клубный пак", "price": 100, "card_count": 2,
            "rarity_probabilities": [{"rarity": "common", "probability": 1.0}],
        },
    )
    pack_id = pack_resp.json()["id"]

    club, headers = await _create_club(client, bot_token, 820400, "Клуб с паками")
    # Give the club enough budget via the daily claim (200 coins by default) — not enough
    # for a 100-coin pack twice, but enough to open once and verify the debit.
    await client.post("/api/v1/clubs/me/daily-claim", headers=headers)

    open_resp = await client.post(f"/api/v1/clubs/me/packs/{pack_id}/open", headers=headers, json={"idempotency_key": "test-key-1"})
    assert open_resp.status_code == 200
    body = open_resp.json()
    assert body["new_budget"] == 100  # 200 - 100
    assert len(body["cards"]) == 2

    cards_resp = await client.get("/api/v1/clubs/me/cards", headers=headers)
    assert len(cards_resp.json()) == 17  # 15 starting + 2 from the pack


async def test_open_club_pack_idempotency_key_prevents_double_charge(client, db_session, bot_token):
    admin_auth = await _admin_auth(client, bot_token)
    for _ in range(5):
        await create_player(db_session)
    pack_resp = await client.post(
        "/api/v1/admin/club-packs", headers=admin_auth,
        json={
            "slug": "club-idem-pack", "name": "Идемпотентный пак", "price": 50, "card_count": 1,
            "rarity_probabilities": [{"rarity": "common", "probability": 1.0}],
        },
    )
    pack_id = pack_resp.json()["id"]
    club, headers = await _create_club(client, bot_token, 820401, "Клуб с идемпотентностью")
    await client.post("/api/v1/clubs/me/daily-claim", headers=headers)

    first = await client.post(f"/api/v1/clubs/me/packs/{pack_id}/open", headers=headers, json={"idempotency_key": "same-key"})
    second = await client.post(f"/api/v1/clubs/me/packs/{pack_id}/open", headers=headers, json={"idempotency_key": "same-key"})
    assert first.json()["opening_id"] == second.json()["opening_id"]
    assert first.json()["new_budget"] == second.json()["new_budget"]


async def test_open_club_pack_fails_on_insufficient_budget(client, db_session, bot_token):
    admin_auth = await _admin_auth(client, bot_token)
    for _ in range(5):
        await create_player(db_session)
    pack_resp = await client.post(
        "/api/v1/admin/club-packs", headers=admin_auth,
        json={
            "slug": "club-expensive-pack", "name": "Дорогой пак", "price": 999999, "card_count": 1,
            "rarity_probabilities": [{"rarity": "common", "probability": 1.0}],
        },
    )
    pack_id = pack_resp.json()["id"]
    club, headers = await _create_club(client, bot_token, 820402, "Бедный клуб")

    resp = await client.post(f"/api/v1/clubs/me/packs/{pack_id}/open", headers=headers, json={})
    assert resp.status_code == 400


async def test_open_club_pack_requires_manager_role(client, db_session, bot_token):
    """Symmetric to test_club_squad.py's test_non_manager_cannot_set_lineup — pack opening is
    the other manager-gated, budget-spending club route, and arguably the highest-value one to
    guard (a plain member could otherwise drain the whole club budget)."""
    admin_auth = await _admin_auth(client, bot_token)
    for _ in range(5):
        await create_player(db_session)
    pack_resp = await client.post(
        "/api/v1/admin/club-packs", headers=admin_auth,
        json={
            "slug": "club-manager-gate-pack", "name": "Пак под защитой", "price": 50, "card_count": 1,
            "rarity_probabilities": [{"rarity": "common", "probability": 1.0}],
        },
    )
    pack_id = pack_resp.json()["id"]

    club, captain_headers = await _create_club(client, bot_token, 820403, "Клуб без прав на паки")
    await client.post("/api/v1/clubs/me/daily-claim", headers=captain_headers)

    await _register_only(client, bot_token, 820404)
    member_headers = telegram_headers(820404, bot_token)
    await client.post(f"/api/v1/clubs/{club['id']}/join", headers=member_headers)

    resp = await client.post(f"/api/v1/clubs/me/packs/{pack_id}/open", headers=member_headers, json={})
    assert resp.status_code == 403

    club_detail = await client.get("/api/v1/clubs/me", headers=captain_headers)
    assert club_detail.json()["budget"] == 200  # unchanged: the daily-claim credit, no pack debit


async def test_open_club_pack_concurrent_same_idempotency_key_no_double_debit():
    """Genuine concurrency regression test for the flush-time IntegrityError bug: two truly
    concurrent open_club_pack calls (asyncio.gather, two independent DB sessions/connections)
    with the same idempotency_key both pass the pre-check SELECT before either commits, so both
    attempt the INSERT into club_pack_openings. Postgres enforces the unique constraint on
    (club_id, idempotency_key) at INSERT/flush time, not at COMMIT time — so, before the fix, the
    losing call's `await db.flush()` (which sat outside the try/except IntegrityError block)
    raised an unhandled exception instead of falling back to the winner's result. This differs
    from test_open_club_pack_idempotency_key_prevents_double_charge above, which only issues two
    *sequential* HTTP requests — the second request's pre-check always finds the first request's
    already-committed row and returns early, never reaching `db.flush()`, so it can't catch this
    bug. Runs against real Postgres (see REAL_POSTGRES_URL above) — skips if unreachable.
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
    user = club_id = pack_id = None
    user_id = None
    try:
        user = User(telegram_id=990_000_000_000 + uuid.uuid4().int % 1_000_000_000, username=f"race_{suffix}")
        setup.add(user)
        await setup.flush()

        club = Club(
            name=f"Race Club {suffix}", club_type=ClubType.open, logo_shape=ClubLogoShape.shield,
            logo_color="#123456", captain_id=user.id, invite_code=f"race{suffix}"[:16], budget=200,
        )
        setup.add(club)
        await setup.flush()

        setup.add(ClubMember(club_id=club.id, user_id=user.id, role=ClubRole.captain))

        pack = ClubPack(slug=f"race-pack-{suffix}", name="Гоночный пак (race test)", price=50, card_count=1, is_active=True)
        setup.add(pack)
        await setup.flush()
        setup.add(ClubPackRarityProbability(club_pack_id=pack.id, rarity=Rarity.common, probability=1.0))

        await setup.commit()
        user_id, club_id, pack_id = user.id, club.id, pack.id

        session_a = RealSessionLocal()
        session_b = RealSessionLocal()
        try:
            user_a = await session_a.get(User, user_id)
            user_b = await session_b.get(User, user_id)

            results = await asyncio.gather(
                open_club_pack(session_a, user_a, pack_id, "race-key"),
                open_club_pack(session_b, user_b, pack_id, "race-key"),
                return_exceptions=True,
            )
        finally:
            await session_a.close()
            await session_b.close()

        for result in results:
            assert not isinstance(result, BaseException), f"open_club_pack raised instead of handling the race: {result!r}"

        opening_ids = {result.opening_id for result in results}
        assert len(opening_ids) == 1, "both concurrent callers must resolve to the same winning opening"

        budgets = {result.new_budget for result in results}
        assert budgets == {150}, f"expected a single 50-coin debit from the 200-coin starting budget, got {budgets}"

        async with RealSessionLocal() as verify:
            final_club = await verify.get(Club, club_id)
            assert final_club.budget == 150, "club budget must reflect exactly one debit, not two"
    finally:
        # Self-cleaning: this test writes real rows into the shared dev Postgres instance, so
        # tear everything it created back down regardless of pass/fail. Deleting the club first
        # cascades club_members/club_pack_openings/club_pack_opening_cards/club_cards/
        # club_budget_transactions (all ondelete="CASCADE" on club_id/opening_id); the pack and
        # user are deleted afterwards since nothing still references them at that point.
        async with RealSessionLocal() as cleanup:
            if club_id is not None:
                club_row = await cleanup.get(Club, club_id)
                if club_row is not None:
                    await cleanup.delete(club_row)
            if pack_id is not None:
                pack_row = await cleanup.get(ClubPack, pack_id)
                if pack_row is not None:
                    await cleanup.delete(pack_row)
            await cleanup.commit()
            if user is not None and user_id is not None:
                user_row = await cleanup.get(User, user_id)
                if user_row is not None:
                    await cleanup.delete(user_row)
                    await cleanup.commit()
        await setup.close()
        await engine.dispose()
