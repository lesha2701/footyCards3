import pytest
from sqlalchemy import select

from app.models.enums import CardSource, TransactionType, WheelPrizeType, WheelSpinSource
from app.models.wheel import WheelPrize, WheelSpin
from tests.factories import create_wheel_prize


async def test_wheel_prize_model_roundtrip(db_session):
    prize = await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=10, coins_amount=50)
    assert prize.id is not None
    assert prize.weight == 10
    assert prize.coins_amount == 50
    assert prize.is_active is True


async def test_wheel_spin_model_roundtrip(db_session):
    from tests.factories import create_player, create_pack, get_user_by_telegram_id
    from tests.utils import telegram_headers

    prize = await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, coins_amount=25)
    spin = WheelSpin(user_id=1, prize_id=prize.id, source=WheelSpinSource.free, coins_amount=25)
    db_session.add(spin)
    await db_session.commit()
    await db_session.refresh(spin)
    assert spin.id is not None
    assert spin.source == WheelSpinSource.free


def test_new_enum_members_exist():
    assert CardSource.wheel == "wheel"
    assert TransactionType.wheel_spin_cost == "wheel_spin_cost"
    assert TransactionType.wheel_spin_reward == "wheel_spin_reward"
    assert WheelPrizeType.card_rarity == "card_rarity"


from app.core.exceptions import ConflictError, InsufficientBalanceError
from app.models.badge import UserBadge
from app.models.enums import Rarity, WheelPrizeType
from app.models.game_config import GameConfig
from app.services import wheel_service
from tests.factories import create_badge, create_pack, create_player, create_wheel_prize, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def test_roll_prize_picks_only_active_weighted(db_session):
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=100, coins_amount=10)
    inactive = await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=100, coins_amount=999, is_active=False)

    for _ in range(20):
        prize = await wheel_service._roll_prize(db_session)
        assert prize.id != inactive.id


async def test_roll_prize_raises_when_no_active_prizes(db_session):
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=10, is_active=False)
    with pytest.raises(ConflictError):
        await wheel_service._roll_prize(db_session)


async def test_grant_coins_prize_credits_balance(client, db_session, bot_token):
    user = await _register(client, db_session, 860001, bot_token)
    prize = await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=77)

    result = await wheel_service._grant_prize(db_session, user, prize, wheel_service.WheelSpinSource.free)
    await db_session.commit()
    await db_session.refresh(user)

    assert result.prize.id == prize.id
    assert user.balance == 500 + 77
    assert result.new_balance == 500 + 77


async def test_grant_pack_prize_opens_cards(client, db_session, bot_token):
    user = await _register(client, db_session, 860002, bot_token)
    await create_player(db_session, rarity=Rarity.common)
    pack = await create_pack(db_session, "wheel-pack", price=0, card_count=2, probabilities={Rarity.common: 1.0})
    prize = await create_wheel_prize(db_session, prize_type=WheelPrizeType.pack, weight=1, pack_id=pack.id)

    result = await wheel_service._grant_prize(db_session, user, prize, wheel_service.WheelSpinSource.free)
    await db_session.commit()

    assert result.pack_result is not None
    assert len(result.pack_result.cards) == 2


async def test_grant_card_rarity_prize_grants_one_card_of_that_rarity(client, db_session, bot_token):
    user = await _register(client, db_session, 860003, bot_token)
    await create_player(db_session, rarity=Rarity.legendary)
    prize = await create_wheel_prize(db_session, prize_type=WheelPrizeType.card_rarity, weight=1, card_rarity=Rarity.legendary)

    result = await wheel_service._grant_prize(db_session, user, prize, wheel_service.WheelSpinSource.free)
    await db_session.commit()

    assert result.card_result is not None
    assert result.card_result.card.player.rarity == Rarity.legendary


