import pytest_asyncio
from sqlalchemy import func, select

from app.models.club import Club
from app.models.enums import Position
from app.models.tournament import Tournament
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """Same seeding test_tournament_simulation_service.py's own autouse fixture does —
    each club's starter squad needs active Players to draw from per formation
    category."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _create_club_with_full_squad(client, db_session, bot_token, telegram_id, name):
    """Registers telegram_id as captain of a fresh club (auto-seeded 11/11 lineup via
    seed_starting_squad), plus a second member so apply_to_tournament's >=2-members check
    passes. Mirrors test_tournament_simulation_service.py's own helper of the same name (each
    test file gets its own local copy per this codebase's convention — not cross-file
    importable)."""
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    captain = await get_user_by_telegram_id(db_session, telegram_id)

    create_resp = await client.post(
        "/api/v1/clubs", headers=telegram_headers(telegram_id, bot_token),
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert create_resp.status_code == 200
    club = await db_session.get(Club, create_resp.json()["id"])

    second_member_telegram_id = telegram_id + 900_000
    resp2 = await client.post("/api/v1/auth/session", headers=telegram_headers(second_member_telegram_id, bot_token))
    assert resp2.status_code == 200
    join_resp = await client.post(f"/api/v1/clubs/{club.id}/join", headers=telegram_headers(second_member_telegram_id, bot_token))
    assert join_resp.status_code == 200

    return club, captain


@pytest_asyncio.fixture
async def seeded_club_with_full_squad(client, db_session, bot_token):
    """A single tournament-eligible club (full squad, >=2 members) that has never applied to
    the tournament queue — for the not_queued /tournament/current case."""
    return await _create_club_with_full_squad(client, db_session, bot_token, 851000, "Клуб без турнира")


@pytest_asyncio.fixture
async def eight_club_tournament(client, db_session, bot_token):
    """Registers 8 clubs and applies each to the tournament queue — the 8th application forms
    the Tournament. Yields (tournament, clubs_and_captains) so callers can authenticate as any
    of the 8 captains. This is this file's own local copy of the fixture, per the same
    per-file-local convention test_tournament_simulation_service.py established."""
    from app.services.tournament_queue_service import apply_to_tournament

    clubs_and_captains = []
    tournament_id = None
    for i in range(8):
        club, captain = await _create_club_with_full_squad(client, db_session, bot_token, 852000 + i, f"Клуб API {i}")
        result = await apply_to_tournament(db_session, captain)
        clubs_and_captains.append((club, captain))
        if result.tournament_id is not None:
            tournament_id = result.tournament_id

    assert tournament_id is not None
    tournament = await db_session.get(Tournament, tournament_id)
    return tournament, clubs_and_captains


async def test_current_returns_not_queued_for_a_club_never_applied(client, db_session, bot_token, seeded_club_with_full_squad):
    club, captain = seeded_club_with_full_squad
    resp = await client.get("/api/v1/clubs/tournament/current", headers=telegram_headers(captain.telegram_id, bot_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "not_queued"


async def test_current_returns_active_with_standings_after_formation(client, db_session, bot_token, eight_club_tournament):
    tournament, clubs_and_captains = eight_club_tournament
    _, captain = clubs_and_captains[0]
    resp = await client.get("/api/v1/clubs/tournament/current", headers=telegram_headers(captain.telegram_id, bot_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "active"
    assert body["tournament_id"] == tournament.id
    assert body["can_apply"] is False


async def test_current_can_apply_true_when_never_applied(client, db_session, bot_token, seeded_club_with_full_squad):
    club, captain = seeded_club_with_full_squad
    resp = await client.get("/api/v1/clubs/tournament/current", headers=telegram_headers(captain.telegram_id, bot_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["can_apply"] is True
    assert body["cooldown_seconds_remaining"] is None


async def test_current_reports_cooldown_after_tournament_completes_and_can_apply_stays_independent_of_status(
    client, db_session, bot_token, eight_club_tournament
):
    from app.services.tournament_simulation_service import simulate_next_round

    tournament, clubs_and_captains = eight_club_tournament
    club0, captain0 = clubs_and_captains[0]

    for _ in range(14):
        await simulate_next_round(db_session)
        await db_session.commit()
    await db_session.refresh(club0)
    assert club0.last_tournament_applied_at is not None  # conclude_tournament stamps every participant

    resp = await client.get("/api/v1/clubs/tournament/current", headers=telegram_headers(captain0.telegram_id, bot_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["tournament_id"] == tournament.id
    # Default config cooldown is a few hours — freshly concluded, so still cooling down — and
    # this must hold simultaneously with status == "completed", not be masked by it.
    assert body["can_apply"] is False
    assert body["cooldown_seconds_remaining"] is not None
    assert body["cooldown_seconds_remaining"] > 0

    club0.last_tournament_applied_at = None
    db_session.add(club0)
    await db_session.commit()

    resp2 = await client.get("/api/v1/clubs/tournament/current", headers=telegram_headers(captain0.telegram_id, bot_token))
    body2 = resp2.json()
    assert body2["status"] == "completed"  # still shows the last tournament...
    assert body2["can_apply"] is True  # ...while independently reporting the club is free to apply again
    assert body2["cooldown_seconds_remaining"] is None


async def test_detail_returns_standings_sorted_by_rank(client, db_session, bot_token, eight_club_tournament):
    tournament, clubs_and_captains = eight_club_tournament
    _, captain = clubs_and_captains[0]
    resp = await client.get(f"/api/v1/clubs/tournament/{tournament.id}", headers=telegram_headers(captain.telegram_id, bot_token))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["standings"]) == 8
    ranks = [s["final_rank"] for s in body["standings"]]
    assert ranks == sorted(ranks)


async def test_detail_reports_next_round_countdown_while_active_none_once_completed(
    client, db_session, bot_token, eight_club_tournament
):
    from app.services.tournament_simulation_service import simulate_next_round

    tournament, clubs_and_captains = eight_club_tournament
    _, captain = clubs_and_captains[0]

    resp = await client.get(f"/api/v1/clubs/tournament/{tournament.id}", headers=telegram_headers(captain.telegram_id, bot_token))
    assert resp.status_code == 200
    remaining = resp.json()["next_round_seconds_remaining"]
    assert remaining is not None
    assert 0 <= remaining <= 16 * 3600  # slots are at most 16h apart (20:00 -> next day 12:00)

    for _ in range(14):
        await simulate_next_round(db_session)
        await db_session.commit()

    done_resp = await client.get(f"/api/v1/clubs/tournament/{tournament.id}", headers=telegram_headers(captain.telegram_id, bot_token))
    assert done_resp.json()["next_round_seconds_remaining"] is None


async def test_next_round_countdown_is_zero_when_due_slot_not_yet_processed(client, db_session, bot_token, eight_club_tournament):
    """Regression test: a slot's nominal time passing does not mean the bot's sweep has
    actually picked it up yet (it only polls every 15 minutes — see
    bot/services/tournament_scheduler.py's LOOP_CHECK_INTERVAL_SECONDS). Before this fix, the
    countdown assumed any passed slot had already fired and jumped straight to the *next* one
    — e.g. at 20:04 it would claim ~16h remaining until tomorrow's 12:00 slot even though the
    20:00 round simply hadn't been swept yet, which read as "today's round got skipped" to
    players. The most-recently-passed slot is now checked against
    TournamentSimulationSlotLog (the bot's own dedup record of which slots actually ran) —
    unprocessed, it must report due-now (0) instead of a ~16h wait."""
    from datetime import datetime, timedelta

    from app.core.timeutil import app_timezone
    from app.routers.clubs import _SIMULATION_SLOTS

    tournament, clubs_and_captains = eight_club_tournament
    _, captain = clubs_and_captains[0]

    now = datetime.now(app_timezone())
    today_slots = [now.replace(hour=h, minute=m, second=0, microsecond=0) for h, m in _SIMULATION_SLOTS]
    all_instants = sorted(today_slots + [t + timedelta(days=1) for t in today_slots] + [t - timedelta(days=1) for t in today_slots])
    most_recently_passed = [t for t in all_instants if t <= now][-1]

    # No TournamentSimulationSlotLog row exists for this slot (nothing in this test wrote one)
    # — the sweep hasn't confirmed it ran, so the countdown must report due-now.
    resp = await client.get(f"/api/v1/clubs/tournament/{tournament.id}", headers=telegram_headers(captain.telegram_id, bot_token))
    assert resp.json()["next_round_seconds_remaining"] == 0

    # Once the bot's dedup log confirms that exact slot ran, the countdown correctly advances
    # to the real next slot instead of staying pinned at 0.
    from app.models.tournament_simulation_slot_log import TournamentSimulationSlotLog

    db_session.add(TournamentSimulationSlotLog(kind="simulate_round", slot_key=most_recently_passed.strftime("%Y-%m-%dT%H:%M")))
    await db_session.commit()

    resp2 = await client.get(f"/api/v1/clubs/tournament/{tournament.id}", headers=telegram_headers(captain.telegram_id, bot_token))
    remaining = resp2.json()["next_round_seconds_remaining"]
    assert remaining is not None
    assert 0 < remaining <= 16 * 3600


async def test_match_detail_includes_event_log(client, db_session, bot_token, eight_club_tournament):
    from app.services.tournament_simulation_service import simulate_next_round

    tournament, clubs_and_captains = eight_club_tournament
    _, captain = clubs_and_captains[0]
    matches = await simulate_next_round(db_session)
    await db_session.commit()
    match = next(m for m in matches if m.tournament_id == tournament.id)

    resp = await client.get(
        f"/api/v1/clubs/tournament/{tournament.id}/matches/{match.id}", headers=telegram_headers(captain.telegram_id, bot_token)
    )
    assert resp.status_code == 200
    assert isinstance(resp.json()["event_log"], list)


async def test_current_returns_completed_after_tournament_completes_without_reapplying(
    client, db_session, bot_token, eight_club_tournament
):
    """Regression test for the queue-scoping bug: a club that finished its tournament and
    hasn't reapplied still has an old TournamentQueueEntry row sitting in that tournament's
    now-formed, historical queue (entries are never deleted). /tournament/current must not
    mistake that old entry for a live "queued" state — it must instead resolve to the
    completed-tournament branch (previously this fell all the way through to "not_queued",
    the Critical bug fixed by adding the completed check)."""
    from app.services.tournament_simulation_service import simulate_next_round

    tournament, clubs_and_captains = eight_club_tournament
    _, captain = clubs_and_captains[0]

    for _ in range(14):
        await simulate_next_round(db_session)
        await db_session.commit()
    await db_session.refresh(tournament)
    assert tournament.status.value == "completed"

    resp = await client.get("/api/v1/clubs/tournament/current", headers=telegram_headers(captain.telegram_id, bot_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


async def test_current_does_not_crash_with_two_historical_queue_entries(client, db_session, bot_token, eight_club_tournament):
    """Regression test: a club that has played more than one tournament over its lifetime
    accumulates multiple TournamentQueueEntry rows across multiple past, already-`formed`
    queues (entries are never deleted once a queue forms). An unscoped club_id-only lookup
    used to raise MultipleResultsFound in this exact scenario."""
    from app.models.enums import TournamentStatus
    from app.models.tournament_queue import TournamentQueueEntry
    from app.services.tournament_queue_service import apply_to_tournament

    tournament, clubs_and_captains = eight_club_tournament
    club0, captain0 = clubs_and_captains[0]

    # Mark tournament 1 completed and clear club0's cooldown so it's free to queue again
    # (mirrors test_tournament_queue_service.py's own "reapply after completion" test).
    tournament.status = TournamentStatus.completed
    db_session.add(tournament)
    club0.last_tournament_applied_at = None
    db_session.add(club0)
    await db_session.commit()

    # Queue club0 into the new current queue, then bring in 7 more fresh clubs so that queue
    # also fully forms — giving club0 a second TournamentQueueEntry row in a second,
    # now-also-formed queue. Its first entry (in tournament 1's original queue) is still
    # there too, since entries are never deleted.
    result = await apply_to_tournament(db_session, captain0)
    assert result.tournament_id is None  # queued, not yet the 8th application

    tournament2_id = None
    for i in range(7):
        _, captain = await _create_club_with_full_squad(client, db_session, bot_token, 853000 + i, f"Клуб реванша {i}")
        result = await apply_to_tournament(db_session, captain)
        if result.tournament_id is not None:
            tournament2_id = result.tournament_id
    assert tournament2_id is not None  # 8th application formed a second tournament

    # Mark tournament 2 completed too, so club0 currently has no *active* tournament and the
    # endpoint actually falls through to the (previously buggy) queue lookup, and then to the
    # completed-tournament check (club0 belongs to two completed tournaments now — the most
    # recent one, tournament2, should win).
    tournament2 = await db_session.get(Tournament, tournament2_id)
    tournament2.status = TournamentStatus.completed
    db_session.add(tournament2)
    await db_session.commit()

    entry_count = (
        await db_session.execute(select(func.count()).select_from(TournamentQueueEntry).where(TournamentQueueEntry.club_id == club0.id))
    ).scalar_one()
    assert entry_count == 2  # sanity check: this is the exact multi-historical-entry scenario that used to crash

    resp = await client.get("/api/v1/clubs/tournament/current", headers=telegram_headers(captain0.telegram_id, bot_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["tournament_id"] == tournament2_id


async def test_current_returns_completed_with_tournament_id_after_finishing(client, db_session, bot_token, eight_club_tournament):
    from app.services.tournament_simulation_service import simulate_next_round

    tournament, clubs_and_captains = eight_club_tournament
    _, captain = clubs_and_captains[0]

    for _ in range(14):
        await simulate_next_round(db_session)
        await db_session.commit()

    resp = await client.get("/api/v1/clubs/tournament/current", headers=telegram_headers(captain.telegram_id, bot_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["tournament_id"] == tournament.id


async def test_match_detail_synthesizes_description_for_legacy_events_without_one(client, db_session, bot_token, eight_club_tournament):
    from app.services.tournament_simulation_service import simulate_next_round

    tournament, clubs_and_captains = eight_club_tournament
    _, captain = clubs_and_captains[0]
    matches = await simulate_next_round(db_session)
    await db_session.commit()
    match = next(m for m in matches if m.tournament_id == tournament.id)

    # Simulate a "legacy" match by stripping description from the stored event_log,
    # matching what a match simulated before this description-generation feature shipped looks like.
    stripped_log = [{k: v for k, v in event.items() if k != "description"} for event in match.event_log]
    match.event_log = stripped_log
    db_session.add(match)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/clubs/tournament/{tournament.id}/matches/{match.id}", headers=telegram_headers(captain.telegram_id, bot_token)
    )
    assert resp.status_code == 200
    events = resp.json()["event_log"]
    assert events, "expected at least one event"
    assert all(e["description"] for e in events)


async def test_tournament_detail_exposes_reward_fields_only_after_completion(
    client, db_session, bot_token, eight_club_tournament
):
    from app.services.tournament_simulation_service import simulate_next_round

    tournament, clubs_and_captains = eight_club_tournament
    _, captain = clubs_and_captains[0]

    mid_resp = await client.get(f"/api/v1/clubs/tournament/{tournament.id}", headers=telegram_headers(captain.telegram_id, bot_token))
    assert mid_resp.status_code == 200
    assert all(s["budget_awarded"] is None for s in mid_resp.json()["standings"])

    for _ in range(14):
        await simulate_next_round(db_session)
        await db_session.commit()

    done_resp = await client.get(f"/api/v1/clubs/tournament/{tournament.id}", headers=telegram_headers(captain.telegram_id, bot_token))
    assert done_resp.status_code == 200
    standings = done_resp.json()["standings"]
    assert all(s["budget_awarded"] is not None for s in standings)
    assert all(s["stars_delta"] is not None for s in standings)
    winner = next(s for s in standings if s["final_rank"] == 1)
    assert winner["cup_awarded"] is True
    runner_up = next(s for s in standings if s["final_rank"] == 2)
    assert runner_up["cup_awarded"] is False
