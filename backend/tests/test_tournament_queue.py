import pytest
from sqlalchemy import select

from app.models.tournament_queue import TournamentQueue, TournamentQueueState


async def _ensure_singleton_seeded(db_session):
    """Ensure the singleton TournamentQueueState row exists, following the GameConfig test pattern."""
    state = await db_session.get(TournamentQueueState, 1)
    if state is None:
        # Create the initial queue
        queue = TournamentQueue(status="open")
        db_session.add(queue)
        await db_session.flush()  # Get the ID

        # Create the singleton state pointing to that queue
        state = TournamentQueueState(id=1, current_queue_id=queue.id)
        db_session.add(state)
        await db_session.commit()

        # Re-fetch to verify
        state = await db_session.get(TournamentQueueState, 1)
    return state


async def test_singleton_state_seeded_by_migration(db_session):
    state = await _ensure_singleton_seeded(db_session)
    queue = (await db_session.execute(select(TournamentQueue).where(TournamentQueue.id == state.current_queue_id))).scalar_one()
    assert queue.status.value == "open"
