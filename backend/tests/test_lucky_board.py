"""«Табло удачи» — the table and its odds, reels, free → paid spins, limits,
account-bound paid prizes, shards → tokens, idempotency, Stars delivery."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.models.card_skill import UserSkillToken
from app.models.enums import TransactionType
from app.models.game_config import LUCKY_BOARD_DEFAULT_OUTCOMES
from app.models.lucky_board import LuckyBoardSpin
from app.models.monetization import Cosmetic, UserCosmetic
from app.models.transaction import CoinTransaction
from app.services import lucky_board_service as svc
from app.services import stars_payment_service
from app.services.game_config_service import get_config
from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers

settings = get_settings()
INTERNAL_HEADERS = {"X-Internal-Secret": settings.internal_api_secret}


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id), telegram_headers(telegram_id, bot_token)


async def _set_config(db_session, **values):
    config = await get_config(db_session)
    for key, value in values.items():
        setattr(config, key, value)
    await db_session.commit()


def _force(monkeypatch, code):
    """Every roll lands on `code` (the table row itself, as _roll returns)."""
    monkeypatch.setattr(svc, "_roll", lambda table, side: next(r for r in table if r["code"] == code))


async def _tokens(db_session, user_id) -> int:
    return int((await db_session.execute(
        select(func.coalesce(func.sum(UserSkillToken.quantity), 0)).where(UserSkillToken.user_id == user_id)
    )).scalar_one())


async def _spin(client, headers, key=None):
    h = dict(headers)
    if key:
        h["Idempotency-Key"] = key
    return await client.post("/api/v1/lucky-board/spin", headers=h)


# --- Table, odds, reels ----------------------------------------------------------


def test_default_table_odds_are_the_agreed_ones():
    table = svc.validate_outcomes(LUCKY_BOARD_DEFAULT_OUTCOMES)
    free, paid = svc.odds(table, "free"), svc.odds(table, "paid")
    assert free == pytest.approx({"cup": .01, "ball": .03, "glove": .08, "boot": .08, "pair": .30, "miss": .50})
    assert paid == pytest.approx({"cup": .01, "ball": .03, "glove": .08, "boot": .03, "pair": .35, "miss": .50})
    # Paid spins never pay coins.
    assert all(r["paid"]["coins"] == 0 for r in table)


def test_expected_value_matches_the_plan():
    class C:
        lucky_board_outcomes = LUCKY_BOARD_DEFAULT_OUTCOMES
        lucky_board_shards_per_token = 5

    ev = svc.expected_value(C())
    # paid: 0.17 tokens direct + (0.35*2 + 0.5*1 + 0.03*3 fallback) / 5 shards
    assert ev["paid"]["tokens"] == pytest.approx(0.17 + 1.29 / 5, abs=1e-3)
    assert ev["paid"]["coins"] == 0
    assert ev["free"]["coins"] == pytest.approx(10 + 24 + 12 + 12.5)


@pytest.mark.parametrize("bad, message", [
    ([{**r, "paid": {**r["paid"], "coins": 10}} if r["code"] == "miss" else r for r in LUCKY_BOARD_DEFAULT_OUTCOMES], "монеты"),
    (LUCKY_BOARD_DEFAULT_OUTCOMES[:-1], "не хватает"),
    ([{**r, "free_weight": -1} if r["code"] == "cup" else r for r in LUCKY_BOARD_DEFAULT_OUTCOMES], "отрицательным"),
    ([{**r, "paid_weight": 0} for r in LUCKY_BOARD_DEFAULT_OUTCOMES], "сумма весов"),
    ([{**r, "free": {**r["free"], "cosmetic": True}} if r["code"] == "boot" else r for r in LUCKY_BOARD_DEFAULT_OUTCOMES], "косметика"),
])
def test_validate_outcomes_refuses_bad_tables(bad, message):
    with pytest.raises(ValueError, match=message):
        svc.validate_outcomes(bad)


def test_reels_show_their_outcome():
    for _ in range(200):
        for code in svc.TRIPLES:
            assert svc.reels_for(code) == [code] * 3
        pair = svc.reels_for("pair")
        assert len(set(pair)) == 2 and all(s in svc.SYMBOLS for s in pair)
        miss = svc.reels_for("miss")
        assert len(set(miss)) == 3


def test_roll_follows_the_weights():
    table = svc.validate_outcomes(LUCKY_BOARD_DEFAULT_OUTCOMES)
    n = 40000
    hits = sum(1 for _ in range(n) if svc._roll(table, "paid")["code"] == "pair")
    assert abs(hits / n - 0.35) < 0.015


# --- Spins ---------------------------------------------------------------------------


async def test_status_shows_the_server_odds(client, db_session, bot_token):
    _, headers = await _register(client, db_session, 880001, bot_token)
    status = (await client.get("/api/v1/lucky-board/status", headers=headers)).json()
    assert status["free_remaining"] == 3 and status["stars_cost"] == 1 and status["paid_daily_limit"] == 20
    assert status["hourly_limit"] == 10 and status["shards_per_token"] == 5
    by_code = {o["code"]: o for o in status["outcomes"]}
    assert by_code["cup"]["free_pct"] == 1.0 and by_code["pair"]["paid_pct"] == 35.0
    assert sum(o["free_pct"] for o in status["outcomes"]) == pytest.approx(100)
    assert by_code["boot"]["symbol"] == "boot" and by_code["miss"]["symbol"] is None


async def test_free_spins_then_no_spins(client, db_session, bot_token, monkeypatch):
    _force(monkeypatch, "glove")
    user, headers = await _register(client, db_session, 880002, bot_token)
    start = user.balance
    for left in (2, 1, 0):
        resp = await _spin(client, headers)
        body = resp.json()
        assert resp.status_code == 200 and body["source"] == "free"
        assert body["reels"] == ["glove"] * 3 and body["prize"]["coins"] == 300
        assert body["status"]["free_remaining"] == left
    resp = await _spin(client, headers)
    assert resp.status_code == 409 and resp.json()["error"]["details"]["reason"] == "no_spins"
    await db_session.refresh(user)
    assert user.balance == start + 900
    tx = (await db_session.execute(select(func.count()).select_from(CoinTransaction).where(
        CoinTransaction.user_id == user.id, CoinTransaction.type == TransactionType.lucky_board_reward,
    ))).scalar_one()
    assert tx == 3


async def test_paid_spin_never_pays_coins_and_gives_tokens(client, db_session, bot_token, monkeypatch):
    await _set_config(db_session, lucky_board_free_per_day=0)
    user, headers = await _register(client, db_session, 880003, bot_token)
    user.lucky_board_paid_spins = 1
    await db_session.commit()
    start = user.balance
    _force(monkeypatch, "cup")
    body = (await _spin(client, headers)).json()
    assert body["source"] == "paid" and body["prize"]["coins"] == 0
    assert sum(t["quantity"] for t in body["prize"]["tokens"]) == 3
    await db_session.refresh(user)
    assert user.balance == start and user.lucky_board_paid_spins == 0
    assert await _tokens(db_session, user.id) == 3


async def test_shards_assemble_into_a_token(client, db_session, bot_token, monkeypatch):
    await _set_config(db_session, lucky_board_free_per_day=0)
    user, headers = await _register(client, db_session, 880004, bot_token)
    user.lucky_board_paid_spins = 3
    await db_session.commit()
    _force(monkeypatch, "pair")  # 2 shards each
    first = (await _spin(client, headers)).json()
    second = (await _spin(client, headers)).json()
    assert first["prize"]["shards"] == 2 and first["status"]["shards"] == 2
    assert second["status"]["shards"] == 4 and second["prize"]["crafted_tokens"] == []
    third = (await _spin(client, headers)).json()
    assert third["status"]["shards"] == 1
    assert sum(t["quantity"] for t in third["prize"]["crafted_tokens"]) == 1
    assert await _tokens(db_session, user.id) == 1


async def test_paid_boot_gives_pool_cosmetic_then_falls_back_to_shards(client, db_session, bot_token, monkeypatch):
    cosmetic = Cosmetic(kind="profile_frame", name="Табло", style_key="lucky_board", coins_price=0, stars_price=0,
                        is_exclusive=True, is_active=True, sort_order=0)
    db_session.add(cosmetic)
    await db_session.commit()
    await _set_config(db_session, lucky_board_free_per_day=0, lucky_board_cosmetic_ids=[cosmetic.id])
    user, headers = await _register(client, db_session, 880005, bot_token)
    user.lucky_board_paid_spins = 2
    await db_session.commit()
    _force(monkeypatch, "boot")

    first = (await _spin(client, headers)).json()
    assert first["prize"]["cosmetic"]["id"] == cosmetic.id and first["prize"]["shards"] == 0
    assert first["status"]["cosmetics_left"] == 0
    owned = (await db_session.execute(select(UserCosmetic).where(UserCosmetic.user_id == user.id))).scalars().all()
    assert [o.cosmetic_id for o in owned] == [cosmetic.id]

    second = (await _spin(client, headers)).json()
    assert second["prize"]["cosmetic"] is None and second["prize"]["shards"] == 3


async def test_idempotency_key_returns_the_same_spin(client, db_session, bot_token, monkeypatch):
    _force(monkeypatch, "miss")
    user, headers = await _register(client, db_session, 880006, bot_token)
    a = (await _spin(client, headers, key="spin-1")).json()
    b = (await _spin(client, headers, key="spin-1")).json()
    assert a["id"] == b["id"] and a["reels"] == b["reels"]
    assert b["status"]["free_remaining"] == 2
    count = (await db_session.execute(select(func.count()).select_from(LuckyBoardSpin).where(
        LuckyBoardSpin.user_id == user.id,
    ))).scalar_one()
    assert count == 1


async def test_hourly_limit(client, db_session, bot_token, monkeypatch):
    _force(monkeypatch, "miss")
    await _set_config(db_session, lucky_board_hourly_limit=2)
    user, headers = await _register(client, db_session, 880007, bot_token)
    assert (await _spin(client, headers)).status_code == 200
    assert (await _spin(client, headers)).status_code == 200
    resp = await _spin(client, headers)
    assert resp.status_code == 409 and resp.json()["error"]["details"]["reason"] == "hourly_limit"
    limits = await client.get("/api/v1/games/limits", headers=headers)
    assert limits.status_code == 200 and limits.json()["lucky_board"] == 0
    # An hour later the window opens again; the third free spin is still there.
    user = await get_user_by_telegram_id(db_session, 880007)
    user.lucky_board_hour_started_at = datetime.now(timezone.utc) - timedelta(hours=1, seconds=1)
    await db_session.commit()
    assert (await _spin(client, headers)).status_code == 200


async def test_blocked_rewards_show_outcome_but_pay_nothing(client, db_session, bot_token, monkeypatch):
    _force(monkeypatch, "glove")
    user, headers = await _register(client, db_session, 880008, bot_token)
    user.game_rewards_blocked = True
    await db_session.commit()
    start = user.balance
    body = (await _spin(client, headers)).json()
    assert body["outcome"] == "glove" and body["prize"]["blocked"] is True and body["prize"]["coins"] == 0
    await db_session.refresh(user)
    assert user.balance == start


async def test_disabled_blocks_spin_and_purchase(client, db_session, bot_token):
    await _set_config(db_session, lucky_board_enabled=False)
    _, headers = await _register(client, db_session, 880009, bot_token)
    assert (await _spin(client, headers)).status_code == 409
    assert (await client.post("/api/v1/lucky-board/stars-invoice", headers=headers)).status_code == 409


async def test_played_metric_counts_spins(client, db_session, bot_token, monkeypatch):
    from app.services.newbie_service import games_played, known_modes

    _force(monkeypatch, "miss")
    user, headers = await _register(client, db_session, 880010, bot_token)
    await _spin(client, headers)
    await _spin(client, headers)
    assert "lucky_board" in known_modes()
    assert await games_played(db_session, user, "lucky_board") == 2


# --- Stars -----------------------------------------------------------------------------


async def _fake_invoice_link(payload_token, title, description, stars_amount, **_):
    return f"https://t.me/invoice/{payload_token}"


def _deliver_json(token, telegram_id, charge_id, amount=1):
    return {
        "payload_token": token, "telegram_user_id": telegram_id,
        "telegram_payment_charge_id": charge_id, "total_amount": amount,
    }


async def test_stars_spin_purchase_is_idempotent_and_playable(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    await _set_config(db_session, lucky_board_free_per_day=0)
    user, headers = await _register(client, db_session, 880020, bot_token)

    invoice = (await client.post("/api/v1/lucky-board/stars-invoice", headers=headers)).json()
    assert invoice["stars_amount"] == 1
    token = invoice["payload_token"]
    pre = await client.post(
        "/api/v1/internal/stars-payments/pre-checkout", json={"payload_token": token, "total_amount": 1},
        headers=INTERNAL_HEADERS,
    )
    assert pre.json()["ok"] is True

    charge = "lb-charge-" + "a" * 40
    for _ in range(2):
        resp = await client.post("/api/v1/internal/stars-payments/deliver", json=_deliver_json(token, 880020, charge), headers=INTERNAL_HEADERS)
        assert resp.status_code == 200
    await db_session.refresh(user)
    assert user.lucky_board_paid_spins == 1 and user.lucky_board_paid_bought_today == 1

    _force(monkeypatch, "miss")
    body = (await _spin(client, headers)).json()
    assert body["source"] == "paid" and body["prize"]["shards"] == 1 and body["prize"]["coins"] == 0


async def test_paid_daily_limit_at_invoice_and_pre_checkout(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    await _set_config(db_session, lucky_board_paid_daily_limit=1)
    _, headers = await _register(client, db_session, 880021, bot_token)

    a = (await client.post("/api/v1/lucky-board/stars-invoice", headers=headers)).json()
    b = (await client.post("/api/v1/lucky-board/stars-invoice", headers=headers)).json()
    resp = await client.post("/api/v1/internal/stars-payments/deliver", json=_deliver_json(a["payload_token"], 880021, "lb-limit-1"), headers=INTERNAL_HEADERS)
    assert resp.status_code == 200
    pre_b = await client.post(
        "/api/v1/internal/stars-payments/pre-checkout", json={"payload_token": b["payload_token"], "total_amount": 1},
        headers=INTERNAL_HEADERS,
    )
    assert pre_b.json()["ok"] is False
    resp = await client.post("/api/v1/lucky-board/stars-invoice", headers=headers)
    assert resp.status_code == 409 and resp.json()["error"]["details"]["reason"] == "paid_limit"

