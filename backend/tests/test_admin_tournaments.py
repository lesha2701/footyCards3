from app.models.club import Club
from app.models.enums import TournamentStatus
from app.models.tournament import Tournament, TournamentClub
from app.models.tournament_queue import TournamentQueue, TournamentQueueEntry, TournamentQueueState
from app.models.tournament_standing import TournamentClubStanding
from tests.utils import telegram_headers


async def _admin_auth(client, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    token = session_resp.json()["admin_token"]
    return {"Authorization": f"Bearer {token}"}


async def _make_bare_club(db_session, name: str, invite_code: str) -> Club:
    club = Club(name=name, description="", club_type="open", logo_shape="shield", logo_color="#000", captain_id=1, invite_code=invite_code)
    db_session.add(club)
    await db_session.flush()
    return club


async def test_list_tournaments_requires_admin(client):
    resp = await client.get("/api/v1/admin/tournaments")
    assert resp.status_code == 401


async def test_list_and_stats_and_detail(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)

    active = Tournament(status=TournamentStatus.active, rounds_simulated=3)
    completed = Tournament(status=TournamentStatus.completed, rounds_simulated=14)
    db_session.add_all([active, completed])
    await db_session.flush()

    clubs = [await _make_bare_club(db_session, f"AdminTourn{i}", f"admtrn{i}") for i in range(2)]
    db_session.add_all(
        [
            TournamentClub(tournament_id=active.id, club_id=clubs[0].id),
            TournamentClub(tournament_id=completed.id, club_id=clubs[0].id),
            TournamentClub(tournament_id=completed.id, club_id=clubs[1].id),
        ]
    )
    db_session.add_all(
        [
            TournamentClubStanding(tournament_id=completed.id, club_id=clubs[0].id, points=10, goals_for=5, goals_against=1),
            TournamentClubStanding(tournament_id=completed.id, club_id=clubs[1].id, points=4, goals_for=2, goals_against=3),
        ]
    )
    await db_session.commit()

    stats_resp = await client.get("/api/v1/admin/tournaments/stats", headers=auth)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["active_count"] >= 1
    assert stats["completed_count"] >= 1

    list_resp = await client.get(
        "/api/v1/admin/tournaments", params={"status": "active", "page_size": 100}, headers=auth
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    active_ids = {i["id"] for i in items}
    assert active.id in active_ids
    assert completed.id not in active_ids
    matched = next(i for i in items if i["id"] == active.id)
    assert matched["club_count"] == 1
    assert matched["rounds_simulated"] == 3

    detail_resp = await client.get(f"/api/v1/admin/tournaments/{completed.id}", headers=auth)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["status"] == "completed"
    assert len(detail["standings"]) == 2
    assert detail["standings"][0]["club_id"] == clubs[0].id
    assert detail["standings"][0]["final_rank"] == 1


async def test_get_tournament_detail_404(client, bot_token):
    auth = await _admin_auth(client, bot_token)
    resp = await client.get("/api/v1/admin/tournaments/999999", headers=auth)
    assert resp.status_code == 404


async def test_stats_reports_current_queue_depth(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)

    queue = TournamentQueue(status="open")
    db_session.add(queue)
    await db_session.flush()
    state = TournamentQueueState(id=1, current_queue_id=queue.id)
    db_session.add(state)

    clubs = [await _make_bare_club(db_session, f"QueuedClub{i}", f"queued{i}") for i in range(3)]
    db_session.add_all([TournamentQueueEntry(queue_id=queue.id, club_id=c.id) for c in clubs])
    await db_session.commit()

    resp = await client.get("/api/v1/admin/tournaments/stats", headers=auth)
    assert resp.status_code == 200
    assert resp.json()["queued_club_count"] == 3
