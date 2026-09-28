from app.models.player_tournament import PlayerTournament, PlayerTournamentParticipant
from app.models.user import User
from app.schemas.player_tournament_ranking import PlayerTournamentRankingMetric
from app.services.player_tournament_ranking_service import get_player_tournament_ranking
from tests.player_tournament_helpers import make_ready_user, make_user


async def _make_participant(db_session, *users):
    """Directly creates a formed tournament with `users` as its participants.

    apply_to_tournament only queues a user until the shared queue reaches
    TOURNAMENT_SIZE (16, see player_tournament_fixture_service.py) — spinning
    up 16 users per ranking test would be impractical, and the ranking
    service filters on PlayerTournamentParticipant existence, so we create
    that row directly instead of going through the real queue-fill flow.
    """
    tournament = PlayerTournament()
    db_session.add(tournament)
    await db_session.flush()
    for user in users:
        db_session.add(PlayerTournamentParticipant(tournament_id=tournament.id, user_id=user.id))
    await db_session.commit()


async def test_ranking_orders_by_metric_and_excludes_non_participants(client, db_session, bot_token):
    a = await make_ready_user(client, db_session, bot_token, 890001)
    b = await make_ready_user(client, db_session, bot_token, 890002)
    await make_user(client, db_session, bot_token, 890003)  # never applied — must be excluded
    await _make_participant(db_session, a, b)

    a.tournament_stars_count, a.tournament_cups_count = 3, 1
    b.tournament_stars_count, b.tournament_cups_count = 8, 0
    db_session.add_all([a, b])
    await db_session.commit()

    stars = await get_player_tournament_ranking(db_session, PlayerTournamentRankingMetric.stars, current_user_id=a.id)
    assert [e.value for e in stars.top][:2] == [8, 3]
    assert [e.user_id for e in stars.top][:2] == [b.id, a.id]
    assert len(stars.top) == 2  # the never-applied user is excluded

    cups = await get_player_tournament_ranking(db_session, PlayerTournamentRankingMetric.cups, current_user_id=a.id)
    assert [e.value for e in cups.top][:2] == [1, 0]
    assert [e.user_id for e in cups.top][:2] == [a.id, b.id]


async def test_ranking_me_reflects_current_users_rank(client, db_session, bot_token):
    a = await make_ready_user(client, db_session, bot_token, 890010)
    b = await make_ready_user(client, db_session, bot_token, 890011)
    await _make_participant(db_session, a, b)
    a.tournament_stars_count, b.tournament_stars_count = 1, 5
    db_session.add_all([a, b])
    await db_session.commit()

    result = await get_player_tournament_ranking(db_session, PlayerTournamentRankingMetric.stars, current_user_id=a.id)
    assert result.me is not None
    assert result.me.user_id == a.id
    assert result.me.rank == 2


async def test_ranking_excludes_banned_and_admin(client, db_session, bot_token):
    a = await make_ready_user(client, db_session, bot_token, 890020)
    await _make_participant(db_session, a)
    a.tournament_stars_count = 5
    a.is_admin = True
    db_session.add(a)
    await db_session.commit()

    result = await get_player_tournament_ranking(db_session, PlayerTournamentRankingMetric.stars, current_user_id=a.id)
    assert result.top == []
    assert result.me is None
