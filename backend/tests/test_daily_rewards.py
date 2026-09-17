from datetime import date, timedelta

from app.core.timeutil import local_today
from app.models.daily_reward import DailyReward, DailyRewardOption
from app.services.daily_reward_service import _cycle_start_date, _resolve_option
from tests.factories import create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

DAY1_DEFAULT_COINS = {40, 45, 50, 55, 60}


async def _admin_auth(client, bot_token):
    headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    session_resp = await client.post("/api/v1/auth/session", headers=headers)
    admin_token = session_resp.json()["admin_token"]
    return {"Authorization": f"Bearer {admin_token}"}


# --- resolution logic (pure, no DB) ---------------------------------------


def test_cycle_start_date_derivation():
    assert _cycle_start_date(date(2026, 3, 10), 1) == date(2026, 3, 10)
    assert _cycle_start_date(date(2026, 3, 10), 4) == date(2026, 3, 7)


def test_resolve_option_is_stable_within_a_cycle():
    candidates = [DailyRewardOption(day=1, option_index=i, coins=c) for i, c in enumerate([10, 20, 30, 40, 50], start=1)]
    cycle_start = date(2026, 1, 5)
    first = _resolve_option(42, cycle_start, 1, candidates)
    second = _resolve_option(42, cycle_start, 1, candidates)
    assert first.coins == second.coins


def test_resolve_option_varies_across_different_cycles():
    candidates = [DailyRewardOption(day=1, option_index=i, coins=c) for i, c in enumerate([10, 20, 30, 40, 50], start=1)]
    base = date(2026, 1, 5)
    results = {_resolve_option(42, base + timedelta(weeks=w), 1, candidates).coins for w in range(20)}
    # With 5 equally likely candidates across 20 independent cycles, seeing
    # only one distinct value would mean the "randomness" isn't varying at
    # all — a near-certain failure if _resolve_option regressed to always
    # picking the same candidate.
    assert len(results) > 1


# --- claim / calendar (existing behavior) ----------------------------------


