import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.club import Club
from app.models.club_pack import ClubPack, ClubPackRarityProbability
from app.models.club_pack_opening import ClubPackOpening
from app.models.enums import ClubLogoShape, ClubType, Rarity
from app.models.user import User
from app.routers.admin_club_packs import delete_club_pack
from tests.utils import telegram_headers

# See test_club_packs.py's REAL_POSTGRES_URL comment for why this test opens its own
# independent connection to the real dev Postgres instance rather than using the pytest
# suite's `client`/`db_session` fixtures (hardcoded to in-memory SQLite, which doesn't
# enforce foreign-key constraints by default and so can't catch a missing ON DELETE CASCADE).
REAL_POSTGRES_URL = os.environ.get("REAL_POSTGRES_URL", "postgresql+asyncpg://postgres:1234@postgres:5432/footycards")


class _NullRequest:
    """Stand-in for FastAPI's Request when calling a router function directly (not through
    FastAPI's own dispatch) — the handler only ever touches `request.client.host if
    request.client else None`, so a bare `client = None` attribute is enough."""
    client = None


async def _admin_auth(client, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    token = session_resp.json()["admin_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_create_club_pack_requires_probabilities_summing_to_one(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    resp = await client.post(
        "/api/v1/admin/club-packs", headers=auth,
        json={
            "slug": "club-basic", "name": "Клубный базовый", "price": 500, "card_count": 3,
            "rarity_probabilities": [{"rarity": "common", "probability": 0.5}],
        },
    )
    assert resp.status_code == 409


async def test_create_and_update_club_pack(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    create_resp = await client.post(
        "/api/v1/admin/club-packs", headers=auth,
        json={
            "slug": "club-premium", "name": "Клубный премиум", "price": 1000, "card_count": 3,
            "rarity_probabilities": [
                {"rarity": "common", "probability": 0.6}, {"rarity": "rare", "probability": 0.3}, {"rarity": "epic", "probability": 0.1},
            ],
        },
    )
    assert create_resp.status_code == 200
    pack_id = create_resp.json()["id"]
    assert len(create_resp.json()["rarity_probabilities"]) == 3

    update_resp = await client.put(f"/api/v1/admin/club-packs/{pack_id}", headers=auth, json={"price": 1500})
    assert update_resp.status_code == 200
    assert update_resp.json()["price"] == 1500

    toggle_resp = await client.post(f"/api/v1/admin/club-packs/{pack_id}/toggle-active", headers=auth)
    assert toggle_resp.json()["is_active"] is False

    list_resp = await client.get("/api/v1/admin/club-packs", headers=auth)
    assert any(p["id"] == pack_id for p in list_resp.json())

    delete_resp = await client.delete(f"/api/v1/admin/club-packs/{pack_id}", headers=auth)
    assert delete_resp.status_code == 204


async def test_delete_club_pack_with_prior_opening_cascades():
    """Regression test for finding 5: club_pack_openings.club_pack_id previously had no
    ondelete on its FK, so deleting a club pack that had ever been opened raised an unhandled
    Postgres FK-violation 500 instead of succeeding. The pytest suite's default `client`/
    `db_session` fixtures run against in-memory SQLite, which doesn't enforce FK constraints
    by default and so can't catch this — this test opens its own connection to the real dev
    Postgres instance instead (skips gracefully if unreachable), mints a real ClubPackOpening
    row referencing the pack, then calls the admin delete endpoint's handler function directly
    and asserts it succeeds and that the opening row is actually gone (cascade took effect).
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
    user_id = club_id = pack_id = opening_id = None
    try:
        user = User(telegram_id=992_000_000_000 + uuid.uuid4().int % 1_000_000_000, username=f"admin_delete_{suffix}", is_admin=True)
        setup.add(user)
        await setup.flush()

        club = Club(
            name=f"Delete Test Club {suffix}", club_type=ClubType.open, logo_shape=ClubLogoShape.shield,
            logo_color="#abcdef", captain_id=user.id, invite_code=f"del{suffix}"[:16], budget=1000,
        )
        setup.add(club)
        await setup.flush()

        pack = ClubPack(slug=f"delete-pack-{suffix}", name="Пак для удаления", price=50, card_count=1, is_active=True)
        setup.add(pack)
        await setup.flush()
        setup.add(ClubPackRarityProbability(club_pack_id=pack.id, rarity=Rarity.common, probability=1.0))
        await setup.flush()

        opening = ClubPackOpening(club_id=club.id, club_pack_id=pack.id, opened_by_user_id=user.id, price_paid=pack.price, idempotency_key=None)
        setup.add(opening)
        await setup.commit()

        # Captured as plain ints (not attribute accesses on the ORM objects) before the
        # possibly-failing call below — if delete_club_pack's commit fails, every ORM object
        # still attached to this `setup` session is expired, and a bare (non-awaited)
        # attribute access on an expired object outside SQLAlchemy's own async call plumbing
        # raises instead of lazy-loading. Same reasoning as open_club_pack's `club_id`
        # capture (club_pack_service.py) and claim_daily_reward's (club_service.py).
        user_id, club_id, pack_id, opening_id = user.id, club.id, pack.id, opening.id

        await delete_club_pack(pack_id, _NullRequest(), db=setup, admin=user)

        async with RealSessionLocal() as verify:
            remaining_opening = await verify.get(ClubPackOpening, opening_id)
            assert remaining_opening is None, "ClubPackOpening row must be cascade-deleted along with its ClubPack"
            remaining_pack = await verify.get(ClubPack, pack_id)
            assert remaining_pack is None, "ClubPack row itself must be gone"
    finally:
        # Self-cleaning: this test writes real rows into the shared dev Postgres instance.
        # The pack (and its cascaded opening) is already deleted by the test itself when it
        # succeeds; only the club and user (and its cascaded admin_actions row) remain. Uses
        # the plain-int ids captured above rather than the (possibly expired/session-broken)
        # ORM objects, for the same reason as the capture above.
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
            if user_id is not None:
                user_row = await cleanup.get(User, user_id)
                if user_row is not None:
                    await cleanup.delete(user_row)
                    await cleanup.commit()
        await setup.close()
        await engine.dispose()