async def test_grant_badge_prize_grants_new_badge(client, db_session, bot_token):
    user = await _register(client, db_session, 860004, bot_token)
    badge = await create_badge(db_session, name="Колесо", icon="🎡")
    prize = await create_wheel_prize(db_session, prize_type=WheelPrizeType.badge, weight=1, badge_id=badge.id)

    result = await wheel_service._grant_prize(db_session, user, prize, wheel_service.WheelSpinSource.free)
    await db_session.commit()

    assert result.badge_result is not None
    assert result.badge_result.id == badge.id
    owned = (
        await db_session.execute(select(UserBadge).where(UserBadge.user_id == user.id, UserBadge.badge_id == badge.id))
    ).scalar_one_or_none()
    assert owned is not None


async def test_grant_duplicate_badge_prize_credits_coins_instead(client, db_session, bot_token):
    user = await _register(client, db_session, 860005, bot_token)
    badge = await create_badge(db_session, name="Колесо", icon="🎡")
    db_session.add(UserBadge(user_id=user.id, badge_id=badge.id))
    await db_session.commit()
    prize = await create_wheel_prize(db_session, prize_type=WheelPrizeType.badge, weight=1, badge_id=badge.id)

    result = await wheel_service._grant_prize(db_session, user, prize, wheel_service.WheelSpinSource.free)
    await db_session.commit()
    await db_session.refresh(user)

    assert result.badge_result is None
    assert result.duplicate_badge_coins == 200
    assert user.balance == 500 + 200


async def test_spin_free_consumes_daily_allowance_then_blocks(client, db_session, bot_token):
    user = await _register(client, db_session, 860006, bot_token)
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=5)

    await wheel_service.spin_free(db_session, user)
    await db_session.refresh(user)
    assert user.wheel_free_spins_used_today == 1

    await wheel_service.spin_free(db_session, user)
    await db_session.refresh(user)
    assert user.wheel_free_spins_used_today == 2

    with pytest.raises(ConflictError):
        await wheel_service.spin_free(db_session, user)


async def test_spin_free_resets_on_a_new_day(client, db_session, bot_token):
    from datetime import datetime, timedelta, timezone

    user = await _register(client, db_session, 860007, bot_token)
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=5)
    user.wheel_free_spins_used_today = 2
    user.wheel_spins_reset_at = datetime.now(timezone.utc) - timedelta(days=2)
    db_session.add(user)
    await db_session.commit()

    await wheel_service.spin_free(db_session, user)
    await db_session.refresh(user)
    assert user.wheel_free_spins_used_today == 1


async def test_spin_paid_coins_debits_configured_cost(client, db_session, bot_token):
    user = await _register(client, db_session, 860008, bot_token)
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=1)
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
    config.wheel_spin_cost_coins = 300
    db_session.add(config)
    await db_session.commit()

    result = await wheel_service.spin_paid_coins(db_session, user)
    await db_session.refresh(user)
    assert user.balance == 500 - 300 + 1
    assert result.new_balance == user.balance


async def test_spin_paid_coins_rejects_insufficient_balance(client, db_session, bot_token):
    user = await _register(client, db_session, 860009, bot_token)
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=1)
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
    config.wheel_spin_cost_coins = 999999
    db_session.add(config)
    await db_session.commit()

    with pytest.raises(InsufficientBalanceError):
        await wheel_service.spin_paid_coins(db_session, user)


async def test_get_status_reports_remaining_free_spins_and_active_prizes(client, db_session, bot_token):
    user = await _register(client, db_session, 860010, bot_token)
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=1)
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=2, is_active=False)

    status = await wheel_service.get_status(db_session, user)
    assert status.free_spins_remaining == 2
    assert status.free_spins_total == 2
    assert len(status.prizes) == 1


async def test_status_and_free_spin_endpoints(client, db_session, bot_token):
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=5)
    await _register(client, db_session, 860020, bot_token)
    headers = telegram_headers(860020, bot_token)

    status_resp = await client.get("/api/v1/wheel/status", headers=headers)
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["free_spins_remaining"] == 2
    assert len(body["prizes"]) == 1

    spin_resp = await client.post("/api/v1/wheel/spin/free", headers=headers)
    assert spin_resp.status_code == 200
    assert spin_resp.json()["prize"]["prize_type"] == "coins"

    status_resp2 = await client.get("/api/v1/wheel/status", headers=headers)
    assert status_resp2.json()["free_spins_remaining"] == 1


