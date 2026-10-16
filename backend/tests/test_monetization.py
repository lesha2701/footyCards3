"""Cosmetics, «Клубный абонемент», «Сезонный пропуск» and the starter offer —
all sold through the standard Stars flow (shop_product_service)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.config import get_settings
from app.models.badge import UserBadge
from app.models.enums import Rarity, TransactionType
from app.models.monetization import ClubSubscription, Cosmetic, SeasonProgress, StarterOfferPurchase, UserCosmetic
from app.models.pack import StarsInvoice
from app.services import (
    admin_analytics_service,
    club_pass_service,
    season_pass_service,
    stars_payment_service,
    stars_receipt_service,
)
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, lock_user_for_update
from tests.factories import create_badge, create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

INTERNAL = {"X-Internal-Secret": get_settings().internal_api_secret}


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    rate_limit_module._hits.clear()
    calls = []

    async def fake_link(payload_token, title, description, stars_amount, subscription_period=None):
        calls.append({"title": title, "description": description, "stars": stars_amount, "period": subscription_period})
        return f"https://t.me/invoice/{payload_token}"

    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", fake_link)
    yield calls


@pytest.fixture(autouse=True)
async def _launched(db_session):
    """Everything here ships switched off; these tests run with it launched.
    The monthly club-pass bonus card is off too unless a test sets it (no
    players exist in most tests)."""
    config = await get_config(db_session)
    config.club_pass_enabled = config.season_pass_enabled = config.starter_offer_enabled = True
    config.artifacts_enabled = True
    config.club_pass_bonus_card_rarity = None
    await db_session.commit()
    yield


async def _register(client, db_session, telegram_id, bot_token):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    return headers, await get_user_by_telegram_id(db_session, telegram_id)


async def _admin(client, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(999000001, bot_token))
    return {"Authorization": f"Bearer {resp.json()['admin_token']}"}


async def _pay(client, token, telegram_id, stars, charge, **extra):
    pre = await client.post("/api/v1/internal/stars-payments/pre-checkout", headers=INTERNAL,
                            json={"payload_token": token, "total_amount": stars})
    resp = await client.post("/api/v1/internal/stars-payments/deliver", headers=INTERNAL, json={
        "payload_token": token, "telegram_user_id": telegram_id, "telegram_payment_charge_id": charge,
        "total_amount": stars, **extra,
    })
    return pre.json(), resp


async def _cosmetic(db_session, **kw) -> Cosmetic:
    data = {"kind": "profile_frame", "name": "Рамка", "style_key": "gold", "coins_price": 100, "stars_price": 5, **kw}
    c = Cosmetic(**data)
    db_session.add(c)
    await db_session.commit()
    return c


# --- cosmetics ------------------------------------------------------------------------


async def test_buy_cosmetic_for_coins_and_equip(client, db_session, bot_token):
    frame = await _cosmetic(db_session)
    headers, user = await _register(client, db_session, 720001, bot_token)

    resp = await client.post(f"/api/v1/cosmetics/{frame.id}/buy", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["balance"] == 400
    item = next(i for i in body["items"] if i["id"] == frame.id)
    assert item["owned"] and item["equipped"]  # empty slot → equipped on purchase
    assert body["equipped"]["frame"] == "gold"

    again = await client.post(f"/api/v1/cosmetics/{frame.id}/buy", headers=headers)
    assert again.status_code == 409

    off = await client.post("/api/v1/cosmetics/equip", headers=headers, json={"kind": "profile_frame", "cosmetic_id": None})
    assert off.json()["equipped"]["frame"] is None

    profile = (await client.get("/api/v1/profile/me", headers=headers)).json()
    assert profile["cosmetics"]["frame"] is None


async def test_cannot_equip_unowned_or_wrong_kind(client, db_session, bot_token):
    frame = await _cosmetic(db_session)
    headers, _ = await _register(client, db_session, 720002, bot_token)
    resp = await client.post("/api/v1/cosmetics/equip", headers=headers, json={"kind": "profile_frame", "cosmetic_id": frame.id})
    assert resp.status_code == 409
    resp = await client.post("/api/v1/cosmetics/equip", headers=headers, json={"kind": "card_skin", "cosmetic_id": frame.id})
    assert resp.status_code == 404


async def test_exclusive_cosmetics_are_hidden_and_not_sold(client, db_session, bot_token):
    exclusive = await _cosmetic(db_session, is_exclusive=True, style_key="club_pass")
    headers, _ = await _register(client, db_session, 720003, bot_token)
    catalog = (await client.get("/api/v1/cosmetics", headers=headers)).json()
    assert all(i["id"] != exclusive.id for i in catalog["items"])
    assert (await client.post(f"/api/v1/cosmetics/{exclusive.id}/buy", headers=headers)).status_code == 409
    assert (await client.post(f"/api/v1/cosmetics/{exclusive.id}/stars-invoice", headers=headers)).status_code == 409


async def test_buy_cosmetic_for_stars(client, db_session, bot_token, _setup):
    frame = await _cosmetic(db_session, coins_price=0, stars_price=25)
    headers, user = await _register(client, db_session, 720004, bot_token)
    assert (await client.post(f"/api/v1/cosmetics/{frame.id}/buy", headers=headers)).status_code == 409

    inv = (await client.post(f"/api/v1/cosmetics/{frame.id}/stars-invoice", headers=headers)).json()
    assert inv["stars_amount"] == 25
    assert "на игру не влияет" in _setup[-1]["description"]
    pre, resp = await _pay(client, inv["payload_token"], 720004, 25, "cos-1")
    assert pre["ok"] and resp.status_code == 200
    owned = (await db_session.execute(select(UserCosmetic).where(UserCosmetic.user_id == user.id))).scalars().all()
    assert [o.cosmetic_id for o in owned] == [frame.id]


# --- «Клубный абонемент» --------------------------------------------------------------


async def _club_pass_config(db_session):
    frame = await _cosmetic(db_session, is_exclusive=True, style_key="club_pass", coins_price=0, stars_price=0)
    badge = await create_badge(db_session, name="Абонемент")
    config = await get_config(db_session)
    config.club_pass_frame_cosmetic_id = frame.id
    config.club_pass_badge_id = badge.id
    await db_session.commit()
    return frame, badge


async def test_club_pass_purchase_is_a_subscription(client, db_session, bot_token, _setup):
    frame, badge = await _club_pass_config(db_session)
    headers, user = await _register(client, db_session, 720010, bot_token)

    status = (await client.get("/api/v1/club-pass", headers=headers)).json()
    assert status["is_active"] is False and status["stars_price"] == 199
    assert status["perks"]["frame"]["id"] == frame.id and status["perks"]["badge"]["id"] == badge.id

    inv = (await client.post("/api/v1/club-pass/stars-invoice", headers=headers)).json()
    assert _setup[-1]["period"] == 2592000
    expiry = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
    pre, resp = await _pay(client, inv["payload_token"], 720010, 199, "sub-1", subscription_expiration_date=expiry)
    assert pre["ok"] and resp.status_code == 200
    assert resp.json()["shop_result"]["kind"] == "club_pass"

    status = (await client.get("/api/v1/club-pass", headers=headers)).json()
    assert status["is_active"] and status["auto_renew"]
    assert abs(datetime.fromisoformat(status["expires_at"]).timestamp() - expiry) < 2
    profile = (await client.get("/api/v1/profile/me", headers=headers)).json()
    assert profile["club_pass_active"] and profile["cosmetics"]["frame"] == "club_pass"
    assert profile["active_badge"]["id"] == badge.id

    # Already active → no second purchase.
    assert (await client.post("/api/v1/club-pass/stars-invoice", headers=headers)).status_code == 409


async def test_club_pass_renewal_extends_and_counts_as_revenue(client, db_session, bot_token):
    headers, user = await _register(client, db_session, 720011, bot_token)
    inv = (await client.post("/api/v1/club-pass/stars-invoice", headers=headers)).json()
    await _pay(client, inv["payload_token"], 720011, 199, "sub-first")
    sub = (await db_session.execute(select(ClubSubscription).where(ClubSubscription.user_id == user.id))).scalar_one()
    first_end = sub.expires_at

    # Telegram renews: same payload, new charge id, no pre-checkout.
    for _ in range(2):  # a redelivered renewal must not extend twice
        resp = await client.post("/api/v1/internal/stars-payments/deliver", headers=INTERNAL, json={
            "payload_token": inv["payload_token"], "telegram_user_id": 720011,
            "telegram_payment_charge_id": "sub-renew-1", "total_amount": 199, "is_recurring": True,
        })
        assert resp.status_code == 200
    await db_session.refresh(sub)
    assert (sub.expires_at - first_end) == timedelta(days=30)
    assert sub.payments == 2 and sub.telegram_charge_id == "sub-first"

    invoices = (await db_session.execute(
        select(StarsInvoice).where(StarsInvoice.user_id == user.id).order_by(StarsInvoice.id)
    )).scalars().all()
    assert [i.shop_product for i in invoices] == ["club_pass", "club_pass_renewal"]
    report = await admin_analytics_service.analytics_report(db_session, 7)
    products = {p["product"]: p for p in report["monetization"]["by_product"]}
    assert products["Клубный абонемент"]["stars"] == 199
    assert products["Клубный абонемент: продление"]["stars"] == 199


async def test_club_pass_daily_bonus_once_a_day(client, db_session, bot_token):
    await create_player(db_session)
    pack = await create_pack(db_session, "basic-cp", price=0, card_count=1, probabilities={"common": 1.0})
    config = await get_config(db_session)
    config.club_pass_daily_pack_id = pack.id
    await db_session.commit()
    headers, user = await _register(client, db_session, 720012, bot_token)
    assert (await client.post("/api/v1/club-pass/daily", headers=headers)).status_code == 409  # not subscribed

    inv = (await client.post("/api/v1/club-pass/stars-invoice", headers=headers)).json()
    await _pay(client, inv["payload_token"], 720012, 199, "sub-daily")
    first = await client.post("/api/v1/club-pass/daily", headers=headers)
    assert first.status_code == 200
    assert first.json()["coins"] == 300 and first.json()["pack_name"] == pack.name
    assert len(first.json()["cards"]) == 1
    assert (await client.post("/api/v1/club-pass/daily", headers=headers)).status_code == 409


async def test_club_pass_perks_stop_at_expiry(client, db_session, bot_token):
    frame, badge = await _club_pass_config(db_session)
    headers, user = await _register(client, db_session, 720013, bot_token)
    inv = (await client.post("/api/v1/club-pass/stars-invoice", headers=headers)).json()
    await _pay(client, inv["payload_token"], 720013, 199, "sub-exp")
    config = await get_config(db_session)
    assert await club_pass_service.extra_rewarded_attempts(db_session, user.id, config) == 2

    sub = (await db_session.execute(select(ClubSubscription).where(ClubSubscription.user_id == user.id))).scalar_one()
    sub.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()

    assert await club_pass_service.extra_rewarded_attempts(db_session, user.id, config) == 0
    status = (await client.get("/api/v1/club-pass", headers=headers)).json()
    assert status["is_active"] is False
    profile = (await client.get("/api/v1/profile/me", headers=headers)).json()
    assert profile["cosmetics"]["frame"] is None and profile["active_badge"] is None
    user_id = user.id
    db_session.expire_all()
    assert (await db_session.execute(select(UserBadge).where(UserBadge.user_id == user_id))).first() is None
    assert (await db_session.execute(select(UserCosmetic).where(UserCosmetic.user_id == user_id))).first() is None
    assert (await client.post("/api/v1/club-pass/daily", headers=headers)).status_code == 409


async def test_club_pass_cancel_auto_renew_calls_telegram(client, db_session, bot_token, monkeypatch):
    calls = []

    async def fake_edit(telegram_user_id, charge_id, is_canceled):
        calls.append((telegram_user_id, charge_id, is_canceled))

    monkeypatch.setattr(club_pass_service, "_request_edit_subscription", fake_edit)
    headers, _ = await _register(client, db_session, 720014, bot_token)
    inv = (await client.post("/api/v1/club-pass/stars-invoice", headers=headers)).json()
    await _pay(client, inv["payload_token"], 720014, 199, "sub-cancel")

    resp = await client.post("/api/v1/club-pass/auto-renew", headers=headers, json={"auto_renew": False})
    assert resp.status_code == 200 and resp.json()["auto_renew"] is False and resp.json()["is_active"]
    assert calls == [(720014, "sub-cancel", True)]
    # Still active, auto-renew off → buying anew is refused (resume instead).
    assert (await client.post("/api/v1/club-pass/stars-invoice", headers=headers)).status_code == 409
    resp = await client.post("/api/v1/club-pass/auto-renew", headers=headers, json={"auto_renew": True})
    assert resp.json()["auto_renew"] is True and calls[-1] == (720014, "sub-cancel", False)


async def test_club_pass_gives_extra_rewarded_mini_game_attempt(client, db_session, bot_token):
    headers, user = await _register(client, db_session, 720015, bot_token)
    config = await get_config(db_session)
    config.hangman_daily_limit = 1
    await db_session.commit()

    from app.services import hangman_service  # noqa: F401 — the capped service uses the helper

    inv = (await client.post("/api/v1/club-pass/stars-invoice", headers=headers)).json()
    await _pay(client, inv["payload_token"], 720015, 199, "sub-games")
    assert await club_pass_service.extra_rewarded_attempts(db_session, user.id, config) == 2
    config.club_pass_extra_rewarded_attempts = 0
    await db_session.commit()
    assert await club_pass_service.extra_rewarded_attempts(db_session, user.id, config) == 0


# --- «Сезонный пропуск» --------------------------------------------------------------


async def _season(client, bot_token, **kw):
    auth = await _admin(client, bot_token)
    now = datetime.now(timezone.utc)
    payload = {
        "name": "Осень", "starts_at": (now - timedelta(days=1)).isoformat(),
        "ends_at": (now + timedelta(days=30)).isoformat(), "premium_stars": 399,
        "levels": [
            {"level": 1, "xp_required": 10, "free": {"coins": 100}, "premium": {"coins": 300}},
            {"level": 2, "xp_required": 30, "free": {"coins": 200}, "premium": {"card_rarity": "epic"}},
        ],
        **kw,
    }
    resp = await client.post("/api/v1/admin/seasons", headers=auth, json=payload)
    assert resp.status_code == 200, resp.json()
    return resp.json()


async def test_season_xp_from_rewarded_games(client, db_session, bot_token):
    season = await _season(client, bot_token)
    headers, user = await _register(client, db_session, 720020, bot_token)
    await get_config(db_session)  # the hook reads the existing config row, never creates it
    locked = await lock_user_for_update(db_session, user.id)
    await credit_coins(db_session, locked, 50, TransactionType.game_reward, "game")
    await credit_coins(db_session, locked, 50, TransactionType.admin_adjustment, "not a game")
    await db_session.commit()

    body = (await client.get("/api/v1/season-pass", headers=headers)).json()
    assert body["season_id"] == season["id"] and body["xp"] == 10 and body["level"] == 1
    assert body["claimable"] == 1 and body["locked_premium"] == 1


async def test_season_claim_free_and_premium_after_purchase(client, db_session, bot_token, _setup):
    await create_player(db_session, rarity=Rarity.epic)
    season = await _season(client, bot_token)
    headers, user = await _register(client, db_session, 720021, bot_token)
    db_session.add(SeasonProgress(user_id=user.id, season_id=season["id"], xp=40))
    await db_session.commit()

    free = await client.post("/api/v1/season-pass/claim", headers=headers, json={"level": 1, "track": "free"})
    assert free.status_code == 200 and free.json()["coins"] == 100
    assert (await client.post("/api/v1/season-pass/claim", headers=headers,
                              json={"level": 1, "track": "free"})).status_code == 409
    locked = await client.post("/api/v1/season-pass/claim", headers=headers, json={"level": 2, "track": "premium"})
    assert locked.status_code == 409

    inv = (await client.post("/api/v1/season-pass/stars-invoice", headers=headers)).json()
    assert inv["stars_amount"] == 399
    assert "300 монет" in _setup[-1]["description"] and "карточек: 1" in _setup[-1]["description"]
    pre, resp = await _pay(client, inv["payload_token"], 720021, 399, "season-1")
    assert pre["ok"] and resp.json()["shop_result"]["kind"] == "season_premium"

    body = (await client.get("/api/v1/season-pass", headers=headers)).json()
    assert body["is_premium"] and body["locked_premium"] == 0 and body["claimable"] == 3
    prem = await client.post("/api/v1/season-pass/claim", headers=headers, json={"level": 2, "track": "premium"})
    assert prem.status_code == 200 and prem.json()["cards"][0]["player"]["rarity"] == "epic"
    assert (await client.post("/api/v1/season-pass/stars-invoice", headers=headers)).status_code == 409


async def test_unreached_level_cannot_be_claimed(client, db_session, bot_token):
    await _season(client, bot_token)
    headers, _ = await _register(client, db_session, 720022, bot_token)
    resp = await client.post("/api/v1/season-pass/claim", headers=headers, json={"level": 1, "track": "free"})
    assert resp.status_code == 409


async def test_no_active_season(client, db_session, bot_token):
    headers, _ = await _register(client, db_session, 720023, bot_token)
    assert (await client.get("/api/v1/season-pass", headers=headers)).json()["enabled"] is False
    assert await season_pass_service.add_xp(db_session, 1, 10) == 0


async def test_admin_season_validation(client, bot_token):
    auth = await _admin(client, bot_token)
    now = datetime.now(timezone.utc)
    bad = await client.post("/api/v1/admin/seasons", headers=auth, json={
        "name": "X", "starts_at": now.isoformat(), "ends_at": (now - timedelta(days=1)).isoformat(), "levels": [],
    })
    assert bad.status_code == 409
    season = await _season(client, bot_token)
    upd = await client.put(f"/api/v1/admin/seasons/{season['id']}", headers=auth, json={
        "name": "Осень 2", "starts_at": season["starts_at"], "ends_at": season["ends_at"], "premium_stars": 299,
        "levels": [{"level": 1, "xp_required": 5, "free": {"coins": 1}, "premium": {}}],
    })
    assert upd.status_code == 200
    assert upd.json()["name"] == "Осень 2" and len(upd.json()["levels"]) == 1


# --- starter offer --------------------------------------------------------------------


async def test_starter_offer_for_new_players_once(client, db_session, bot_token, _setup):
    frame = await _cosmetic(db_session, is_exclusive=True, style_key="starter", coins_price=0, stars_price=0)
    config = await get_config(db_session)
    config.starter_offer_cosmetic_id = frame.id
    await db_session.commit()
    headers, user = await _register(client, db_session, 720030, bot_token)

    offer = (await client.get("/api/v1/starter-offer", headers=headers)).json()
    assert offer["available"] and offer["stars_price"] == 50 and not offer["seen"]
    assert offer["contents"]["coins"] == 1000 and offer["contents"]["cosmetic"]["id"] == frame.id
    seen = (await client.post("/api/v1/starter-offer/seen", headers=headers)).json()
    assert seen["seen"]

    inv = (await client.post("/api/v1/starter-offer/stars-invoice", headers=headers)).json()
    second_inv = (await client.post("/api/v1/starter-offer/stars-invoice", headers=headers)).json()
    assert "1000 монет" in _setup[-1]["description"]
    pre, resp = await _pay(client, inv["payload_token"], 720030, 50, "starter-1")
    assert pre["ok"] and resp.status_code == 200
    await db_session.refresh(user)
    assert user.balance == 1500

    # Can't be bought twice: a second, older invoice is refused at pre-checkout.
    pre2 = await client.post("/api/v1/internal/stars-payments/pre-checkout", headers=INTERNAL,
                             json={"payload_token": second_inv["payload_token"], "total_amount": 50})
    assert pre2.json()["ok"] is False
    assert (await client.get("/api/v1/starter-offer", headers=headers)).json()["available"] is False
    assert (await client.post("/api/v1/starter-offer/stars-invoice", headers=headers)).status_code == 409
    purchases = (await db_session.execute(select(StarterOfferPurchase))).scalars().all()
    assert len(purchases) == 1


async def test_starter_offer_expires(client, db_session, bot_token):
    headers, user = await _register(client, db_session, 720031, bot_token)
    user.created_at = datetime.now(timezone.utc) - timedelta(hours=49)
    await db_session.commit()
    assert (await client.get("/api/v1/starter-offer", headers=headers)).json()["available"] is False
    assert (await client.post("/api/v1/starter-offer/stars-invoice", headers=headers)).status_code == 409


# --- admin labels ---------------------------------------------------------------------


async def test_receipts_and_analytics_name_the_products(client, db_session, bot_token):
    headers, user = await _register(client, db_session, 720040, bot_token)
    inv = (await client.post("/api/v1/starter-offer/stars-invoice", headers=headers)).json()
    await _pay(client, inv["payload_token"], 720040, 50, "label-1")
    receipt_page = await stars_receipt_service.list_receipts(
        db_session, "all", __import__("app.core.pagination", fromlist=["PageParams"]).PageParams(page=1, page_size=10),
    )
    assert receipt_page.items[0].product == "Стартовое предложение"


# --- launch switches, richer club pass ------------------------------------------------


async def test_paid_features_ship_switched_off(client, db_session, bot_token):
    from app.models.game_config import GameConfig

    fresh = GameConfig(id=2)
    assert fresh.club_pass_enabled is None or fresh.club_pass_enabled is False
    for col in ("club_pass_enabled", "season_pass_enabled", "starter_offer_enabled", "artifacts_enabled"):
        assert GameConfig.__table__.c[col].default.arg is False

    config = await get_config(db_session)
    config.club_pass_enabled = config.season_pass_enabled = config.starter_offer_enabled = False
    config.artifacts_enabled = False
    await db_session.commit()
    headers, _ = await _register(client, db_session, 720050, bot_token)
    assert (await client.post("/api/v1/club-pass/stars-invoice", headers=headers)).status_code == 409
    assert (await client.post("/api/v1/starter-offer/stars-invoice", headers=headers)).status_code == 409
    assert (await client.get("/api/v1/starter-offer", headers=headers)).json()["available"] is False
    assert (await client.get("/api/v1/season-pass", headers=headers)).json()["enabled"] is False
    assert (await client.get("/api/v1/artifacts", headers=headers)).json()["shop"] == []


async def test_club_pass_monthly_bonus_with_every_payment(client, db_session, bot_token, _setup):
    await create_player(db_session, rarity=Rarity.epic)
    config = await get_config(db_session)
    config.club_pass_bonus_card_rarity = "epic"
    await db_session.commit()
    headers, user = await _register(client, db_session, 720051, bot_token)
    status = (await client.get("/api/v1/club-pass", headers=headers)).json()
    assert status["perks"]["monthly_bonus"]["coins"] == 2000
    assert status["perks"]["season_xp_bonus_pct"] == 50 and status["perks"]["free_catchups"] == 3

    inv = (await client.post("/api/v1/club-pass/stars-invoice", headers=headers)).json()
    assert "каждый месяц сразу: 2000 монет" in _setup[-1]["description"]
    await _pay(client, inv["payload_token"], 720051, 199, "sub-bonus-1")
    await db_session.refresh(user)
    assert user.balance == 500 + 2000
    await client.post("/api/v1/internal/stars-payments/deliver", headers=INTERNAL, json={
        "payload_token": inv["payload_token"], "telegram_user_id": 720051,
        "telegram_payment_charge_id": "sub-bonus-2", "total_amount": 199,
    })
    await db_session.refresh(user)
    assert user.balance == 500 + 4000
    from app.models.card import UserCard

    cards = (await db_session.execute(select(UserCard).where(UserCard.owner_id == user.id))).scalars().all()
    assert len(cards) == 2


async def test_club_pass_boosts_season_xp(client, db_session, bot_token):
    await _season(client, bot_token)
    headers, user = await _register(client, db_session, 720052, bot_token)
    inv = (await client.post("/api/v1/club-pass/stars-invoice", headers=headers)).json()
    await _pay(client, inv["payload_token"], 720052, 199, "sub-xp")
    locked = await lock_user_for_update(db_session, user.id)
    await credit_coins(db_session, locked, 50, TransactionType.game_reward, "game")
    await db_session.commit()
    assert (await client.get("/api/v1/season-pass", headers=headers)).json()["xp"] == 15


async def test_club_pass_free_calendar_catchups(client, db_session, bot_token, monkeypatch):
    from datetime import date

    from app.services import daily_reward_service

    monkeypatch.setattr(daily_reward_service, "local_today", lambda: date(2026, 10, 16))
    headers, user = await _register(client, db_session, 720053, bot_token)
    no_pass = await client.post("/api/v1/daily-rewards/catch-up", headers=headers, json={"date": "2026-10-02", "free": True})
    assert no_pass.status_code == 409

    inv = (await client.post("/api/v1/club-pass/stars-invoice", headers=headers)).json()
    await _pay(client, inv["payload_token"], 720053, 199, "sub-catch")
    await db_session.refresh(user)
    before = user.balance
    for n in (2, 3, 4):
        ok = await client.post("/api/v1/daily-rewards/catch-up", headers=headers, json={"date": f"2026-10-0{n}", "free": True})
        assert ok.status_code == 200, ok.json()
    assert (await client.post("/api/v1/daily-rewards/catch-up", headers=headers,
                              json={"date": "2026-10-05", "free": True})).status_code == 409
    calendar = (await client.get("/api/v1/daily-rewards/calendar", headers=headers)).json()
    assert calendar["free_catchups_left"] == 0 and calendar["catchups_left"] == 5  # paid ones untouched
    await db_session.refresh(user)
    assert user.balance == before + (50 + 5) + (50 + 10) + (50 + 15)  # no coins charged


# --- «Артефакты» ----------------------------------------------------------------------


async def _artifact(client, bot_token, **kw):
    auth = await _admin(client, bot_token)
    payload = {"name": "This is Anfield", "target": "club", "effect": "opp_home_pct", "effect_value": 1,
               "coins_price": 100, "stars_price": 20, **kw}
    resp = await client.post("/api/v1/admin/artifacts", headers=auth, json=payload)
    assert resp.status_code == 200, resp.json()
    return resp.json()


def _copies_of(body, artifact_id):
    return [c for c in body["shelf"] if c["artifact"]["id"] == artifact_id]


async def test_artifact_copies_one_active_per_artifact_and_three_slots(client, db_session, bot_token):
    from app.services import artifact_service

    shirt = await _artifact(client, bot_token, name="Футболка Марадоны", target="my_player", effect="attack", effect_value=3)
    others = [await _artifact(client, bot_token, name=f"Артефакт {i}", target="my_player", effect="defense", effect_value=1)
              for i in range(3)]
    headers, user = await _register(client, db_session, 720060, bot_token)
    user.balance = 10_000
    await db_session.commit()

    body = (await client.post(f"/api/v1/artifacts/{shirt['id']}/buy", headers=headers)).json()
    body = (await client.post(f"/api/v1/artifacts/{shirt['id']}/buy", headers=headers)).json()
    copies = _copies_of(body, shirt["id"])
    assert len(copies) == 2 and [c["equipped"] for c in copies] == [True, False]  # the copy goes to the shelf
    assert {c["serial_number"] for c in copies} == {1, 2}
    assert body["effects"]["my_player"] == [{"effect": "attack", "value": 3, "label": "+3 к атаке"}]

    second = next(c for c in copies if not c["equipped"])
    dup = await client.post(f"/api/v1/artifacts/copies/{second['copy_id']}/active", headers=headers, json={"equipped": True})
    assert dup.status_code == 409  # copies never stack

    for a in others:
        body = (await client.post(f"/api/v1/artifacts/{a['id']}/buy", headers=headers)).json()
    assert body["active_count"] == 3  # 3 slots: the last purchase stayed on the shelf
    last = _copies_of(body, others[-1]["id"])[0]
    assert last["equipped"] is False
    full = await client.post(f"/api/v1/artifacts/copies/{last['copy_id']}/active", headers=headers, json={"equipped": True})
    assert full.status_code == 409
    effects = await artifact_service.effects_of(db_session, user.id, "my_player")
    assert effects == {"attack": 3, "defense": 2}


async def test_my_player_artifact_reaches_match_stats(client, db_session, bot_token):
    from app.models.enums import Position
    from app.models.my_player import MyPlayer
    from app.services import my_player_service

    shirt = await _artifact(client, bot_token, name="Футболка", target="my_player", effect="attack", effect_value=4)
    plaque = await _artifact(client, bot_token)  # a club artifact does nothing for «Мой игрок»
    headers, user = await _register(client, db_session, 720061, bot_token)
    mp = MyPlayer(user_id=user.id, name="Тест", position=Position.ST, attributes={"atk": 60, "def": 40})
    db_session.add(mp)
    await db_session.commit()
    config = await get_config(db_session)
    before = await my_player_service.match_stats(db_session, mp, config)
    await client.post(f"/api/v1/artifacts/{plaque['id']}/buy", headers=headers)
    assert (await my_player_service.match_stats(db_session, mp, config))["attack"] == before["attack"]
    await client.post(f"/api/v1/artifacts/{shirt['id']}/buy", headers=headers)
    after = await my_player_service.match_stats(db_session, mp, config)
    assert after["attack"] == before["attack"] + 4 and after["defense"] == before["defense"]


async def test_stadium_artifact_is_stronger_with_that_stadium(client, db_session, bot_token):
    from app.models.enums import CardSource, Rarity as R
    from app.models.stadium import Stadium
    from app.models.user_stadium_card import UserStadiumCard
    from app.services import artifact_service

    stadium = Stadium(display_name="Энфилд", rarity=R.epic, club="Liverpool")
    db_session.add(stadium)
    await db_session.commit()
    a = await _artifact(client, bot_token, link_type="stadium", link_id=stadium.id, link_effect_value=2)
    headers, user = await _register(client, db_session, 720062, bot_token)
    await client.post(f"/api/v1/artifacts/{a['id']}/buy", headers=headers)
    assert (await artifact_service.effects_of(db_session, user.id, "club")) == {"opp_home_pct": 1}

    db_session.add(UserStadiumCard(user_id=user.id, stadium_id=stadium.id, serial_number=1, source=CardSource.admin_grant))
    await db_session.commit()
    assert (await artifact_service.effects_of(db_session, user.id, "club")) == {"opp_home_pct": 2}
    shop_item = next(i for i in (await client.get("/api/v1/artifacts", headers=headers)).json()["shop"] if i["id"] == a["id"])
    assert shop_item["link_owned"] and shop_item["link_name"] == "Энфилд"
    assert shop_item["active_label"] == "−2% к силе соперника в домашних матчах"


async def test_club_artifacts_change_coach_career_runners(db_session):
    from types import SimpleNamespace

    from app.models.monetization import Artifact, UserArtifact
    from app.models.user import User
    from app.services import career_service

    config = await get_config(db_session)
    user = User(telegram_id=720070, first_name="Coach", balance=0)
    db_session.add(user)
    await db_session.flush()
    for name, effect, value in (("Табличка", "opp_home_pct", 4), ("Флаг", "team_boost_pct", 3)):
        a = Artifact(name=name, target="club", effect=effect, effect_value=value)
        db_session.add(a)
        await db_session.flush()
        db_session.add(UserArtifact(user_id=user.id, artifact_id=a.id, serial_number=1, equipped=True, source="admin"))
    await db_session.commit()
    teams = [{"user_id": user.id}, {"user_id": None}]
    home, away = SimpleNamespace(boost=1.0), SimpleNamespace(boost=1.0)
    await career_service._apply_club_artifacts(db_session, teams, 0, 1, home, away, config)
    assert home.boost == pytest.approx(1.03) and away.boost == pytest.approx(0.96)
    # Away from home only the own-team boost applies.
    home, away = SimpleNamespace(boost=1.0), SimpleNamespace(boost=1.0)
    await career_service._apply_club_artifacts(db_session, teams[::-1], 0, 1, home, away, config)
    assert home.boost == pytest.approx(1.0) and away.boost == pytest.approx(1.03)


def test_home_edge_weakens_the_away_side():
    from app.services import player_career_service

    team = {"index": 1, "name": "X", "mentality": "balanced", "playstyle": "balanced", "players": [
        {"slot": slot.code, "name": f"P{i}", "position": slot.ideal_position.value, "rating": 80}
        for i, slot in enumerate(player_career_service.get_formation_slots(player_career_service.FORMATION))
    ]}
    _side, plain = player_career_service._side(team, None, None)
    _side, weak = player_career_service._side(team, None, None, weaken_pct=5)
    assert all(p["rating"] == 80 for p in plain) and all(p["rating"] == 76 for p in weak)


async def test_gift_an_artifact_copy_to_a_friend(client, db_session, bot_token):
    from app.models.career import Friendship
    from app.services import friend_service

    a = await _artifact(client, bot_token)
    headers, user = await _register(client, db_session, 720071, bot_token)
    friend_headers, friend = await _register(client, db_session, 720072, bot_token)
    stranger_headers, stranger = await _register(client, db_session, 720073, bot_token)
    body = (await client.post(f"/api/v1/artifacts/{a['id']}/buy", headers=headers)).json()
    copy_id = body["shelf"][0]["copy_id"]

    refused = await client.post(f"/api/v1/artifacts/copies/{copy_id}/gift", headers=headers, json={"recipient_id": stranger.id})
    assert refused.status_code == 403

    db_session.add(Friendship(requester_id=user.id, addressee_id=friend.id, user_low=min(user.id, friend.id),
                              user_high=max(user.id, friend.id), status="accepted"))
    await db_session.commit()
    assert friend.id in await friend_service.friend_ids(db_session, user.id)

    resp = await client.post(f"/api/v1/artifacts/copies/{copy_id}/gift", headers=headers, json={"recipient_id": friend.id})
    assert resp.status_code == 200 and resp.json()["shelf"] == []
    theirs = (await client.get("/api/v1/artifacts", headers=friend_headers)).json()["shelf"]
    assert len(theirs) == 1 and theirs[0]["source"] == "gift" and theirs[0]["equipped"]


async def test_artifact_for_stars_and_limited_supply(client, db_session, bot_token):
    a = await _artifact(client, bot_token, coins_price=0, stars_price=20, max_supply=1)
    headers, user = await _register(client, db_session, 720063, bot_token)
    other_headers, _ = await _register(client, db_session, 720064, bot_token)
    assert (await client.post(f"/api/v1/artifacts/{a['id']}/buy", headers=headers)).status_code == 409  # stars only

    inv = (await client.post(f"/api/v1/artifacts/{a['id']}/stars-invoice", headers=headers)).json()
    pre, resp = await _pay(client, inv["payload_token"], 720063, 20, "art-1")
    assert pre["ok"] and resp.json()["shop_result"]["kind"] == "artifact"
    assert (await client.post(f"/api/v1/artifacts/{a['id']}/stars-invoice", headers=other_headers)).status_code == 409


async def test_admin_artifact_rules(client, db_session, bot_token):
    auth = await _admin(client, bot_token)
    bad = await client.post("/api/v1/admin/artifacts", headers=auth, json={
        "name": "X", "target": "club", "effect": "attack", "effect_value": 2,
    })
    assert bad.status_code == 409  # attack is a «Мой игрок» effect
    a = await _artifact(client, bot_token)
    _, user = await _register(client, db_session, 720065, bot_token)
    resp = await client.post(f"/api/v1/admin/artifacts/{a['id']}/grant", headers=auth, json={"user_id": user.id})
    assert resp.status_code == 200 and resp.json()["serial_number"] == 1


async def test_my_player_match_artifacts_reach_engine_card(client, db_session, bot_token):
    from app.models.enums import Position
    from app.models.my_player import MyPlayer
    from app.services import my_player_service

    effects = [("match_rating", 2), ("skill_level", 1), ("shot_pp", 3)]
    artifacts = [await _artifact(client, bot_token, name=f"A{e}", target="my_player", effect=e, effect_value=v)
                 for e, v in effects]
    headers, user = await _register(client, db_session, 720080, bot_token)
    user.balance = 10_000
    db_session.add(MyPlayer(user_id=user.id, name="Тест", position=Position.ST, attributes={"atk": 60, "def": 40},
                            skill_code="sniper", skill_level=1))
    await db_session.commit()
    config = await get_config(db_session)
    config.card_skills_enabled = True
    await db_session.commit()
    before = await my_player_service.engine_card(db_session, user.id, config)
    for a in artifacts:
        await client.post(f"/api/v1/artifacts/{a['id']}/buy", headers=headers)
    after = await my_player_service.engine_card(db_session, user.id, config)
    assert after.player.rating == before.player.rating + 2
    assert after.skill_level == 2 and after.boosts == {"shot_pp": 3}


def test_engine_reads_shot_and_dribble_boosts(monkeypatch):
    import random
    from types import SimpleNamespace

    from app.services import club_tactical_matchup_service as m
    from app.services import tournament_match_engine as e

    monkeypatch.setattr(random, "random", lambda: 0.30)
    plain = {"name": "X", "rating": 70}
    missed, _notes, _aerial = e._shot_miss_roll(0.32, plain, {}, None)
    assert missed is True
    boosted, _notes, _aerial = e._shot_miss_roll(0.32, {**plain, "boosts": {"shot_pp": 5}}, {}, None)
    assert boosted is False  # 0.30 < 0.32 misses; < 0.27 needed with the artifact

    picks = []
    monkeypatch.setattr(random, "choices", lambda outcomes, weights, k: picks.append(weights) or [outcomes[0]])
    duelist = SimpleNamespace(skill=None, boosts={"dribble_pp": 10}, player=SimpleNamespace(display_name="D"))
    m._resolve_stage1_for(1.0, duelist, [])
    base = m._stage1_weights(1.0, 0.0)
    assert picks[-1][2] == pytest.approx(base[2] / sum(base) + 0.10)


async def test_coach_link_and_player_card_bonus(client, db_session, bot_token):
    from types import SimpleNamespace

    from app.models.coach import Coach
    from app.models.enums import CardSource, Rarity as R
    from app.models.user_coach_card import UserCoachCard
    from app.services import artifact_service, career_service

    coach = Coach(display_name="Сэр Алекс Фергюсон", rarity=R.legendary)
    db_session.add(coach)
    maradona = await create_player(db_session, rarity=Rarity.legendary)
    await db_session.commit()
    board = await _artifact(client, bot_token, name="Доска Фергюсона", target="club", effect="team_boost_pct",
                            effect_value=1, link_type="coach", link_id=coach.id, link_effect_value=3)
    shirt = await _artifact(client, bot_token, name="Футболка Марадоны", target="my_player", effect="dribble_pp",
                            effect_value=2, card_player_id=maradona.id, card_rating_bonus=3)
    headers, user = await _register(client, db_session, 720090, bot_token)
    user.balance = 10_000
    await db_session.commit()
    for a in (board, shirt):
        await client.post(f"/api/v1/artifacts/{a['id']}/buy", headers=headers)
    assert (await artifact_service.effects_of(db_session, user.id, "club")) == {"team_boost_pct": 1}
    db_session.add(UserCoachCard(user_id=user.id, coach_id=coach.id, serial_number=1, source=CardSource.admin_grant))
    await db_session.commit()
    assert (await artifact_service.effects_of(db_session, user.id, "club")) == {"team_boost_pct": 3}
    assert await artifact_service.card_bonuses(db_session, user.id) == {maradona.id: 3}

    item = next(i for i in (await client.get("/api/v1/artifacts", headers=headers)).json()["shop"] if i["id"] == shirt["id"])
    assert item["card_label"] == f"+3 к рейтингу карточек «{maradona.display_name}»"

    config = await get_config(db_session)
    mine = SimpleNamespace(card=SimpleNamespace(player_id=maradona.id), base_rating=88)
    other = SimpleNamespace(card=SimpleNamespace(player_id=-1), base_rating=70)
    run = SimpleNamespace(boost=1.0, on_pitch=[mine, other], bench=[])
    bot = SimpleNamespace(boost=1.0, on_pitch=[], bench=[])
    await career_service._apply_club_artifacts(db_session, [{"user_id": user.id}, {"user_id": None}], 0, 1, run, bot, config)
    assert mine.base_rating == 91 and other.base_rating == 70 and run.boost == pytest.approx(1.03)


def test_dribbler_skill_and_artifact_add_up(monkeypatch):
    import random
    from types import SimpleNamespace

    from app.services import club_tactical_matchup_service as m

    seen = []
    real = m.skill_choice

    def spy(outcomes, weights, boosted, effect, player=None):
        seen.append(effect)
        return real(outcomes, weights, boosted, effect, player=player)

    monkeypatch.setattr(m, "skill_choice", spy)
    random.seed(1)
    skill = {"code": "dribbler", "level": 2, "bonus_pp": 4, "cap_pp": 8, "floor": 0.02, "ceiling": 0.95}
    duelist = SimpleNamespace(skill=skill, boosts={"dribble_pp": 3}, player=SimpleNamespace(display_name="D"))
    m._resolve_stage1_for(1.0, duelist, [])
    assert seen[-1]["bonus_pp"] == 7 and seen[-1]["cap_pp"] == 11
