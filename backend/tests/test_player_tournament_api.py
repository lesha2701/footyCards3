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


async def test_card_arena_tactics_style_and_next_opponent(client, db_session, bot_token):
    """Tactics like Card Arena: a style of four in a circle on the squad,
    the rules, and the next opponent's style with what it means for my lines."""
    users = [await make_ready_user(client, db_session, bot_token, 880500 + i) for i in range(16)]
    h = telegram_headers(880500, bot_token)
    view = (await client.get(f"{BASE}/tactics", headers=h)).json()
    assert [s["value"] for s in view["rules"]["styles"]] == ["attacking", "possession", "defensive", "counter"]
    assert view["next"] is None  # not in a tournament yet

    resp = await client.put(f"{BASE}/squads/1/tactics", headers=h, json={"formation": "4-3-3", "style": "attacking"})
    assert resp.status_code == 200 and resp.json()["style"] == "attacking"
    bad = await client.put(f"{BASE}/squads/1/tactics", headers=h, json={"formation": "4-3-3", "style": "chaos"})
    assert bad.status_code == 409
    # An old client without a style keeps the chosen one.
    resp = await client.put(f"{BASE}/squads/1/tactics", headers=h, json={"formation": "4-3-3", "mentality": "BALANCED", "playstyle": "WING_PLAY"})
    assert resp.json()["style"] == "attacking"

    for u in users:
        await apply_to_tournament(db_session, u)
    view = (await client.get(f"{BASE}/tactics", headers=h)).json()
    nxt = view["next"]
    assert nxt["round"] == 1 and nxt["opponent"]
    from sqlalchemy import select

    from app.models.player_tournament import PlayerTournamentParticipant
    from app.services.player_tournament_fixture_service import generate_fixtures

    order = list((await db_session.execute(
        select(PlayerTournamentParticipant.user_id).order_by(PlayerTournamentParticipant.id)
    )).scalars().all())
    me = users[0].id
    opponent_id = next(b if a == me else a for r, a, b in generate_fixtures(order) if r == 1 and me in (a, b))
    opponent = next(u for u in users if u.id == opponent_id)
    await client.put(f"{BASE}/squads/1/tactics", headers=telegram_headers(opponent.telegram_id, bot_token),
                     json={"formation": "4-3-3", "style": "defensive"})
    nxt = (await client.get(f"{BASE}/tactics", headers=h)).json()["next"]
    edge = view["rules"]["edge_pct"]
    assert nxt["style"] == "defensive" and nxt["edge"] == "win"
    assert nxt["mods"] == {"GK": -4 + edge, "DEF": -4 + edge, "MID": 2 + edge, "FWD": 6 + edge}

    await simulate_next_round(db_session)
    assert (await client.get(f"{BASE}/tactics", headers=h)).json()["next"]["round"] == 2


def test_tactics_change_the_match_ratings():
    from types import SimpleNamespace

    from app.services import manager_tactics

    config = SimpleNamespace(ptour_style_edge_pct=10, ptour_formation_effect_pct=0)
    mods = manager_tactics.modifiers("counter", "3-4-3", "attacking", config, "ptour")
    assert mods == {"GK": 10, "DEF": 13, "MID": 8, "FWD": 13}  # counter beats attacking, no formation tilt
    assert manager_tactics.apply(70, "FWD", mods) == 79
    even = manager_tactics.modifiers("possession", "4-3-3", "attacking", config, "ptour")
    assert even == {"GK": 0, "DEF": 0, "MID": 6, "FWD": 0}
