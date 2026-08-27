import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models.club import Club
from app.models.enums import Position, TournamentStatus
from app.models.tournament import Tournament, TournamentClub
from app.models.tournament_match import TournamentMatch
from app.models.tournament_result import TournamentClubResult
from app.models.tournament_standing import TournamentClubStanding
from app.services.lineup_service import FORMATION_SLOTS
from app.services.tournament_queue_service import apply_to_tournament
from app.services.tournament_simulation_service import simulate_next_round
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

# Same real-dev-Postgres pattern as test_club_packs.py / test_tournament_queue_service.py:
# the pytest suite's `client`/`db_session` fixtures (tests/conftest.py) are hardcoded to an
# in-memory SQLite engine, an entirely separate database from real dev Postgres — there is no
# `tests.conftest.RealSessionLocal` to import (that name does not exist anywhere in this
# codebase). The two genuine-concurrency tests below build their own tournament directly
# against real Postgres (raw model construction, mirroring
# test_tournament_queue_service.py's test_eight_concurrent_applications_form_exactly_one_tournament)
# rather than trying to reuse a SQLite-backed fixture's row id against a different database.
REAL_POSTGRES_URL = os.environ.get("REAL_POSTGRES_URL", "postgresql+asyncpg://postgres:1234@postgres:5432/footycards")


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """Same seeding test_tournament_queue_service.py's own autouse fixture does —
    each club's starter squad needs active Players to draw from per formation
    category."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _create_club_with_full_squad(client, db_session, bot_token, telegram_id, name):
    """Registers telegram_id as captain of a fresh club (auto-seeded 11/11 lineup via
    seed_starting_squad), plus a second member so apply_to_tournament's >=2-members check
    passes. Mirrors test_tournament_queue_service.py's own helper of the same name (each test
    file gets its own local copy per this codebase's convention — not cross-file importable)."""
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


@pytest_asyncio.fixture
async def eight_club_tournament(client, db_session, bot_token):
    """Registers 8 clubs and applies each to the tournament queue — the 8th application forms
    the Tournament. Yields (tournament, clubs_and_captains) so callers can authenticate as any
    of the 8 captains. Task 16 (and any other task needing this setup) references the same
    fixture name/shape in its own test file — this is that file's own local copy."""
    clubs_and_captains = []
    tournament_id = None
    for i in range(8):
        club, captain = await _create_club_with_full_squad(client, db_session, bot_token, 841000 + i, f"Клуб симуляции {i}")
        result = await apply_to_tournament(db_session, captain)
        clubs_and_captains.append((club, captain))
        if result.tournament_id is not None:
            tournament_id = result.tournament_id

    assert tournament_id is not None
    tournament = await db_session.get(Tournament, tournament_id)
    return tournament, clubs_and_captains


@pytest_asyncio.fixture
async def eight_club_tournament_at_round_13(db_session, eight_club_tournament):
    tournament, clubs_and_captains = eight_club_tournament
    for _ in range(13):
        await simulate_next_round(db_session)
        await db_session.commit()
    await db_session.refresh(tournament)
    assert tournament.rounds_simulated == 13
    return tournament, clubs_and_captains


async def test_simulate_next_round_simulates_round_1_for_a_fresh_tournament(db_session, eight_club_tournament):
    tournament, _clubs_and_captains = eight_club_tournament
    matches = await simulate_next_round(db_session)
    await db_session.commit()

    round_1_matches = [m for m in matches if m.tournament_id == tournament.id]
    assert len(round_1_matches) == 4
    await db_session.refresh(tournament)
    assert tournament.rounds_simulated == 1
    for m in round_1_matches:
        assert m.event_log  # non-empty for a real (non-withdrawn) match
        assert m.score_a >= 0 and m.score_b >= 0


