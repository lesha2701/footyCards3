from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.personal_squad import PersonalSquad
from app.models.player_tournament import (
    PlayerTournament, PlayerTournamentMatch, PlayerTournamentParticipant, PlayerTournamentQueue,
    PlayerTournamentQueueEntry, PlayerTournamentResult, PlayerTournamentStanding,
)
from app.services.game_config_service import get_config
from tests.player_tournament_helpers import make_user


async def test_config_defaults(db_session):
    config = await get_config(db_session)
    assert (config.ptour_match_reward_win, config.ptour_match_reward_draw, config.ptour_match_reward_loss) == (100, 40, 15)
    assert len(config.ptour_place_rewards) == 16
    assert config.ptour_rating_by_place == [5, 4, 3, 2, 1, 0, 0, 0, 0, 0, 0, -1, -2, -3, -4, -5]
    assert sum(config.ptour_rating_by_place) == 0


async def test_user_rating_defaults_to_zero(client, db_session, bot_token):
    user = await make_user(client, db_session, bot_token, 840001)
    assert user.tournament_rating == 0


async def test_participant_unique_per_tournament(client, db_session, bot_token):
    user = await make_user(client, db_session, bot_token, 840002)
    tournament = PlayerTournament()
    db_session.add(tournament)
    await db_session.flush()
    db_session.add(PlayerTournamentParticipant(tournament_id=tournament.id, user_id=user.id))
    await db_session.commit()
    db_session.add(PlayerTournamentParticipant(tournament_id=tournament.id, user_id=user.id))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_squad_template_unique_and_one_active(client, db_session, bot_token):
    user = await make_user(client, db_session, bot_token, 840003)
    user_id = user.id  # rollback expires ORM instances; async lazy-load would fail
    db_session.add(PersonalSquad(user_id=user_id, template_index=1, is_active=True))
    await db_session.commit()
    db_session.add(PersonalSquad(user_id=user_id, template_index=1, is_active=False))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
    db_session.add(PersonalSquad(user_id=user_id, template_index=2, is_active=True))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_match_round_range_check(client, db_session, bot_token):
    a = await make_user(client, db_session, bot_token, 840004)
    b = await make_user(client, db_session, bot_token, 840005)
    tournament = PlayerTournament()
    db_session.add(tournament)
    await db_session.flush()
    db_session.add(PlayerTournamentMatch(
        tournament_id=tournament.id, round_number=31, user_a_id=a.id, user_b_id=b.id,
        score_a=1, score_b=0, event_log=[], simulated_at=datetime.now(timezone.utc),
    ))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
