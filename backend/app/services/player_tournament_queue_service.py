from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models.enums import NotificationType, TournamentQueueStatus, TournamentStatus
from app.models.player_tournament import (
    PlayerTournament, PlayerTournamentParticipant, PlayerTournamentQueue, PlayerTournamentQueueEntry,
    PlayerTournamentQueueState, PlayerTournamentResult, PlayerTournamentStanding,
)
from app.models.user import User
from app.schemas.player_tournament import PlayerTournamentApplyResult, PlayerTournamentCurrentOut
from app.services import personal_squad_service
from app.services.notification_service import notify
from app.services.player_tournament_fixture_service import TOURNAMENT_SIZE


async def _lock_queue_state(db: AsyncSession) -> PlayerTournamentQueueState:
    """Locks the singleton queue-state row (id=1) so concurrent applications
    serialize — same idiom as tournament_queue_service._lock_queue_state.
    Lazily creates the singleton: migration 0119 seeds it on real Postgres,
    but tests build the schema with create_all."""
    result = await db.execute(
        select(PlayerTournamentQueueState).where(PlayerTournamentQueueState.id == 1)
        .with_for_update().execution_options(populate_existing=True)
    )
    state = result.scalar_one_or_none()
    if state is None:
        queue = PlayerTournamentQueue()
        db.add(queue)
        await db.flush()
        state = PlayerTournamentQueueState(id=1, current_queue_id=queue.id)
        db.add(state)
        await db.flush()
    return state


async def _active_tournament_id(db: AsyncSession, user_id: int) -> int | None:
    return (
        await db.execute(
            select(PlayerTournament.id)
            .join(PlayerTournamentParticipant, PlayerTournamentParticipant.tournament_id == PlayerTournament.id)
            .where(PlayerTournamentParticipant.user_id == user_id, PlayerTournament.status == TournamentStatus.active)
        )
    ).scalar_one_or_none()


async def _queue_position(db: AsyncSession, user_id: int, queue_id: int) -> int | None:
    entries = (
        await db.execute(
            select(PlayerTournamentQueueEntry.user_id)
            .where(PlayerTournamentQueueEntry.queue_id == queue_id)
            .order_by(PlayerTournamentQueueEntry.joined_at, PlayerTournamentQueueEntry.id)
        )
    ).scalars().all()
    return entries.index(user_id) + 1 if user_id in entries else None


async def apply_to_tournament(db: AsyncSession, user: User) -> PlayerTournamentApplyResult:
    if not await personal_squad_service.is_squad_complete(db, user.id):
        raise ConflictError("Заполни все позиции активного состава турнира, прежде чем подавать заявку")
    if await _active_tournament_id(db, user.id) is not None:
        raise ConflictError("Ты уже участвуешь в турнире")

    state = await _lock_queue_state(db)
    queue = await db.get(PlayerTournamentQueue, state.current_queue_id)
    already = (
        await db.execute(
            select(PlayerTournamentQueueEntry.id).where(
                PlayerTournamentQueueEntry.queue_id == queue.id, PlayerTournamentQueueEntry.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if already is not None:
        raise ConflictError("Ты уже в очереди на турнир")

    db.add(PlayerTournamentQueueEntry(queue_id=queue.id, user_id=user.id))
    await db.flush()

    entries = (
        await db.execute(
            select(PlayerTournamentQueueEntry)
            .where(PlayerTournamentQueueEntry.queue_id == queue.id)
            .order_by(PlayerTournamentQueueEntry.joined_at, PlayerTournamentQueueEntry.id)
        )
    ).scalars().all()

    if len(entries) < TOURNAMENT_SIZE:
        await db.commit()
        return PlayerTournamentApplyResult(queued=True, queue_position=len(entries), queue_size=TOURNAMENT_SIZE)

    tournament = PlayerTournament()
    db.add(tournament)
    await db.flush()
    for entry in entries:
        db.add(PlayerTournamentParticipant(tournament_id=tournament.id, user_id=entry.user_id))
        db.add(PlayerTournamentStanding(tournament_id=tournament.id, user_id=entry.user_id))
        await notify(
            db, entry.user_id, NotificationType.player_tournament_match, "Турнир начался",
            "Набрался полный состав участников — первый тур скоро сыграют!",
            related_object_type="player_tournament", related_object_id=tournament.id,
        )

    queue.status = TournamentQueueStatus.formed
    db.add(queue)
    new_queue = PlayerTournamentQueue()
    db.add(new_queue)
    await db.flush()
    state.current_queue_id = new_queue.id
    db.add(state)

    await db.commit()
    return PlayerTournamentApplyResult(queued=True, tournament_id=tournament.id, queue_size=TOURNAMENT_SIZE)


async def get_current(db: AsyncSession, user: User) -> PlayerTournamentCurrentOut:
    tournaments_played = (
        await db.execute(
            select(func.count(PlayerTournamentResult.id)).where(PlayerTournamentResult.user_id == user.id)
        )
    ).scalar_one()
    summary = dict(
        tournaments_played=tournaments_played, stars_count=user.tournament_stars_count,
        cups_count=user.tournament_cups_count,
    )

    active_id = await _active_tournament_id(db, user.id)
    if active_id is not None:
        return PlayerTournamentCurrentOut(status="active", tournament_id=active_id, queue_size=TOURNAMENT_SIZE, **summary)

    # Plain read (no lock): the singleton is only lazily created by apply_to_tournament.
    state = await db.get(PlayerTournamentQueueState, 1)
    position = await _queue_position(db, user.id, state.current_queue_id) if state is not None else None
    if position is not None:
        return PlayerTournamentCurrentOut(status="queued", queue_position=position, queue_size=TOURNAMENT_SIZE, **summary)

    last_completed = (
        await db.execute(
            select(PlayerTournament.id)
            .join(PlayerTournamentParticipant, PlayerTournamentParticipant.tournament_id == PlayerTournament.id)
            .where(PlayerTournamentParticipant.user_id == user.id, PlayerTournament.status == TournamentStatus.completed)
            .order_by(PlayerTournament.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    can_apply = await personal_squad_service.is_squad_complete(db, user.id)
    return PlayerTournamentCurrentOut(
        status="completed" if last_completed is not None else "not_queued",
        tournament_id=last_completed, queue_size=TOURNAMENT_SIZE, can_apply=can_apply, **summary,
    )
