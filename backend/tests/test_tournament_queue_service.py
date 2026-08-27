import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.exceptions import ConflictError
from app.models.club import Club
from app.models.enums import Position
from app.models.tournament import Tournament, TournamentClub
from app.models.tournament_queue import TournamentQueue, TournamentQueueEntry, TournamentQueueState
from app.services.tournament_queue_service import apply_to_tournament
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

REAL_POSTGRES_URL = os.environ.get("REAL_POSTGRES_URL", "postgresql+asyncpg://postgres:1234@postgres:5432/footycards")


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """Same seeding test_clubs.py's own autouse fixture does — each club's
    starter squad needs active Players to draw from per formation category."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _create_club_with_full_squad(client, db_session, bot_token, telegram_id, name):
    """Registers telegram_id as captain of a fresh club. club_service.create_club
    already auto-seeds a full 11/11 starting lineup via seed_starting_squad
    (Phase 2) — no extra lineup-filling step needed; every freshly created
    club is tournament-eligible on the squad-completeness axis by default.

    Also registers and joins a second member: apply_to_tournament requires >=2 members
    (docs/superpowers/specs/2026-08-26-clubs-design.md, "Tournament: queue -> formation"
    section), so every club this helper builds needs to be eligible on that axis too, not
    just squad-completeness. The second member's telegram_id is derived from the captain's
    with a fixed offset so it stays distinct from every other id used across this file's tests."""
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    captain = await get_user_by_telegram_id(db_session, telegram_id)

    create_resp = await client.post(
        "/api/v1/clubs", headers=telegram_headers(telegram_id, bot_token),
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert create_resp.status_code == 200
    club = await db_session.get(Club, create_resp.json()["id"])

    second_member_telegram_id = telegram_id + 900_000
    resp2 = await client.post("/api/v1/auth/session", headers=telegram_headers(second_member_telegram_id, bot_token))
    assert resp2.status_code == 200
    join_resp = await client.post(f"/api/v1/clubs/{club.id}/join", headers=telegram_headers(second_member_telegram_id, bot_token))
    assert join_resp.status_code == 200

    return club, captain


async def test_apply_queues_a_ready_club(client, db_session, bot_token):
    club, captain = await _create_club_with_full_squad(client, db_session, bot_token, 830001, "Тестовый клуб 1")
    result = await apply_to_tournament(db_session, captain)
    assert result.queued is True
    assert result.tournament_id is None
    entry = (await db_session.execute(select(TournamentQueueEntry).where(TournamentQueueEntry.club_id == club.id))).scalar_one()
    assert entry is not None


async def test_eighth_application_forms_tournament(client, db_session, bot_token):
    for i in range(7):
        club, captain = await _create_club_with_full_squad(client, db_session, bot_token, 830100 + i, f"Клуб очереди {i}")
        await apply_to_tournament(db_session, captain)

    club, captain = await _create_club_with_full_squad(client, db_session, bot_token, 830200, "Клуб очереди 7")
    result = await apply_to_tournament(db_session, captain)
    assert result.queued is True
    assert result.tournament_id is not None

    tournament = await db_session.get(Tournament, result.tournament_id)
    assert tournament.rounds_simulated == 0
    participants = (await db_session.execute(select(TournamentClub).where(TournamentClub.tournament_id == tournament.id))).scalars().all()
    assert len(participants) == 8

    state = await db_session.get(TournamentQueueState, 1)
    new_queue = await db_session.get(TournamentQueue, state.current_queue_id)
    assert new_queue.id != tournament.id  # a fresh queue was opened, distinct id space from Tournament anyway
    assert new_queue.status.value == "open"


async def test_club_can_reapply_to_fresh_queue_after_its_first_queue_formed(client, db_session, bot_token):
    """Regression test: TournamentQueueEntry rows are never deleted once their queue is formed
    (they stay as history), so `_is_already_queued` must be scoped to the *current* queue's id,
    not to "any entry this club has ever had" — otherwise a club that queued once would be
    permanently blocked from ever applying again, in any future queue, even long after its
    tournament finished. Forms a tournament with 8 clubs, marks it completed (simulating what a
    later task's tournament-resolution step will eventually do — that flow doesn't exist yet in
    Task 9), clears one participant's cooldown, and confirms that club can queue again despite
    its old TournamentQueueEntry row (in the now-formed, historical queue) still existing."""
    clubs_and_captains = []
    for i in range(7):
        club, captain = await _create_club_with_full_squad(client, db_session, bot_token, 830600 + i, f"Реванш {i}")
        await apply_to_tournament(db_session, captain)
        clubs_and_captains.append((club, captain))

    club8, captain8 = await _create_club_with_full_squad(client, db_session, bot_token, 830700, "Реванш 7")
    result = await apply_to_tournament(db_session, captain8)
    assert result.tournament_id is not None

    from app.models.enums import TournamentStatus
    tournament = await db_session.get(Tournament, result.tournament_id)
    tournament.status = TournamentStatus.completed
    db_session.add(tournament)

    # This club's first-ever TournamentQueueEntry now lives in a "formed" queue, and its
    # tournament is completed (not active). Bypass the cooldown too, so this test isolates the
    # queue-scoping bug from the separately-tested cooldown gate.
    club0, captain0 = clubs_and_captains[0]
    club0.last_tournament_applied_at = None
    db_session.add(club0)
    await db_session.commit()

    result2 = await apply_to_tournament(db_session, captain0)
    assert result2.queued is True
    assert result2.tournament_id is None


async def test_apply_rejects_incomplete_squad(client, db_session, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(830300, bot_token))
    assert resp.status_code == 200
    captain = await get_user_by_telegram_id(db_session, 830300)
    create_resp = await client.post(
        "/api/v1/clubs", headers=telegram_headers(830300, bot_token),
        json={"name": "Неполный клуб", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert create_resp.status_code == 200

    # Give this club a second member too, so the ConflictError asserted below is actually
    # caused by the incomplete squad (the thing under test), not incidentally by the
    # separate ">=2 members" check running first.
    resp2 = await client.post("/api/v1/auth/session", headers=telegram_headers(1730300, bot_token))
    assert resp2.status_code == 200
    join_resp = await client.post(f"/api/v1/clubs/{create_resp.json()['id']}/join", headers=telegram_headers(1730300, bot_token))
    assert join_resp.status_code == 200

    # club_service.create_club already auto-seeds a full 11/11 lineup today —
    # empty it out to exercise the "incomplete squad" rejection path.
    from app.models.club_lineup import ClubLineup, ClubLineupCard
    lineup = (await db_session.execute(select(ClubLineup).where(ClubLineup.club_id == create_resp.json()["id"])))
    lineup = lineup.scalar_one()
    await db_session.execute(select(ClubLineupCard).where(ClubLineupCard.club_lineup_id == lineup.id))
    for lc in (await db_session.execute(select(ClubLineupCard).where(ClubLineupCard.club_lineup_id == lineup.id))).scalars().all():
        await db_session.delete(lc)
    await db_session.commit()

    with pytest.raises(ConflictError):
        await apply_to_tournament(db_session, captain)


async def test_apply_rejects_single_member_club(client, db_session, bot_token):
    """The design spec (docs/superpowers/specs/2026-08-26-clubs-design.md, "Tournament: queue
    -> formation" section) requires >=2 members as a queue-application validation criterion —
    a solo-captain club, even with a full 11/11 starting XI, must not be able to apply."""
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(830800, bot_token))
    assert resp.status_code == 200
    captain = await get_user_by_telegram_id(db_session, 830800)
    create_resp = await client.post(
        "/api/v1/clubs", headers=telegram_headers(830800, bot_token),
        json={"name": "Клуб одиночка", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert create_resp.status_code == 200
    # No second member joins — club_service.create_club already auto-seeds a full 11/11
    # lineup, so this club is squad-complete; only the membership-count axis is under test.

    with pytest.raises(ConflictError):
        await apply_to_tournament(db_session, captain)


async def test_apply_rejects_non_manager(client, db_session, bot_token):
    club, captain = await _create_club_with_full_squad(client, db_session, bot_token, 830400, "Клуб не менеджера")
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(830401, bot_token))
    assert resp.status_code == 200
    member = await get_user_by_telegram_id(db_session, 830401)
    join_resp = await client.post(f"/api/v1/clubs/{club.id}/join", headers=telegram_headers(830401, bot_token))
    assert join_resp.status_code == 200

    from app.core.exceptions import ForbiddenError
    with pytest.raises(ForbiddenError):
        await apply_to_tournament(db_session, member)


async def test_eight_concurrent_applications_form_exactly_one_tournament():
    """Genuine concurrency regression test for the singleton TournamentQueueState lock: 8 clubs
    apply concurrently (asyncio.gather, independent DB sessions/connections against real Postgres)
    and exactly one of them must observe the queue crossing 8 entries and form the Tournament.

    Runs against real Postgres (see REAL_POSTGRES_URL above) — skips gracefully if unreachable,
    same as test_club_packs.py's own concurrent-race regression test. For the same reason that
    test avoids the pytest suite's SQLite-backed `client`/`db_session` fixtures (a single shared
    StaticPool connection can't reproduce genuine two-connection FOR UPDATE lock timing, and the
    dependency-overridden `client` never touches real Postgres at all), this test also builds its
    fixtures — users, clubs, full 11-card lineups — directly against `RealSessionLocal`, mirroring
    test_club_packs.py's raw-model-construction pattern instead of going through HTTP endpoints.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.club import ClubMember
    from app.models.club_card import ClubCard
    from app.models.club_lineup import ClubLineup, ClubLineupCard
    from app.models.enums import ClubCardSource, ClubLogoShape, ClubRole, ClubType, Rarity
    from app.models.player import Player
    from app.models.user import User
    from app.services.lineup_service import FORMATION_SLOTS

    engine = create_async_engine(REAL_POSTGRES_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except (OSError, OperationalError) as exc:
        await engine.dispose()
        pytest.skip(f"real dev Postgres not reachable at {REAL_POSTGRES_URL!r}: {exc!r}")

    RealSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:8]

    setup = RealSessionLocal()
    captain_ids: list[int] = []
    try:
        # One shared pool of 11 players (one per formation slot's ideal position) — every
        # club's ClubCard rows below just reference these; nothing about ClubCard/UserCard
        # requires a player to be exclusive to one club.
        players = []
        for slot in FORMATION_SLOTS:
            player = Player(
                first_name=f"Race{suffix}", last_name=slot.code, display_name=f"Race {suffix} {slot.code}",
                rating=70, rarity=Rarity.common, country="Тестландия", club=f"ФК Гонка {suffix}",
                position=slot.ideal_position, quick_sell_price=10, is_active=True,
            )
            setup.add(player)
            players.append(player)
        await setup.flush()

        for i in range(8):
            telegram_id = 990_500_000_000 + (uuid.uuid4().int % 1_000_000_000)
            user = User(telegram_id=telegram_id, username=f"race_{suffix}_{i}")
            setup.add(user)
            await setup.flush()

            club = Club(
                name=f"Гонка турнира {suffix} {i}", club_type=ClubType.open, logo_shape=ClubLogoShape.shield,
                logo_color="#123456", captain_id=user.id, invite_code=f"race{suffix}{i}"[:16], budget=0,
            )
            setup.add(club)
            await setup.flush()
            setup.add(ClubMember(club_id=club.id, user_id=user.id, role=ClubRole.captain))

            # apply_to_tournament requires >= 2 members — add a second one directly too,
            # matching this test's raw-construction style rather than going through the API.
            second_telegram_id = 990_600_000_000 + (uuid.uuid4().int % 1_000_000_000)
            second_user = User(telegram_id=second_telegram_id, username=f"race2_{suffix}_{i}")
            setup.add(second_user)
            await setup.flush()
            setup.add(ClubMember(club_id=club.id, user_id=second_user.id, role=ClubRole.member))

            lineup = ClubLineup(club_id=club.id)
            setup.add(lineup)
            await setup.flush()
            for slot, player in zip(FORMATION_SLOTS, players):
                card = ClubCard(club_id=club.id, player_id=player.id, serial_number=1, source=ClubCardSource.starter_seed)
                setup.add(card)
                await setup.flush()
                setup.add(ClubLineupCard(club_lineup_id=lineup.id, club_card_id=card.id, slot_code=slot.code))

            captain_ids.append(user.id)

        await setup.commit()
    finally:
        await setup.close()

    async def apply_in_real_session(captain_id: int):
        async with RealSessionLocal() as session:
            captain = await session.get(User, captain_id)
            return await apply_to_tournament(session, captain)

    results = await asyncio.gather(*(apply_in_real_session(cid) for cid in captain_ids), return_exceptions=True)
    for result in results:
        assert not isinstance(result, BaseException), f"apply_to_tournament raised instead of handling the race: {result!r}"

    formed = [r for r in results if r.tournament_id is not None]
    assert len(formed) == 1

    async with RealSessionLocal() as session:
        participants = (
            await session.execute(select(TournamentClub).where(TournamentClub.tournament_id == formed[0].tournament_id))
        ).scalars().all()
        assert len(participants) == 8

    await engine.dispose()