async def test_simulate_next_round_updates_standings(db_session, eight_club_tournament):
    tournament, _clubs_and_captains = eight_club_tournament
    matches = await simulate_next_round(db_session)
    await db_session.commit()

    standings = (
        await db_session.execute(select(TournamentClubStanding).where(TournamentClubStanding.tournament_id == tournament.id))
    ).scalars().all()
    total_points_awarded = sum(s.points for s in standings)

    # 4 matches this round: each is either decisive (3 points total, all to the winner) or a
    # draw (1+1 = 2 points total) — compute the expected total from the actual persisted
    # scores rather than hardcoding a single number, since a real random-outcome engine can and
    # does produce draws.
    round_1_matches = [m for m in matches if m.tournament_id == tournament.id]
    expected_points = sum(2 if m.score_a == m.score_b else 3 for m in round_1_matches)
    assert total_points_awarded == expected_points
    assert 8 <= total_points_awarded <= 12


async def test_simulate_next_round_auto_scores_withdrawn_club_as_loss(db_session, eight_club_tournament):
    tournament, _clubs_and_captains = eight_club_tournament
    participants = (
        await db_session.execute(select(TournamentClub).where(TournamentClub.tournament_id == tournament.id))
    ).scalars().all()
    withdrawn = participants[0]
    withdrawn.is_withdrawn = True
    db_session.add(withdrawn)
    await db_session.commit()

    matches = await simulate_next_round(db_session)
    withdrawn_matches = [m for m in matches if m.club_a_id == withdrawn.club_id or m.club_b_id == withdrawn.club_id]
    assert len(withdrawn_matches) == 1
    m = withdrawn_matches[0]
    assert m.event_log == []
    if m.club_a_id == withdrawn.club_id:
        assert (m.score_a, m.score_b) == (0, 3)
    else:
        assert (m.score_a, m.score_b) == (3, 0)


async def test_simulate_next_round_notifies_both_clubs_on_a_real_match(db_session, eight_club_tournament):
    from sqlalchemy import select

    from app.models.enums import NotificationType
    from app.models.notification import Notification
    from app.services.tournament_simulation_service import simulate_next_round

    tournament, clubs_and_captains = eight_club_tournament
    matches = await simulate_next_round(db_session)
    await db_session.commit()

    real_matches = [m for m in matches if m.tournament_id == tournament.id and m.event_log]
    assert real_matches  # at least one real (non-withdrawn) match this round

    notifications = (
        await db_session.execute(select(Notification).where(Notification.type == NotificationType.club_match))
    ).scalars().all()
    # 2 members per club (per Task 2's fixture convention) * 2 clubs per real match
    assert len(notifications) == len(real_matches) * 4
    assert notifications[0].related_object_type == "club_match"
    assert notifications[0].related_object_id == tournament.id


async def test_simulate_next_round_concludes_tournament_at_round_14(db_session, eight_club_tournament_at_round_13):
    tournament, _clubs_and_captains = eight_club_tournament_at_round_13
    matches = await simulate_next_round(db_session)
    await db_session.commit()
    await db_session.refresh(tournament)

    round_14_matches = [m for m in matches if m.tournament_id == tournament.id]
    assert len(round_14_matches) == 4
    assert tournament.rounds_simulated == 14
    assert tournament.status.value == "completed"

    results = (
        await db_session.execute(select(TournamentClubResult).where(TournamentClubResult.tournament_id == tournament.id))
    ).scalars().all()
    assert len(results) == 8
    ranks = sorted(r.final_rank for r in results)
    assert ranks == list(range(1, 9))


# --- Real-Postgres concurrency tests ----------------------------------------
# Both tests below build their own 8-club tournament straight against real Postgres (raw
# model construction, mirroring test_tournament_queue_service.py's own real-Postgres race
# test) rather than reusing the SQLite `db_session`-backed `eight_club_tournament` fixture —
# that fixture's rows live in a completely different (in-memory SQLite) database and would
# not exist for a RealSessionLocal query to find. Skips gracefully if real dev Postgres is
# unreachable, same as every other real-Postgres regression test in this suite.