async def test_free_spin_exhausted_returns_409(client, db_session, bot_token):
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=5)
    await _register(client, db_session, 860021, bot_token)
    headers = telegram_headers(860021, bot_token)

    for _ in range(2):
        assert (await client.post("/api/v1/wheel/spin/free", headers=headers)).status_code == 200

    resp = await client.post("/api/v1/wheel/spin/free", headers=headers)
    assert resp.status_code == 409


async def test_paid_coin_spin_endpoint(client, db_session, bot_token):
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=1)
    await _register(client, db_session, 860022, bot_token)
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
    config.wheel_spin_cost_coins = 300
    db_session.add(config)
    await db_session.commit()
    headers = telegram_headers(860022, bot_token)

    resp = await client.post("/api/v1/wheel/spin/coins", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["new_balance"] == 500 - 300 + 1


from app.config import get_settings

settings = get_settings()
INTERNAL_HEADERS = {"X-Internal-Secret": settings.internal_api_secret}


async def _fake_invoice_link(payload_token, title, description, stars_amount):
    return f"https://t.me/invoice/{payload_token}"


async def test_stars_spin_full_flow(client, db_session, bot_token, monkeypatch):
    # wheel_service.create_spin_invoice calls a name it imported from
    # stars_payment_service at module load time
    # (`from app.services.stars_payment_service import _request_telegram_invoice_link`),
    # which is its own separate binding — patching
    # stars_payment_service._request_telegram_invoice_link afterwards would
    # not affect wheel_service's copy, so the mock must target
    # wheel_service's own name.
    monkeypatch.setattr(wheel_service, "_request_telegram_invoice_link", _fake_invoice_link)
    await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=7)
    await _register(client, db_session, 860030, bot_token)
    headers = telegram_headers(860030, bot_token)

    invoice_resp = await client.post("/api/v1/wheel/spin/stars-invoice", headers=headers)
    assert invoice_resp.status_code == 200
    invoice = invoice_resp.json()
    assert invoice["stars_amount"] == 10  # default GameConfig.wheel_spin_cost_stars

    status_resp = await client.get(f"/api/v1/wheel/stars-invoices/{invoice['payload_token']}", headers=headers)
    assert status_resp.json()["status"] == "pending"

    pre_checkout = await client.post(
        "/api/v1/internal/stars-payments/pre-checkout",
        json={"payload_token": invoice["payload_token"], "total_amount": 10},
        headers=INTERNAL_HEADERS,
    )
    assert pre_checkout.json()["ok"] is True

    deliver = await client.post(
        "/api/v1/internal/stars-payments/deliver",
        json={
            "payload_token": invoice["payload_token"],
            "telegram_user_id": 860030,
            "telegram_payment_charge_id": "wheel-charge-" + "f" * 120,
            "total_amount": 10,
        },
        headers=INTERNAL_HEADERS,
    )
    assert deliver.status_code == 200
    body = deliver.json()
    assert body["status"] == "completed"
    assert body["wheel_result"]["new_balance"] == 500 + 7

    status_resp2 = await client.get(f"/api/v1/wheel/stars-invoices/{invoice['payload_token']}", headers=headers)
    assert status_resp2.json()["status"] == "completed"
    assert status_resp2.json()["wheel_result"]["new_balance"] == 500 + 7

    # Redelivering the same charge must not spin (and thus not credit) twice.
    second = await client.post(
        "/api/v1/internal/stars-payments/deliver",
        json={
            "payload_token": invoice["payload_token"],
            "telegram_user_id": 860030,
            "telegram_payment_charge_id": "wheel-charge-" + "f" * 120,
            "total_amount": 10,
        },
        headers=INTERNAL_HEADERS,
    )
    assert second.json()["wheel_result"]["new_balance"] == 500 + 7
