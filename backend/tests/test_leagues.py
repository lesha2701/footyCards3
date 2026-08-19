import pytest

import app.core.rate_limit as rate_limit_module
from app.models.league import LeagueTier, UserLeagueRewardClaim
from app.schemas.league import LeagueTierOut, LeagueTierPublicOut


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    # The in-memory rate limiter (app/core/rate_limit.py) is process-global
    # and keyed by numeric user id, but every test gets a fresh DB whose
    # autoincrement ids restart at 1 — without this, this file's tests could
    # both contaminate and be contaminated by other test files' hits on the
    # same low-numbered bucket (e.g. "play_match:1"). Same fix already
    # applied to test_packs.py and test_lineups_matches.py in this repo.
    rate_limit_module._hits.clear()
    yield


async def test_league_tier_and_claim_round_trip(db_session):
    tier = LeagueTier(name="Дворовая лига", min_rating=0, icon="🥉", reward_coins=100, sort_order=0)
    db_session.add(tier)
    await db_session.commit()
    await db_session.refresh(tier)

    assert LeagueTierOut.model_validate(tier).reward_pack_id is None

    claim = UserLeagueRewardClaim(user_id=1, league_tier_id=tier.id, reward_coins=100)
    db_session.add(claim)
    await db_session.commit()
    await db_session.refresh(claim)
    assert claim.tier.name == "Дворовая лига"
