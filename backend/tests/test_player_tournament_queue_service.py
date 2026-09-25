import pytest
from sqlalchemy import select

from app.core.exceptions import ConflictError
from app.models.player_tournament import (
    PlayerTournament, PlayerTournamentParticipant, PlayerTournamentQueue, PlayerTournamentStanding,
)
from app.services.player_tournament_queue_service import apply_to_tournament, get_current
from tests.player_tournament_helpers import make_ready_user, make_user


async def test_apply_queues_ready_user(client, db_session, bot_token):
    user = await make_ready_user(client, db_session, bot_token, 850001)
    result = await apply_to_tournament(db_session, user)
    assert result.queued is True and result.tournament_id is None
    assert result.queue_position == 1 and result.queue_size == 16
    current = await get_current(db_session, user)
    assert current.status == "queued" and current.queue_position == 1 and current.can_apply is False


async def test_incomplete_squad_cannot_apply(client, db_session, bot_token):
    user = await make_user(client, db_session, bot_token, 850002)
    with pytest.raises(ConflictError):
        await apply_to_tournament(db_session, user)


async def test_double_apply_rejected(client, db_session, bot_token):
    user = await make_ready_user(client, db_session, bot_token, 850003)
    await apply_to_tournament(db_session, user)
    with pytest.raises(ConflictError):
        await apply_to_tournament(db_session, user)


async def test_sixteenth_application_forms_tournament(client, db_session, bot_token):
    users = [await make_ready_user(client, db_session, bot_token, 850100 + i) for i in range(16)]
    for u in users[:15]:
        result = await apply_to_tournament(db_session, u)
        assert result.tournament_id is None
    result = await apply_to_tournament(db_session, users[15])
    assert result.tournament_id is not None

    tournament = await db_session.get(PlayerTournament, result.tournament_id)
    assert tournament.status.value == "active" and tournament.rounds_simulated == 0
    participants = (await db_session.execute(select(PlayerTournamentParticipant))).scalars().all()
    standings = (await db_session.execute(select(PlayerTournamentStanding))).scalars().all()
    assert len(participants) == 16 and len(standings) == 16

    formed = (await db_session.execute(select(PlayerTournamentQueue).where(PlayerTournamentQueue.status == "formed"))).scalars().all()
    assert len(formed) == 1
    current = await get_current(db_session, users[0])
    assert current.status == "active" and current.tournament_id == tournament.id

    with pytest.raises(ConflictError):  # already in an active tournament
        await apply_to_tournament(db_session, users[0])

    # A new queue is open for the next 16.
    next_result = await apply_to_tournament(db_session, await make_ready_user(client, db_session, bot_token, 850200))
    assert next_result.queued is True and next_result.queue_position == 1