async def test_claim_daily_reward(client, bot_token):
    headers = telegram_headers(710001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.post("/api/v1/daily-rewards/claim", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["streak_day"] == 1
    assert body["coins_awarded"] in DAY1_DEFAULT_COINS
    assert body["new_balance"] == 500 + body["coins_awarded"]

    profile = await client.get("/api/v1/profile/me", headers=headers)
    assert profile.json()["daily_login_streak"] == 1


async def test_claim_daily_reward_twice_same_day_fails(client, bot_token):
    headers = telegram_headers(710002, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    first = await client.post("/api/v1/daily-rewards/claim", headers=headers)
    second = await client.post("/api/v1/daily-rewards/claim", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


async def test_daily_reward_calendar_reflects_claim_state(client, bot_token):
    headers = telegram_headers(710003, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    before = await client.get("/api/v1/daily-rewards/calendar", headers=headers)
    assert before.json()["already_claimed_today"] is False

    await client.post("/api/v1/daily-rewards/claim", headers=headers)

    after = await client.get("/api/v1/daily-rewards/calendar", headers=headers)
    assert after.json()["already_claimed_today"] is True


async def test_calendar_and_claim_agree_on_todays_reward(client, bot_token):
    headers = telegram_headers(710004, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    calendar = await client.get("/api/v1/daily-rewards/calendar", headers=headers)
    today_entry = next(d for d in calendar.json()["days"] if d["is_today"])

    claim = await client.post("/api/v1/daily-rewards/claim", headers=headers)
    assert claim.json()["coins_awarded"] == today_entry["coins"]


async def test_reward_stable_across_repeated_calendar_calls(client, bot_token):
    headers = telegram_headers(710005, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    first = await client.get("/api/v1/daily-rewards/calendar", headers=headers)
    second = await client.get("/api/v1/daily-rewards/calendar", headers=headers)
    assert first.json()["days"] == second.json()["days"]


# --- streak day computation across real days (direct DB row setup) --------


async def test_streak_continues_across_consecutive_days(client, db_session, bot_token):
    headers = telegram_headers(710010, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 710010)

    yesterday = local_today() - timedelta(days=1)
    db_session.add(DailyReward(user_id=user.id, reward_date=yesterday, streak_day=3, coins_awarded=100))
    await db_session.commit()

    calendar = await client.get("/api/v1/daily-rewards/calendar", headers=headers)
    assert calendar.json()["current_streak"] == 4
    assert calendar.json()["already_claimed_today"] is False


async def test_streak_wraps_after_day_7(client, db_session, bot_token):
    headers = telegram_headers(710011, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 710011)

    yesterday = local_today() - timedelta(days=1)
    db_session.add(DailyReward(user_id=user.id, reward_date=yesterday, streak_day=7, coins_awarded=300))
    await db_session.commit()

    calendar = await client.get("/api/v1/daily-rewards/calendar", headers=headers)
    assert calendar.json()["current_streak"] == 1


async def test_streak_resets_after_missed_day(client, db_session, bot_token):
    headers = telegram_headers(710012, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 710012)

    two_days_ago = local_today() - timedelta(days=2)
    db_session.add(DailyReward(user_id=user.id, reward_date=two_days_ago, streak_day=4, coins_awarded=125))
    await db_session.commit()

    calendar = await client.get("/api/v1/daily-rewards/calendar", headers=headers)
    assert calendar.json()["current_streak"] == 1


async def test_day4_of_cycle_grants_free_pack(client, db_session, bot_token):
    await create_pack(db_session, "basic", price=100, card_count=1, probabilities={"common": 1.0})
    await create_player(db_session)

    headers = telegram_headers(710013, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 710013)

    yesterday = local_today() - timedelta(days=1)
    db_session.add(DailyReward(user_id=user.id, reward_date=yesterday, streak_day=3, coins_awarded=100))
    await db_session.commit()

    claim = await client.post("/api/v1/daily-rewards/claim", headers=headers)
    body = claim.json()
    assert body["streak_day"] == 4
    assert body["granted_pack_name"] is not None


async def test_day6_of_cycle_grants_random_card(client, db_session, bot_token):
    await create_player(db_session)

    headers = telegram_headers(710014, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 710014)

    yesterday = local_today() - timedelta(days=1)
    db_session.add(DailyReward(user_id=user.id, reward_date=yesterday, streak_day=5, coins_awarded=150))
    await db_session.commit()

    claim = await client.post("/api/v1/daily-rewards/claim", headers=headers)
    body = claim.json()
    assert body["streak_day"] == 6
    assert body["granted_card"] is not None


# --- admin: candidate pool management --------------------------------------


async def test_admin_lists_default_daily_reward_options(client, bot_token):
    auth = await _admin_auth(client, bot_token)
    resp = await client.get("/api/v1/admin/daily-reward-options", headers=auth)
    assert resp.status_code == 200
    options = resp.json()
    assert len(options) == 35
    assert {o["day"] for o in options} == set(range(1, 8))


def _simple_options(overrides: dict | None = None, skip_day: int | None = None) -> dict:
    """A minimal, self-contained 7-day x 1-option payload (coins only, no
    pack/card grants) — deliberately not derived from the server's own
    defaults, so these tests don't depend on (or accidentally validate
    against) the "basic"/"premium" pack rows the real defaults reference,
    which don't exist in a bare test DB."""
    overrides = overrides or {}
    options = [{"day": d, "option_index": 1, "coins": 50 + d, "free_pack_slug": None, "grants_random_card": False} for d in range(1, 8)]
    if skip_day is not None:
        options = [o for o in options if o["day"] != skip_day]
    for key, value in overrides.items():
        day, field = key
        next(o for o in options if o["day"] == day)[field] = value
    return {"options": options}


async def test_admin_updates_daily_reward_options(client, bot_token):
    auth = await _admin_auth(client, bot_token)
    resp = await client.put("/api/v1/admin/daily-reward-options", headers=auth, json=_simple_options())
    assert resp.status_code == 200
    assert len(resp.json()) == 7

    headers = telegram_headers(710020, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    calendar = await client.get("/api/v1/daily-rewards/calendar", headers=headers)
    day1 = next(d for d in calendar.json()["days"] if d["day"] == 1)
    assert day1["coins"] == 51


async def test_admin_update_rejects_missing_day(client, bot_token):
    auth = await _admin_auth(client, bot_token)
    resp = await client.put("/api/v1/admin/daily-reward-options", headers=auth, json=_simple_options(skip_day=7))
    assert resp.status_code == 409


async def test_admin_update_rejects_unknown_pack_slug(client, bot_token):
    auth = await _admin_auth(client, bot_token)
    payload = _simple_options(overrides={(1, "free_pack_slug"): "no-such-pack"})
    resp = await client.put("/api/v1/admin/daily-reward-options", headers=auth, json=payload)
    assert resp.status_code == 409


async def test_admin_update_rejects_negative_coins(client, bot_token):
    auth = await _admin_auth(client, bot_token)
    payload = _simple_options(overrides={(1, "coins"): -5})
    resp = await client.put("/api/v1/admin/daily-reward-options", headers=auth, json=payload)
    assert resp.status_code == 409