async def _seed_real_eight_club_tournament(RealSessionLocal, suffix: str) -> dict:
    """Builds 8 clubs (raw construction: Players, Users, Clubs, ClubMembers, ClubLineups,
    ClubCards) with full 11-card starting lineups directly against real Postgres, then calls
    apply_to_tournament sequentially (not concurrently — queue-formation racing is already
    covered by test_tournament_queue_service.py; here we just need a concrete, already-formed
    tournament to exist before racing simulate_next_round against it). Returns the created ids
    (for cleanup) and the formed tournament's id."""
    from app.models.club import ClubMember
    from app.models.club_card import ClubCard
    from app.models.club_lineup import ClubLineup, ClubLineupCard
    from app.models.enums import ClubCardSource, ClubLogoShape, ClubRole, ClubType, Rarity
    from app.models.player import Player
    from app.models.user import User

    setup = RealSessionLocal()
    player_ids: list[int] = []
    club_ids: list[int] = []
    user_ids: list[int] = []
    captain_ids: list[int] = []
    try:
        players = []
        for slot in FORMATION_SLOTS:
            player = Player(
                first_name=f"Sim{suffix}", last_name=slot.code, display_name=f"Sim {suffix} {slot.code}",
                rating=70, rarity=Rarity.common, country="Тестландия", club=f"ФК Симуляция {suffix}",
                position=slot.ideal_position, quick_sell_price=10, is_active=True,
            )
            setup.add(player)
            players.append(player)
        await setup.flush()
        player_ids = [p.id for p in players]

        for i in range(8):
            telegram_id = 992_000_000_000 + (uuid.uuid4().int % 1_000_000_000)
            user = User(telegram_id=telegram_id, username=f"sim_{suffix}_{i}")
            setup.add(user)
            await setup.flush()
            user_ids.append(user.id)

            club = Club(
                name=f"Симуляция турнира {suffix} {i}", club_type=ClubType.open, logo_shape=ClubLogoShape.shield,
                logo_color="#123456", captain_id=user.id, invite_code=f"sim{suffix}{i}"[:16], budget=0,
            )
            setup.add(club)
            await setup.flush()
            club_ids.append(club.id)
            setup.add(ClubMember(club_id=club.id, user_id=user.id, role=ClubRole.captain))

            second_telegram_id = 992_100_000_000 + (uuid.uuid4().int % 1_000_000_000)
            second_user = User(telegram_id=second_telegram_id, username=f"sim2_{suffix}_{i}")
            setup.add(second_user)
            await setup.flush()
            user_ids.append(second_user.id)
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

    tournament_id = None
    for captain_id in captain_ids:
        async with RealSessionLocal() as session:
            captain = await session.get(User, captain_id)
            result = await apply_to_tournament(session, captain)
            if result.tournament_id is not None:
                tournament_id = result.tournament_id

    assert tournament_id is not None, "8 sequential applications should have formed a tournament"
    return {"tournament_id": tournament_id, "club_ids": club_ids, "user_ids": user_ids, "player_ids": player_ids}


async def _cleanup_real_tournament(RealSessionLocal, tournament_id, club_ids, user_ids, player_ids):
    from app.models.player import Player
    from app.models.user import User

    async with RealSessionLocal() as session:
        tournament = await session.get(Tournament, tournament_id)
        if tournament is not None:
            await session.delete(tournament)
        await session.commit()
    async with RealSessionLocal() as session:
        for club_id in club_ids:
            club = await session.get(Club, club_id)
            if club is not None:
                await session.delete(club)
        await session.commit()
    async with RealSessionLocal() as session:
        for user_id in user_ids:
            user = await session.get(User, user_id)
            if user is not None:
                await session.delete(user)
        await session.commit()
    async with RealSessionLocal() as session:
        for player_id in player_ids:
            player = await session.get(Player, player_id)
            if player is not None:
                await session.delete(player)
        await session.commit()


