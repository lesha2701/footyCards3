from app.services.player_tournament_queue_service import apply_to_tournament
from app.services.player_tournament_simulation_service import simulate_next_round
from tests.player_tournament_helpers import make_ready_user
from tests.utils import telegram_headers

BASE = "/api/v1/player-tournaments"


async def test_squads_list_and_tactics(client, db_session, bot_token):
    user = await make_ready_user(client, db_session, bot_token, 880001)
    h = telegram_headers(880001, bot_token)
    resp = await client.get(f"{BASE}/squads", headers=h)
    assert resp.status_code == 200
    squads = resp.json()
    assert [s["template_index"] for s in squads] == [1, 2, 3, 4, 5]
    assert squads[0]["is_complete"] is True

    resp = await client.put(
        f"{BASE}/squads/1/tactics", headers=h,
        json={"formation": "4-4-2", "mentality": "DEFENSIVE", "playstyle": "POSSESSION"},
    )
    assert resp.status_code == 200 and resp.json()["formation"] == "4-4-2"

    resp = await client.post(f"{BASE}/squads/2/activate", headers=h)
    assert resp.status_code == 200 and resp.json()["is_active"] is True

    resp = await client.put(f"{BASE}/squads/2/name", headers=h, json={"name": "Атакующий"})
    assert resp.json()["name"] == "Атакующий"


async def test_apply_current_and_full_flow(client, db_session, bot_token):
    users = [await make_ready_user(client, db_session, bot_token, 880100 + i) for i in range(16)]
    for u in users[:15]:
        await apply_to_tournament(db_session, u)
    h = telegram_headers(880100 + 15, bot_token)
    resp = await client.post(f"{BASE}/apply", headers=h)
    assert resp.status_code == 200 and resp.json()["tournament_id"] is not None
    tournament_id = resp.json()["tournament_id"]

    resp = await client.get(f"{BASE}/current", headers=h)
    assert resp.json()["status"] == "active" and resp.json()["tournament_id"] == tournament_id

    await simulate_next_round(db_session)
    resp = await client.get(f"{BASE}/{tournament_id}", headers=h)
    body = resp.json()
    assert resp.status_code == 200 and body["rounds_simulated"] == 1
    assert len(body["standings"]) == 16 and len(body["matches"]) == 8
    assert body["next_round_seconds_remaining"] is not None

    match_id = body["matches"][0]["id"]
    resp = await client.get(f"{BASE}/matches/{match_id}", headers=h)
    assert resp.status_code == 200 and "event_log" in resp.json()


async def test_apply_without_squad_is_409(client, db_session, bot_token):
    from tests.player_tournament_helpers import make_user
    await make_user(client, db_session, bot_token, 880300)
    resp = await client.post(f"{BASE}/apply", headers=telegram_headers(880300, bot_token))
    assert resp.status_code == 409


async def test_leaderboard_sorted_by_metric(client, db_session, bot_token):
    from app.models.player_tournament import PlayerTournament, PlayerTournamentParticipant

    a = await make_ready_user(client, db_session, bot_token, 880400)
    b = await make_ready_user(client, db_session, bot_token, 880401)
    # apply_to_tournament only queues a user until the shared queue reaches
    # TOURNAMENT_SIZE (16) — create the participant rows the leaderboard
    # filters on directly rather than spinning up 16 users here.
    tournament = PlayerTournament()
    db_session.add(tournament)
    await db_session.flush()
    db_session.add(PlayerTournamentParticipant(tournament_id=tournament.id, user_id=a.id))
    db_session.add(PlayerTournamentParticipant(tournament_id=tournament.id, user_id=b.id))
    a.tournament_stars_count, b.tournament_stars_count = 3, 8
    db_session.add_all([a, b])
    await db_session.commit()
    resp = await client.get(f"{BASE}/leaderboard", params={"metric": "stars"}, headers=telegram_headers(880400, bot_token))
    assert resp.status_code == 200
    body = resp.json()
    assert [e["value"] for e in body["top"]][:2] == [8, 3]
    assert body["me"]["user_id"] == a.id
