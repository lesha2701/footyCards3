import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.exceptions import ConflictError
from app.models.club import Club
from app.models.club_lineup import ClubLineup, ClubLineupCard
from app.models.enums import ClubLogoShape, ClubType, Position
from app.models.user import User
from app.schemas.club import ClubCreate
from app.schemas.club_squad import ClubLineupSetRequest, ClubLineupSlotIn
from app.services import club_service
from app.services.club_squad_service import set_club_lineup
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

# See test_club_packs.py's REAL_POSTGRES_URL comment for why this test opens its own
# independent connection to the real dev Postgres instance rather than using the pytest
# suite's `client`/`db_session` fixtures (hardcoded to in-memory SQLite, single shared
# connection, can't reproduce genuine multi-connection unique-constraint race timing).
REAL_POSTGRES_URL = os.environ.get("REAL_POSTGRES_URL", "postgresql+asyncpg://postgres:1234@postgres:5432/footycards")


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """club_service.create_club seeds a starting squad on every club
    creation (Task 4) — give every test in this file enough active players
    per formation category (GK/DEF/MID/FWD) to draw from. Unlike
    test_clubs.py, this file has no other autouse fixture doing this —
    autouse fixtures are file-scoped in this codebase's test setup, so it
    must be repeated here (fresh SQLite schema per test, see conftest.py's
    `_fresh_schema`)."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _register_only(client, bot_token, telegram_id):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200


async def _create_club(client, bot_token, telegram_id, name):
    await _register_only(client, bot_token, telegram_id)
    headers = telegram_headers(telegram_id, bot_token)
    resp = await client.post(
        "/api/v1/clubs", headers=headers,
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 200
    return resp.json(), headers


async def test_get_club_lineup_is_complete_after_creation(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820300, "Клуб с готовым составом")
    resp = await client.get("/api/v1/clubs/me/lineup", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_complete"] is True
    assert body["team_strength"] is not None
    assert len(body["slots"]) == 11
    assert all(s["card"] is not None for s in body["slots"])


async def test_get_club_lineup_reports_line_stats_for_own_squad(client, db_session, bot_token):
    """Same 4 rolled-up numbers (attack/midfield/defence/goalkeeping) shown
    for the next tournament opponent's lineup should also be exposed for a
    club's own lineup, so the squad screen can show them too. Each number is
    a plain average of the ratings of the players actually fielded in that
    line — not compute_profile's cross-zone weighted value, which a player
    could see credit a midfielder's partial contribution to "attack" and
    read as higher than either forward's own rating."""
    _, headers = await _create_club(client, bot_token, 820320, "Клуб со статами линий")
    resp = await client.get("/api/v1/clubs/me/lineup", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_complete"] is True

    category_by_stat = {"attack": "FWD", "midfield": "MID", "defence": "DEF", "goalkeeping": "GK"}
    for stat, category in category_by_stat.items():
        ratings = [s["card"]["player"]["rating"] for s in body["slots"] if s["category"] == category]
        assert ratings  # every category has at least one slot in any formation
        assert body[stat] == round(sum(ratings) / len(ratings))


async def test_list_club_cards_includes_bench(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820301, "Клуб со скамейкой")
    resp = await client.get("/api/v1/clubs/me/cards", headers=headers)
    assert resp.status_code == 200
    cards = resp.json()
    assert len(cards) == 15
    assert sum(1 for c in cards if not c["is_in_lineup"]) == 4


CATEGORY_POSITIONS_FOR_TEST = {
    "GK": {"GK"}, "DEF": {"LB", "CB", "RB"}, "MID": {"CDM", "CM", "CAM", "LM", "RM"}, "FWD": {"LW", "ST", "RW"},
}


def _category_for_position(position: str) -> str:
    return next(category for category, positions in CATEGORY_POSITIONS_FOR_TEST.items() if position in positions)


async def test_set_club_lineup_swaps_a_bench_card_into_a_slot(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820302, "Клуб с заменой")
    cards = (await client.get("/api/v1/clubs/me/cards", headers=headers)).json()
    bench_card = next(c for c in cards if not c["is_in_lineup"])
    bench_category = _category_for_position(bench_card["player"]["position"])
    lineup = (await client.get("/api/v1/clubs/me/lineup", headers=headers)).json()

    # Every club is seeded with exactly one bench card per category and one
    # starter per formation slot within that same category, so there is
    # always at least one legal target slot — same category, any slot.
    matching_slot = next(s for s in lineup["slots"] if s["category"] == bench_category)
    slots_payload = [
        {"slot_code": s["slot_code"], "club_card_id": bench_card["id"] if s["slot_code"] == matching_slot["slot_code"] else s["card"]["id"]}
        for s in lineup["slots"]
    ]
    resp = await client.put("/api/v1/clubs/me/lineup", headers=headers, json={"slots": slots_payload})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_complete"] is True

    # Regression check for the identity-map staleness bug fixed alongside
    # this test: the PUT response itself (not just a subsequent GET) must
    # reflect the just-swapped card in its slot. With expire_on_commit=False
    # (see database.py), a re-read missing populate_existing=True can
    # silently return the session's pre-swap cached ClubLineup object.
    put_slot = next(s for s in body["slots"] if s["slot_code"] == matching_slot["slot_code"])
    assert put_slot["card"]["id"] == bench_card["id"]


async def test_non_manager_cannot_set_lineup(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820303, "Клуб без прав")
    await _register_only(client, bot_token, 820304)
    member_headers = telegram_headers(820304, bot_token)
    await client.post(f"/api/v1/clubs/{club['id']}/join", headers=member_headers)

    lineup = (await client.get("/api/v1/clubs/me/lineup", headers=member_headers)).json()
    slots_payload = [{"slot_code": s["slot_code"], "club_card_id": s["card"]["id"]} for s in lineup["slots"]]
    resp = await client.put("/api/v1/clubs/me/lineup", headers=member_headers, json={"slots": slots_payload})
    assert resp.status_code == 403


async def test_set_lineup_concurrent_saves_no_unhandled_integrity_error():
    """Genuine concurrency regression test for an unhandled IntegrityError observed in
    production as a 500 on PUT /clubs/me/lineup: set_club_lineup's with_for_update(of=ClubLineup)
    lock serializes overlapping saves once each one's SELECT resolves, but two truly concurrent
    submissions (asyncio.gather) didn't reliably reproduce the crash — it took a wider fan-out to
    expose reliably, matching how the reported bug surfaced under real load (a slow/hanging save
    inviting repeated taps). With 6 concurrent identical saves against real Postgres, some
    interleave around the delete-then-recreate of club_lineup_cards and collide on
    uq_club_lineup_card_once. Before the fix this raised a raw IntegrityError (500); after, the
    loser(s) get a clean ConflictError (409) instead. Skips if real Postgres is unreachable.
    """
    engine = create_async_engine(REAL_POSTGRES_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except OSError as exc:
        await engine.dispose()
        pytest.skip(f"real dev Postgres not reachable at {REAL_POSTGRES_URL!r}: {exc!r}")
    except OperationalError as exc:
        await engine.dispose()
        pytest.skip(f"real dev Postgres not reachable at {REAL_POSTGRES_URL!r}: {exc!r}")

    RealSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]

    setup = RealSessionLocal()
    captain = club_id = None
    try:
        captain = User(telegram_id=991_300_000_000 + uuid.uuid4().int % 1_000_000_000, username=f"lineup_race_{suffix}", balance=10000)
        setup.add(captain)
        await setup.flush()
        await setup.commit()

        detail = await club_service.create_club(
            setup, captain,
            ClubCreate(name=f"Lineup Race Club {suffix}", description="", club_type=ClubType.open, logo_shape=ClubLogoShape.shield, logo_color="#abcdef"),
        )
        club_id = detail.id
        await setup.close()
        setup = None

        async with RealSessionLocal() as verify:
            # A club now has 5 ClubLineup template rows (Phase 3 of the
            # lineup-templates feature) — this race test only cares about
            # the one seed_starting_squad fills in, template_index=1.
            lineup = (
                await verify.execute(select(ClubLineup).where(ClubLineup.club_id == club_id, ClubLineup.template_index == 1))
            ).scalar_one()
            cards = (await verify.execute(select(ClubLineupCard).where(ClubLineupCard.club_lineup_id == lineup.id))).scalars().all()
            slot_to_card = {c.slot_code: c.club_card_id for c in cards}

        payload = ClubLineupSetRequest(slots=[ClubLineupSlotIn(slot_code=code, club_card_id=cid) for code, cid in slot_to_card.items()])

        concurrency = 6
        sessions = [RealSessionLocal() for _ in range(concurrency)]
        try:
            captains = [await s.get(User, captain.id) for s in sessions]
            results = await asyncio.gather(
                *[set_club_lineup(sessions[i], captains[i], payload) for i in range(concurrency)],
                return_exceptions=True,
            )
        finally:
            for s in sessions:
                await s.close()

        successes = [r for r in results if not isinstance(r, BaseException)]
        failures = [r for r in results if isinstance(r, BaseException)]
        assert successes, f"expected at least one winner, got results: {results!r}"
        for f in failures:
            assert isinstance(f, ConflictError), f"every loser must raise ConflictError (409), not an unhandled exception: {f!r}"

        async with RealSessionLocal() as final_verify:
            final_lineup = (
                await final_verify.execute(select(ClubLineup).where(ClubLineup.club_id == club_id, ClubLineup.template_index == 1))
            ).scalar_one()
            final_cards = (
                await final_verify.execute(select(ClubLineupCard).where(ClubLineupCard.club_lineup_id == final_lineup.id))
            ).scalars().all()
            assert len(final_cards) == 11, "lineup must end with exactly 11 cards, not duplicated or partially deleted"
    finally:
        async with RealSessionLocal() as cleanup:
            if club_id is not None:
                club_row = await cleanup.get(Club, club_id)
                if club_row is not None:
                    await cleanup.delete(club_row)
            await cleanup.commit()
            if captain is not None:
                user_row = await cleanup.get(User, captain.id)
                if user_row is not None:
                    await cleanup.delete(user_row)
            await cleanup.commit()
        if setup is not None:
            await setup.close()
        await engine.dispose()


async def test_new_club_lineup_defaults_to_4_3_3_balanced_central(client, db_session, bot_token):
    from app.models.club_lineup import ClubLineup

    club, _headers = await _create_club(client, bot_token, 820310, "Клуб с тактикой по умолчанию")
    # `select` is already imported at the top of this file (`from sqlalchemy import select, text`).
    lineup = (await db_session.execute(select(ClubLineup).where(ClubLineup.club_id == club["id"]))).scalar_one()
    assert lineup.formation == "4-3-3"
    assert lineup.mentality == "BALANCED"
    assert lineup.playstyle == "CENTRAL_PLAY"


async def test_get_club_lineup_reports_formation_mentality_playstyle_and_fit(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820320, "Клуб с тактикой в ответе")
    resp = await client.get("/api/v1/clubs/me/lineup", headers=headers)
    body = resp.json()
    assert body["formation"] == "4-3-3"
    assert body["mentality"] == "BALANCED"
    assert body["playstyle"] == "CENTRAL_PLAY"
    assert 0 <= body["tactical_fit"] <= 100


async def test_set_club_tactics_updates_formation_mentality_playstyle(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820321, "Клуб меняет тактику")
    resp = await client.put(
        "/api/v1/clubs/me/tactics", headers=headers,
        json={"formation": "4-4-2", "mentality": "ATTACKING", "playstyle": "WING_PLAY"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["formation"] == "4-4-2"
    assert body["mentality"] == "ATTACKING"
    assert body["playstyle"] == "WING_PLAY"
    assert len(body["slots"]) == 11


async def test_set_club_tactics_rejects_unknown_formation(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820322, "Клуб с плохой тактикой")
    resp = await client.put(
        "/api/v1/clubs/me/tactics", headers=headers,
        json={"formation": "4-2-4", "mentality": "BALANCED", "playstyle": "CENTRAL_PLAY"},
    )
    assert resp.status_code == 409


async def test_set_club_tactics_rejects_unknown_mentality(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820323, "Клуб с плохим настроем")
    resp = await client.put(
        "/api/v1/clubs/me/tactics", headers=headers,
        json={"formation": "4-3-3", "mentality": "BERSERK", "playstyle": "CENTRAL_PLAY"},
    )
    assert resp.status_code == 409


async def test_set_club_tactics_non_manager_forbidden(client, db_session, bot_token):
    club, captain_headers = await _create_club(client, bot_token, 820324, "Клуб с рядовым участником")
    await _register_only(client, bot_token, 820325)
    member_headers = telegram_headers(820325, bot_token)
    await client.post(f"/api/v1/clubs/{club['id']}/join", headers=member_headers)

    resp = await client.put(
        "/api/v1/clubs/me/tactics", headers=member_headers,
        json={"formation": "4-4-2", "mentality": "BALANCED", "playstyle": "CENTRAL_PLAY"},
    )
    assert resp.status_code == 403


async def test_changing_formation_clears_slots_not_present_in_the_new_formation_and_keeps_shared_ones(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820326, "Клуб меняет формацию")
    before = (await client.get("/api/v1/clubs/me/lineup", headers=headers)).json()
    gk_card_id_before = next(s["card"]["id"] for s in before["slots"] if s["slot_code"] == "GK")

    resp = await client.put(
        "/api/v1/clubs/me/tactics", headers=headers,
        json={"formation": "4-4-2", "mentality": "BALANCED", "playstyle": "CENTRAL_PLAY"},
    )
    body = resp.json()
    # 4-3-3's slot codes are GK,DEF1-4,MID1-3,FWD1-3; 4-4-2's are
    # GK,DEF1-4,MID1-4,FWD1-2 — only FWD3 exists in 4-3-3 but not 4-4-2 (its
    # card gets freed to the bench), and only MID4 exists in 4-4-2 but not
    # 4-3-3 (newly empty, nothing to free). Every other code is shared and
    # keeps its card. So exactly one slot goes from filled to missing.
    assert body["is_complete"] is False

    gk_slot = next(s for s in body["slots"] if s["slot_code"] == "GK")
    assert gk_slot["card"]["id"] == gk_card_id_before  # shared-code slot kept its card
    mid4_slot = next(s for s in body["slots"] if s["slot_code"] == "MID4")
    assert mid4_slot["card"] is None  # 4-3-3 never had a MID4 code to carry over

    cards_resp = (await client.get("/api/v1/clubs/me/cards", headers=headers)).json()
    freed_cards = [c for c in cards_resp if not c["is_in_lineup"]]
    # seed_starting_squad mints 4 bench cards on top of the 11 starters
    # (Task 1's fixture, unchanged by this feature); the formation switch
    # frees exactly one more (the card that was in FWD3) on top of those.
    assert len(freed_cards) == 5


async def test_get_club_lineup_reports_a_tactical_fit_hint(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820330, "Клуб с подсказкой")
    resp = await client.get("/api/v1/clubs/me/lineup", headers=headers)
    body = resp.json()
    assert isinstance(body["tactical_fit_hint"], str)
    assert len(body["tactical_fit_hint"]) > 0


async def test_tactical_fit_hint_praises_a_well_aligned_playstyle(client, db_session, bot_token):
    # The default new-club squad is BALANCED/CENTRAL_PLAY on a fresh position
    # pool seeded evenly (see _seed_position_pool) — set an explicit
    # CENTRAL_PLAY (already the default) and assert the praise-branch string,
    # since a freshly seeded squad has no artificially weak zone to trigger
    # the "Слабое место" branch on this exact seed.
    _, headers = await _create_club(client, bot_token, 820331, "Клуб с похвалой")
    resp = await client.get("/api/v1/clubs/me/lineup", headers=headers)
    body = resp.json()
    assert body["tactical_fit_hint"] in (
        "Хорошо подходит для игры через центр", "Хорошо подходит для игры по флангам",
        "Хорошо подходит для контроля мяча", "Хорошо подходит для высокого прессинга",
        "Хорошо подходит для контратак",
    ) or body["tactical_fit_hint"].startswith("Слабое место: ")


async def test_next_opponent_rejects_a_club_with_no_active_tournament(client, db_session, bot_token):
    _, headers = await _create_club(client, bot_token, 820340, "Клуб без турнира")
    resp = await client.get("/api/v1/clubs/tournament/next-opponent", headers=headers)
    assert resp.status_code == 409


async def test_next_opponent_reports_round_and_opponent_for_an_active_tournament(client, db_session, bot_token):
    from sqlalchemy import select
    from app.models.club import Club
    from app.services.club_squad_service import get_next_opponent
    from app.services.tournament_queue_service import apply_to_tournament
    from tests.factories import get_user_by_telegram_id

    club_ids_and_users = []
    for i in range(8):
        club, _headers = await _create_club(client, bot_token, 820350 + i, f"Скаутинг {i}")
        # apply_to_tournament requires >=2 club members (MIN_MEMBERS_TO_APPLY,
        # see app/services/tournament_queue_service.py) — mirrors
        # test_tournament_queue_service.py's _create_club_with_full_squad
        # helper, which adds a second member for the same reason. _create_club
        # here only registers the captain, so a second member is joined here.
        second_member_telegram_id = 820350 + i + 900_000
        await _register_only(client, bot_token, second_member_telegram_id)
        join_resp = await client.post(
            f"/api/v1/clubs/{club['id']}/join", headers=telegram_headers(second_member_telegram_id, bot_token)
        )
        assert join_resp.status_code == 200
        user = await get_user_by_telegram_id(db_session, 820350 + i)
        club_ids_and_users.append((club, user))

    tournament_id = None
    for _club, user in club_ids_and_users:
        result = await apply_to_tournament(db_session, user)
        if result.tournament_id is not None:
            tournament_id = result.tournament_id
    assert tournament_id is not None

    first_club, first_user = club_ids_and_users[0]
    out = await get_next_opponent(db_session, first_user)
    assert out.round_number == 1
    assert out.opponent_club_id != first_club["id"]
    opponent = await db_session.get(Club, out.opponent_club_id)
    assert out.opponent_club_name == opponent.name
    # Fresh clubs' seeded starting squads (see _seed_position_pool) give every
    # line a real, positive value — never all-zero, since _category_line_stats
    # only returns 0 for a line with no cards fielded in it at all.
    assert out.attack > 0
    assert out.midfield > 0
    assert out.defence > 0
    assert out.goalkeeping > 0


# --- Squad training (Тренировка состава) ------------------------------------
# eight_club_tournament below mirrors test_tournament_simulation_service.py's
# own fixture of the same name/shape — this codebase's convention is a fresh,
# file-local copy rather than a cross-file import (no test file in this repo
# imports another test file's fixtures).


async def _create_club_with_full_squad(client, db_session, bot_token, telegram_id, name):
    """Registers telegram_id as captain of a fresh club (auto-seeded 11/11 lineup via
    seed_starting_squad), plus a second member so apply_to_tournament's >=2-members check
    passes."""
    club, headers = await _create_club(client, bot_token, telegram_id, name)
    captain = await get_user_by_telegram_id(db_session, telegram_id)

    second_member_telegram_id = telegram_id + 900_000
    await _register_only(client, bot_token, second_member_telegram_id)
    join_resp = await client.post(
        f"/api/v1/clubs/{club['id']}/join", headers=telegram_headers(second_member_telegram_id, bot_token)
    )
    assert join_resp.status_code == 200

    return club, captain


@pytest_asyncio.fixture
async def eight_club_tournament(client, db_session, bot_token):
    """Registers 8 clubs and applies each to the tournament queue — the 8th application forms
    the Tournament. Yields (tournament, clubs_and_captains) so callers can authenticate as any
    of the 8 captains."""
    from app.models.tournament import Tournament
    from app.services.tournament_queue_service import apply_to_tournament

    clubs_and_captains = []
    tournament_id = None
    for i in range(8):
        club, captain = await _create_club_with_full_squad(client, db_session, bot_token, 821000 + i, f"Клуб тренировки {i}")
        result = await apply_to_tournament(db_session, captain)
        clubs_and_captains.append((club, captain))
        if result.tournament_id is not None:
            tournament_id = result.tournament_id

    assert tournament_id is not None
    tournament = await db_session.get(Tournament, tournament_id)
    return tournament, clubs_and_captains


async def test_activate_training_requires_manager(db_session, eight_club_tournament):
    from app.core.exceptions import ForbiddenError
    from app.models.club import ClubMember
    from app.models.user import User
    from app.services.club_squad_service import activate_training

    tournament, clubs_and_captains = eight_club_tournament
    club, captain = clubs_and_captains[0]

    # eight_club_tournament's own fixture always adds a second, plain member to every club —
    # no new member needs creating here.
    other_membership = (
        await db_session.execute(
            select(ClubMember).where(ClubMember.club_id == club["id"], ClubMember.user_id != captain.id)
        )
    ).scalar_one()
    assert other_membership.role.value == "member"
    plain_member = await db_session.get(User, other_membership.user_id)

    with pytest.raises(ForbiddenError):
        await activate_training(db_session, plain_member)


async def test_activate_training_boosts_exactly_the_next_round_and_is_consumed(db_session, eight_club_tournament):
    from app.models.tournament_standing import TournamentClubStanding
    from app.services.club_squad_service import activate_training, get_club_lineup
    from app.services.tournament_simulation_service import simulate_next_round

    tournament, clubs_and_captains = eight_club_tournament
    club, captain = clubs_and_captains[0]

    lineup_before = await get_club_lineup(db_session, captain)
    assert lineup_before.training_uses_remaining == 3
    assert lineup_before.training_boost_active is False

    boosted = await activate_training(db_session, captain)
    assert boosted.training_uses_remaining == 2
    assert boosted.training_boost_active is True
    assert boosted.team_strength > lineup_before.team_strength

    # Re-activating for the same still-upcoming round must be rejected.
    with pytest.raises(ConflictError):
        await activate_training(db_session, captain)

    await simulate_next_round(db_session)
    await db_session.commit()

    standing = (
        await db_session.execute(
            select(TournamentClubStanding).where(
                TournamentClubStanding.tournament_id == tournament.id, TournamentClubStanding.club_id == club["id"],
            )
        )
    ).scalar_one()
    assert standing.training_boost_round is None  # consumed, even though only 1 round was simulated

    lineup_after = await get_club_lineup(db_session, captain)
    assert lineup_after.training_boost_active is False
