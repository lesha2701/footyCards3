from sqlalchemy import func, select

from app.models.enums import TransactionType, TournamentStatus
from app.models.personal_squad import PersonalSquadCard
from app.models.player_tournament import (
    PlayerTournament, PlayerTournamentMatch, PlayerTournamentResult, PlayerTournamentStanding,
)
from app.models.transaction import CoinTransaction
from app.models.user import User
from app.services.game_config_service import get_config
from app.services.player_tournament_queue_service import apply_to_tournament
from app.services.player_tournament_simulation_service import simulate_next_round
from tests.player_tournament_helpers import make_ready_user


async def _form_tournament(client, db_session, bot_token, base_id):
    users = [await make_ready_user(client, db_session, bot_token, base_id + i) for i in range(16)]
    for u in users:
        result = await apply_to_tournament(db_session, u)
    return users, result.tournament_id


async def test_round_simulates_eight_matches_and_pays_match_rewards(client, db_session, bot_token):
    users, tournament_id = await _form_tournament(client, db_session, bot_token, 860000)
    config = await get_config(db_session)
    matches = await simulate_next_round(db_session)
    assert len(matches) == 8

    tournament = await db_session.get(PlayerTournament, tournament_id)
    assert tournament.rounds_simulated == 1

    standings = (await db_session.execute(select(PlayerTournamentStanding))).scalars().all()
    assert sum(s.points for s in standings) >= 8 * 2  # every match yields 2 (draw) or 3 (win) points
    txs = (await db_session.execute(
        select(CoinTransaction).where(CoinTransaction.type == TransactionType.player_tournament_match_reward)
    )).scalars().all()
    assert len(txs) == 16
    allowed = {config.ptour_match_reward_win, config.ptour_match_reward_draw, config.ptour_match_reward_loss}
    assert {t.amount for t in txs} <= allowed


async def test_same_slot_key_is_idempotent(client, db_session, bot_token):
    _users, tournament_id = await _form_tournament(client, db_session, bot_token, 861000)
    first = await simulate_next_round(db_session, slot_key="2026-09-25T10:00")
    second = await simulate_next_round(db_session, slot_key="2026-09-25T10:00")
    assert len(first) == 8 and second == []
    tournament = await db_session.get(PlayerTournament, tournament_id)
    assert tournament.rounds_simulated == 1


async def test_full_season_concludes_with_places_rewards_and_rating(client, db_session, bot_token):
    users, tournament_id = await _form_tournament(client, db_session, bot_token, 862000)
    config = await get_config(db_session)
    for _ in range(30):
        await simulate_next_round(db_session)

    tournament = await db_session.get(PlayerTournament, tournament_id)
    await db_session.refresh(tournament)
    assert tournament.status == TournamentStatus.completed and tournament.rounds_simulated == 30
    assert (await db_session.execute(select(func.count(PlayerTournamentMatch.id)))).scalar_one() == 240

    results = (await db_session.execute(
        select(PlayerTournamentResult).order_by(PlayerTournamentResult.final_rank)
    )).scalars().all()
    assert [r.final_rank for r in results] == list(range(1, 17))
    for r in results:
        assert r.rating_delta == config.ptour_rating_by_place[r.final_rank - 1]
        assert r.coins_awarded == config.ptour_place_rewards[r.final_rank - 1]
        user = await db_session.get(User, r.user_id)
        await db_session.refresh(user)
        assert user.tournament_rating == r.rating_delta
    assert sum(r.rating_delta for r in results) == 0

    place_txs = (await db_session.execute(
        select(CoinTransaction).where(CoinTransaction.type == TransactionType.player_tournament_place_reward)
    )).scalars().all()
    assert len(place_txs) == sum(1 for r in results if r.coins_awarded > 0)

    # Finished tournaments are not simulated again.
    assert await simulate_next_round(db_session) == []


async def test_player_without_full_squad_forfeits(client, db_session, bot_token):
    users, _tournament_id = await _form_tournament(client, db_session, bot_token, 863000)
    victim = users[0]
    victim_id = victim.id
    from app.models.personal_squad import PersonalSquad
    squad_ids = (await db_session.execute(select(PersonalSquad.id).where(PersonalSquad.user_id == victim_id))).scalars().all()
    rows = (await db_session.execute(select(PersonalSquadCard).where(PersonalSquadCard.squad_id.in_(squad_ids)))).scalars().all()
    for row in rows:
        await db_session.delete(row)
    await db_session.commit()

    await simulate_next_round(db_session)
    match = (await db_session.execute(
        select(PlayerTournamentMatch).where(
            (PlayerTournamentMatch.user_a_id == victim_id) | (PlayerTournamentMatch.user_b_id == victim_id)
        )
    )).scalar_one()
    victim_score, other_score = (match.score_a, match.score_b) if match.user_a_id == victim_id else (match.score_b, match.score_a)
    assert (victim_score, other_score) == (0, 3)
    assert match.event_log == []


def test_engine_card_carries_diamond_bonus_and_profile_attributes():
    from types import SimpleNamespace

    from app.models.enums import Position, Rarity
    from app.services.club_formation_service import get_formation_slots
    from app.services.club_tactical_matchup_service import build_side
    from app.services.player_tournament_simulation_service import _engine_card

    slot = get_formation_slots("4-3-3")[0]
    player = SimpleNamespace(
        display_name="X", position=Position.GK, rating=90, rarity=Rarity.diamond, club="C", country="K",
        attack_rating=None, defense_rating=None,
    )
    card = SimpleNamespace(id=1, player_id=2, player=player, diamond_rating_bonus=5)
    adapted = _engine_card(card)
    assert adapted.player.rating == 95
    assert (adapted.player.rarity, adapted.player.club, adapted.player.country) == (Rarity.diamond, "C", "K")
    assert build_side([(adapted, slot)], "balanced", "possession") is not None