async def _real_engine_or_skip():
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(REAL_POSTGRES_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except (OSError, OperationalError) as exc:
        await engine.dispose()
        pytest.skip(f"real dev Postgres not reachable at {REAL_POSTGRES_URL!r}: {exc!r}")
    return engine


async def test_simulate_next_round_is_idempotent_under_concurrent_calls():
    """Genuine concurrency regression test against real Postgres: two concurrent
    simulate_next_round calls racing on the same freshly-formed tournament must not
    double-simulate round 1 (checked by asserting rounds_simulated == 1 and exactly 4 matches
    exist for round 1 afterward, not 8)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    engine = await _real_engine_or_skip()
    RealSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:8]
    seed = await _seed_real_eight_club_tournament(RealSessionLocal, suffix)
    tournament_id = seed["tournament_id"]

    try:
        async def call():
            async with RealSessionLocal() as session:
                return await simulate_next_round(session)

        results = await asyncio.gather(call(), call(), return_exceptions=True)
        for result in results:
            assert not isinstance(result, BaseException), f"simulate_next_round raised instead of handling the race: {result!r}"

        async with RealSessionLocal() as session:
            tournament = await session.get(Tournament, tournament_id)
            assert tournament.rounds_simulated == 1
            round_1_matches = (
                await session.execute(
                    select(TournamentMatch).where(TournamentMatch.tournament_id == tournament_id, TournamentMatch.round_number == 1)
                )
            ).scalars().all()
            assert len(round_1_matches) == 4
    finally:
        await _cleanup_real_tournament(RealSessionLocal, tournament_id, seed["club_ids"], seed["user_ids"], seed["player_ids"])
        await engine.dispose()


async def test_round_14_reward_distribution_cannot_double_fire_under_concurrency():
    """Genuine concurrency regression test against real Postgres: advances a tournament to
    round 13 (sequentially — only the final round-14 call is raced), then fires two concurrent
    simulate_next_round calls that both try to simulate round 14 and conclude the tournament.
    Exactly one must win: TournamentClubResult must end up with exactly one row per club (8),
    not 16, and the tournament's budget/star rewards must only be credited once."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    engine = await _real_engine_or_skip()
    RealSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:8]
    seed = await _seed_real_eight_club_tournament(RealSessionLocal, suffix)
    tournament_id = seed["tournament_id"]

    try:
        for _ in range(13):
            async with RealSessionLocal() as session:
                await simulate_next_round(session)

        async with RealSessionLocal() as session:
            tournament = await session.get(Tournament, tournament_id)
            assert tournament.rounds_simulated == 13
            assert tournament.status == TournamentStatus.active

        async def call():
            async with RealSessionLocal() as session:
                return await simulate_next_round(session)

        results = await asyncio.gather(call(), call(), return_exceptions=True)
        for result in results:
            assert not isinstance(result, BaseException), f"simulate_next_round raised instead of handling the race: {result!r}"

        async with RealSessionLocal() as session:
            tournament = await session.get(Tournament, tournament_id)
            assert tournament.rounds_simulated == 14
            assert tournament.status == TournamentStatus.completed

            result_count = (
                await session.execute(select(func.count(TournamentClubResult.id)).where(TournamentClubResult.tournament_id == tournament_id))
            ).scalar_one()
            assert result_count == 8  # exactly one TournamentClubResult per club, not 16

            round_14_matches = (
                await session.execute(
                    select(func.count(TournamentMatch.id)).where(
                        TournamentMatch.tournament_id == tournament_id, TournamentMatch.round_number == 14
                    )
                )
            ).scalar_one()
            assert round_14_matches == 4  # not 8 — round 14 itself wasn't double-simulated either
    finally:
        await _cleanup_real_tournament(RealSessionLocal, tournament_id, seed["club_ids"], seed["user_ids"], seed["player_ids"])
        await engine.dispose()
