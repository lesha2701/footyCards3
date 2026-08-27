from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models.club import Club
from app.models.club_lineup import ClubLineup, ClubLineupCard
from app.models.enums import TournamentQueueStatus
from app.models.tournament import Tournament, TournamentClub
from app.models.tournament_queue import TournamentQueue, TournamentQueueEntry, TournamentQueueState
from app.models.tournament_standing import TournamentClubStanding
from app.models.user import User
from app.schemas.tournament import TournamentApplyResult
from app.services.game_config_service import get_config
from app.services.lineup_service import FORMATION_SLOTS
from app.services.tournament_fixture_service import generate_fixtures

TOURNAMENT_CLUB_COUNT = 8


async def _lock_queue_state(db: AsyncSession) -> TournamentQueueState:
    """Locks the singleton TournamentQueueState row (id=1) so concurrent applications
    serialize on the current queue, following `club_service._lock_club`'s
    `.with_for_update().execution_options(populate_existing=True)` idiom by analogy —
    no other singleton-row lock exists in this codebase to copy verbatim.

    `populate_existing=True` matters here for the same reason it does in `_lock_club`:
    without it, a `TournamentQueueState` already in the session's identity map would be
    returned as-is instead of the freshly locked row, silently defeating the lock.

    The migration that creates this table (0065_tournament_queue.py) also seeds row 1
    via `op.execute` INSERT statements — which run against real Postgres, but not against
    the test suite's SQLite DB (tests/conftest.py provisions schema via
    `Base.metadata.create_all`, not Alembic). So this also lazily creates the singleton
    the first time it's missing, mirroring `game_config_service.get_config`'s get-or-create
    pattern for the same reason. Against real Postgres the row already exists, so this
    branch never runs there.
    """
    result = await db.execute(
        select(TournamentQueueState).where(TournamentQueueState.id == 1)
        .with_for_update().execution_options(populate_existing=True)
    )
    state = result.scalar_one_or_none()
    if state is None:
        queue = TournamentQueue()
        db.add(queue)
        await db.flush()
        state = TournamentQueueState(id=1, current_queue_id=queue.id)
        db.add(state)
        await db.flush()
    return state


async def _has_full_starting_xi(db: AsyncSession, club_id: int) -> bool:
    lineup = (await db.execute(select(ClubLineup).where(ClubLineup.club_id == club_id))).scalar_one_or_none()
    if lineup is None:
        return False
    count = (
        await db.execute(select(func.count(ClubLineupCard.id)).where(ClubLineupCard.club_lineup_id == lineup.id))
    ).scalar_one()
    return count == len(FORMATION_SLOTS)


async def _is_in_active_tournament(db: AsyncSession, club_id: int) -> bool:
    active = (
        await db.execute(
            select(TournamentClub).join(Tournament, Tournament.id == TournamentClub.tournament_id)
            .where(TournamentClub.club_id == club_id, Tournament.status == "active")
        )
    ).scalar_one_or_none()
    return active is not None


async def _is_already_queued(db: AsyncSession, club_id: int, queue_id: int) -> bool:
    """Whether this club already has an entry in the given (current, open) queue.

    Deliberately scoped to `queue_id` rather than checking for any `TournamentQueueEntry`
    row ever created for this club: entries are never deleted once a queue is formed (see
    `apply_to_tournament` — a formed queue's entries stay as history), so an unscoped check
    would permanently block the club from ever applying again, in any future queue, once its
    very first application landed. Called after `_lock_queue_state` has resolved the current
    queue, so this also closes the check-then-insert race for a club double-submitting.
    """
    queued = (
        await db.execute(
            select(TournamentQueueEntry).where(
                TournamentQueueEntry.club_id == club_id, TournamentQueueEntry.queue_id == queue_id
            )
        )
    ).scalar_one_or_none()
    return queued is not None


async def apply_to_tournament(db: AsyncSession, user: User) -> TournamentApplyResult:
    from app.services.club_service import _require_manager, _require_membership

    membership = await _require_membership(db, user.id)
    _require_manager(membership)
    club = await db.get(Club, membership.club_id)

    if not await _has_full_starting_xi(db, club.id):
        raise ConflictError("Заполни все 11 позиций в составе клуба, прежде чем подавать заявку")
    if await _is_in_active_tournament(db, club.id):
        raise ConflictError("Клуб уже участвует в турнире")

    config = await get_config(db)
    if club.last_tournament_applied_at is not None:
        elapsed = datetime.now(timezone.utc) - club.last_tournament_applied_at
        if elapsed.total_seconds() < config.club_tournament_cooldown_hours * 3600:
            raise ConflictError("Клуб пока не может подать новую заявку — подожди перед повторной подачей")

    state = await _lock_queue_state(db)
    queue = await db.get(TournamentQueue, state.current_queue_id)

    if await _is_already_queued(db, club.id, queue.id):
        raise ConflictError("Клуб уже в очереди на турнир")

    db.add(TournamentQueueEntry(queue_id=queue.id, club_id=club.id))
    await db.flush()
    club.last_tournament_applied_at = datetime.now(timezone.utc)
    db.add(club)

    entries = (
        await db.execute(select(TournamentQueueEntry).where(TournamentQueueEntry.queue_id == queue.id).order_by(TournamentQueueEntry.joined_at))
    ).scalars().all()

    if len(entries) < TOURNAMENT_CLUB_COUNT:
        await db.commit()
        return TournamentApplyResult(queued=True, queue_position=len(entries))

    club_ids = [e.club_id for e in entries]
    tournament = Tournament()
    db.add(tournament)
    await db.flush()

    for club_id in club_ids:
        db.add(TournamentClub(tournament_id=tournament.id, club_id=club_id))
        db.add(TournamentClubStanding(tournament_id=tournament.id, club_id=club_id))
        club_row = await db.get(Club, club_id)
        club_row.last_tournament_applied_at = datetime.now(timezone.utc)
        db.add(club_row)

    for round_number, club_a_id, club_b_id in generate_fixtures(club_ids):
        # Fixtures themselves aren't persisted as rows yet — TournamentMatch
        # rows are only created when a round is actually simulated (Task 14).
        # generate_fixtures is deterministic given club_ids, so the schedule
        # can always be recomputed; nothing is lost by not storing it early.
        pass

    queue.status = TournamentQueueStatus.formed
    db.add(queue)

    new_queue = TournamentQueue()
    db.add(new_queue)
    await db.flush()
    state.current_queue_id = new_queue.id
    db.add(state)

    await db.commit()
    return TournamentApplyResult(queued=True, tournament_id=tournament.id)
