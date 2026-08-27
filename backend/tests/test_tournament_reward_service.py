from sqlalchemy import select

from app.models.club import Club
from app.models.tournament import Tournament
from app.models.tournament_result import TournamentClubResult
from app.models.tournament_standing import TournamentClubStanding
from app.services.game_config_service import get_config
from app.services.tournament_reward_service import conclude_tournament


async def _make_club(db_session, name: str) -> Club:
    club = Club(name=name, description="", club_type="open", logo_shape="shield", logo_color="#000", captain_id=1, invite_code=name[:8])
    db_session.add(club)
    await db_session.flush()
    return club


async def test_conclude_awards_cups_stars_budget_by_rank(db_session):
    tournament = Tournament(rounds_simulated=14)
    db_session.add(tournament)
    await db_session.flush()

    clubs = [await _make_club(db_session, f"Club{i}") for i in range(8)]
    standings = []
    for i, club in enumerate(clubs):
        s = TournamentClubStanding(tournament_id=tournament.id, club_id=club.id, points=(8 - i) * 3, goals_for=10, goals_against=0)
        db_session.add(s)
        standings.append(s)
    await db_session.flush()

    config = await get_config(db_session)
    results = await conclude_tournament(db_session, tournament, standings, matches=[])
    await db_session.commit()

    by_club = {r.club_id: r for r in results}
    first_result = by_club[clubs[0].id]
    assert first_result.final_rank == 1
    assert first_result.cup_awarded is True
    assert first_result.stars_delta == 3
    assert first_result.budget_awarded == config.club_tournament_budget_place_1

    last_result = by_club[clubs[7].id]
    assert last_result.final_rank == 8
    assert last_result.stars_delta == -3
    assert last_result.cup_awarded is False

    await db_session.refresh(clubs[0])
    assert clubs[0].cups_count == 1
    assert clubs[0].stars_count == 3
    assert clubs[0].budget == config.club_tournament_budget_place_1

    await db_session.refresh(clubs[7])
    assert clubs[7].stars_count == -3


async def test_conclude_leaves_4th_and_5th_stars_unchanged(db_session):
    tournament = Tournament(rounds_simulated=14)
    db_session.add(tournament)
    await db_session.flush()
    clubs = [await _make_club(db_session, f"ClubB{i}") for i in range(8)]
    standings = [TournamentClubStanding(tournament_id=tournament.id, club_id=c.id, points=(8 - i) * 3) for i, c in enumerate(clubs)]
    db_session.add_all(standings)
    await db_session.flush()

    results = await conclude_tournament(db_session, tournament, standings, matches=[])
    by_rank = {r.final_rank: r for r in results}
    assert by_rank[4].stars_delta == 0
    assert by_rank[5].stars_delta == 0


async def test_conclude_tournament_notifies_every_club(db_session):
    from sqlalchemy import select

    from app.models.club import ClubMember
    from app.models.enums import NotificationType
    from app.models.notification import Notification
    from app.models.tournament import Tournament
    from app.models.tournament_standing import TournamentClubStanding
    from app.models.user import User
    from app.services.tournament_reward_service import conclude_tournament

    tournament = Tournament(rounds_simulated=14)
    db_session.add(tournament)
    await db_session.flush()

    clubs = [await _make_club(db_session, f"CNotif{i}") for i in range(8)]
    standings = []
    for i, club in enumerate(clubs):
        user = User(telegram_id=900000 + i, first_name="T")
        db_session.add(user)
        await db_session.flush()
        db_session.add(ClubMember(club_id=club.id, user_id=user.id, role="captain"))
        s = TournamentClubStanding(tournament_id=tournament.id, club_id=club.id, points=(8 - i) * 3)
        db_session.add(s)
        standings.append(s)
    await db_session.flush()

    await conclude_tournament(db_session, tournament, standings, matches=[])
    await db_session.commit()

    notifications = (
        await db_session.execute(select(Notification).where(Notification.type == NotificationType.club_tournament_results_ready))
    ).scalars().all()
    assert len(notifications) == 8  # one captain per club, per this test's minimal setup
