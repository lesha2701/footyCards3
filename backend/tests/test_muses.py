"""«Музы» (services/muse_service.py): pack drops, the album, the active Muse
and her bonus for «Мой футболист», gifts that raise it (coins and Stars),
the daily coins, spare copies and the admin catalog."""
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.config import get_settings
from app.models.enums import Position, Rarity, TransactionType
from app.models.game_config import GameConfig
from app.models.muse import Muse, MuseAccessory, MuseCollection, MuseDailyClaim, MuseDate, UserMuse, UserMuseAccessory
from app.models.transaction import CoinTransaction
from app.services import muse_service, stars_payment_service
from tests.factories import create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1/muses"
INTERNAL = {"X-Internal-Secret": get_settings().internal_api_secret}


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    rate_limit_module._hits.clear()

    async def fake_link(payload_token, title, description, stars_amount, subscription_period=None):
        return f"https://t.me/invoice/{payload_token}"

    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", fake_link)
    yield


async def _config(db_session, **overrides) -> GameConfig:
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
    config.muses_enabled = True
    config.muse_date_required = False  # date tests switch it on
    for key, value in overrides.items():
        setattr(config, key, value)
    await db_session.commit()
    return config


async def _muse(db_session, **kw) -> Muse:
    data = dict(name="Муза", rarity="rare", effect="daily_coins", effect_value=100)
    data.update(kw)
    muse = Muse(**data)
    db_session.add(muse)
    await db_session.commit()
    await db_session.refresh(muse)
    return muse


async def _gift(db_session, **kw) -> MuseAccessory:
    data = dict(name="Сумка", kind="bag", boost_pct=20, coins_price=500)
    data.update(kw)
    gift = MuseAccessory(**data)
    db_session.add(gift)
    await db_session.commit()
    await db_session.refresh(gift)
    return gift


async def _register(client, db_session, telegram_id, bot_token, balance=10_000):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, telegram_id)
    user.balance = balance
    await db_session.commit()
    return headers, user


async def _own(db_session, user_id, muse, active=True, copies=1) -> UserMuse:
    row = UserMuse(user_id=user_id, muse_id=muse.id, copies=copies, is_active=active, source="admin")
    db_session.add(row)
    await db_session.commit()
    return row


# --- bonus math ---------------------------------------------------------------------------------


def test_boosted_value_rounds_half_up_and_caps():
    config = NS(muse_max_stat=6, muse_max_pp=12, muse_max_xp_pct=30, muse_max_daily_coins=1000, muse_max_accessory_pct=100)
    assert muse_service.boosted_value(NS(effect="attack", effect_value=1), 50, config) == 2
    assert muse_service.boosted_value(NS(effect="attack", effect_value=3), 0, config) == 3
    assert muse_service.boosted_value(NS(effect="attack", effect_value=5), 100, config) == 6  # stat cap
    assert muse_service.boosted_value(NS(effect="daily_coins", effect_value=300), 250, config) == 600  # gifts cap 100%
    assert muse_service.boosted_value(NS(effect="shot_pp", effect_value=10), 50, config) == 12


# --- packs --------------------------------------------------------------------------------------


async def test_muse_pack_drops_muses_first_becomes_active_repeat_adds_copies(client, db_session, bot_token):
    await _config(db_session)
    muse = await _muse(db_session, rarity="epic")
    await create_player(db_session, rarity=Rarity.epic)
    pack = await create_pack(db_session, "muses-t", price=10, card_count=3, probabilities={Rarity.epic: 1.0},
                             muse_drop_chance=1.0)
    headers, user = await _register(client, db_session, 830001, bot_token)

    first = await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={"idempotency_key": "m-1"})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["cards"] == [] and len(body["muses"]) == 3
    assert [m["is_new"] for m in body["muses"]] == [True, False, False]
    assert body["muses"][0]["muse"]["name"] == "Муза"
    row = (await db_session.execute(select(UserMuse).where(UserMuse.user_id == user.id)
                                    .execution_options(populate_existing=True))).scalar_one()
    assert row.copies == 3 and row.is_active and row.muse_id == muse.id

    replay = await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={"idempotency_key": "m-1"})
    assert len(replay.json()["muses"]) == 3
    await db_session.refresh(row)
    assert row.copies == 3


async def test_bulk_open_returns_muses_and_replays_them(client, db_session, bot_token):
    await _config(db_session)
    await _muse(db_session, rarity="epic")
    await create_player(db_session, rarity=Rarity.epic)
    pack = await create_pack(db_session, "muses-bulk", price=10, card_count=2, probabilities={Rarity.epic: 1.0},
                             muse_drop_chance=1.0)
    headers, _ = await _register(client, db_session, 830013, bot_token)

    body = {"quantity": 3, "idempotency_key": "bulk-m-1"}
    first = await client.post(f"/api/v1/packs/{pack.id}/open-bulk", headers=headers, json=body)
    assert first.status_code == 200, first.text
    assert first.json()["cards"] == [] and len(first.json()["muses"]) == 6
    replay = await client.post(f"/api/v1/packs/{pack.id}/open-bulk", headers=headers, json=body)
    assert len(replay.json()["muses"]) == 6


async def test_switched_off_or_empty_pool_drops_footballers(client, db_session, bot_token):
    await _config(db_session, muses_enabled=False)
    await _muse(db_session)
    await create_player(db_session, rarity=Rarity.common)
    pack = await create_pack(db_session, "muses-off", price=10, card_count=2, probabilities={Rarity.common: 1.0},
                             muse_drop_chance=1.0)
    headers, _ = await _register(client, db_session, 830002, bot_token)
    body = (await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={})).json()
    assert len(body["cards"]) == 2 and body["muses"] == []


def test_pick_random_muse_prefers_the_slot_rarity_then_closest():
    common, legend = NS(rarity="common", drop_weight=1), NS(rarity="legendary", drop_weight=1)
    assert muse_service.pick_random_muse([common, legend], Rarity.diamond) is legend
    assert muse_service.pick_random_muse([common, legend], Rarity.rare) is common
    assert muse_service.pick_random_muse([legend], Rarity.common) is legend
    assert muse_service.pick_random_muse([], Rarity.common) is None


# --- album, active Muse, «Мой футболист» -----------------------------------------------------------


async def test_active_muse_reaches_my_player_match_stats(client, db_session, bot_token):
    from app.models.my_player import MyPlayer
    from app.services import my_player_service

    config = await _config(db_session)
    striker = await _muse(db_session, name="Луиза", effect="attack", effect_value=3)
    coins = await _muse(db_session, name="Марта", effect="daily_coins", effect_value=100)
    headers, user = await _register(client, db_session, 830003, bot_token)
    mp = MyPlayer(user_id=user.id, name="Тест", position=Position.ST, attributes={"atk": 60, "def": 40})
    db_session.add(mp)
    await _own(db_session, user.id, striker, active=False)
    await _own(db_session, user.id, coins, active=True)
    before = await my_player_service.match_stats(db_session, mp, config)

    resp = await client.post(f"{API}/active", headers=headers, json={"muse_id": striker.id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["active"]["id"] == striker.id
    rows = (await db_session.execute(select(UserMuse).where(UserMuse.user_id == user.id)
                                     .execution_options(populate_existing=True))).scalars().all()
    assert {r.muse_id: r.is_active for r in rows} == {striker.id: True, coins.id: False}
    after = await my_player_service.match_stats(db_session, mp, config)
    assert after["attack"] == before["attack"] + 3

    config.muses_enabled = False
    await db_session.commit()
    assert (await my_player_service.match_stats(db_session, mp, config))["attack"] == before["attack"]


async def test_album_lists_collections_owned_and_missing(client, db_session, bot_token):
    await _config(db_session)
    collection = MuseCollection(name="Звёздные музы")
    db_session.add(collection)
    await db_session.commit()
    a = await _muse(db_session, name="А", collection_id=collection.id)
    await _muse(db_session, name="Б", collection_id=collection.id)
    headers, user = await _register(client, db_session, 830004, bot_token)
    await _own(db_session, user.id, a, copies=2)

    body = (await client.get(API, headers=headers)).json()
    assert body["enabled"] and body["owned_count"] == 1 and body["total_count"] == 2
    group = body["collections"][0]
    assert group["name"] == "Звёздные музы"
    assert [(m["name"], m["owned"], m["copies"]) for m in group["muses"]] == [("А", True, 2), ("Б", False, 0)]
    assert body["active"]["name"] == "А" and body["daily"] == {"coins": 100, "claimed_today": False, "claimed_coins": 0}


async def test_cannot_activate_a_muse_you_do_not_own(client, db_session, bot_token):
    await _config(db_session)
    muse = await _muse(db_session)
    headers, _ = await _register(client, db_session, 830005, bot_token)
    assert (await client.post(f"{API}/active", headers=headers, json={"muse_id": muse.id})).status_code == 404


# --- daily coins --------------------------------------------------------------------------------


async def test_daily_coins_once_a_day_even_after_switching(client, db_session, bot_token):
    await _config(db_session)
    rich = await _muse(db_session, name="Изабелла", effect="daily_coins", effect_value=300)
    other = await _muse(db_session, name="Марта", effect="daily_coins", effect_value=200)
    headers, user = await _register(client, db_session, 830006, bot_token, balance=0)
    await _own(db_session, user.id, rich)
    await _own(db_session, user.id, other, active=False)

    resp = await client.post(f"{API}/daily/claim", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["claimed"] == 300 and resp.json()["new_balance"] == 300
    assert (await client.post(f"{API}/daily/claim", headers=headers)).status_code == 409
    await client.post(f"{API}/active", headers=headers, json={"muse_id": other.id})
    assert (await client.post(f"{API}/daily/claim", headers=headers)).status_code == 409
    claims = (await db_session.execute(select(MuseDailyClaim).where(MuseDailyClaim.user_id == user.id))).scalars().all()
    assert len(claims) == 1
    tx = (await db_session.execute(select(CoinTransaction).where(
        CoinTransaction.user_id == user.id, CoinTransaction.type == TransactionType.muse_daily_coins,
    ))).scalars().all()
    assert [t.amount for t in tx] == [300]


async def test_daily_claim_needs_a_coin_muse(client, db_session, bot_token):
    await _config(db_session)
    muse = await _muse(db_session, effect="attack", effect_value=2)
    headers, user = await _register(client, db_session, 830007, bot_token)
    await _own(db_session, user.id, muse)
    assert (await client.post(f"{API}/daily/claim", headers=headers)).status_code == 409


# --- gifts --------------------------------------------------------------------------------------


async def test_gift_for_coins_raises_the_bonus_once_and_is_idempotent(client, db_session, bot_token):
    await _config(db_session)
    muse = await _muse(db_session, effect="daily_coins", effect_value=100)
    bag = await _gift(db_session, boost_pct=50, coins_price=700)
    headers, user = await _register(client, db_session, 830008, bot_token, balance=1000)
    await _own(db_session, user.id, muse)

    body = {"accessory_id": bag.id, "idempotency_key": "gift-1"}
    resp = await client.post(f"{API}/{muse.id}/gifts", headers=headers, json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["new_balance"] == 300
    assert resp.json()["active"]["boosted_value"] == 150 and resp.json()["active"]["accessory_ids"] == [bag.id]
    replay = await client.post(f"{API}/{muse.id}/gifts", headers=headers, json=body)
    assert replay.status_code == 200 and replay.json()["new_balance"] == 300
    again = await client.post(f"{API}/{muse.id}/gifts", headers=headers, json={"accessory_id": bag.id})
    assert again.status_code == 409
    assert await muse_service.effects_of(db_session, user.id) == {"daily_coins": 150}


async def test_gift_needs_the_muse_and_enough_coins(client, db_session, bot_token):
    await _config(db_session)
    muse = await _muse(db_session)
    bag = await _gift(db_session, coins_price=5000)
    headers, user = await _register(client, db_session, 830009, bot_token, balance=100)
    assert (await client.post(f"{API}/{muse.id}/gifts", headers=headers, json={"accessory_id": bag.id})).status_code == 404
    await _own(db_session, user.id, muse)
    assert (await client.post(f"{API}/{muse.id}/gifts", headers=headers, json={"accessory_id": bag.id})).status_code == 400


async def test_gift_for_stars_is_delivered_and_a_raced_duplicate_refunds_coins(client, db_session, bot_token):
    await _config(db_session)
    muse = await _muse(db_session)
    dress = await _gift(db_session, name="Платье", kind="dress", coins_price=0, stars_price=40, boost_pct=40)
    headers, user = await _register(client, db_session, 830010, bot_token, balance=0)
    owned = await _own(db_session, user.id, muse)
    assert (await client.post(f"{API}/{muse.id}/gifts", headers=headers, json={"accessory_id": dress.id})).status_code == 409

    invoices = [
        (await client.post(f"{API}/{muse.id}/gifts/stars-invoice", headers=headers, json={"accessory_id": dress.id})).json()
        for _ in range(2)
    ]
    assert invoices[0]["stars_amount"] == 40
    for i, inv in enumerate(invoices):
        pre = await client.post("/api/v1/internal/stars-payments/pre-checkout", headers=INTERNAL,
                                json={"payload_token": inv["payload_token"], "total_amount": 40})
        assert pre.json()["ok"]
    for i, inv in enumerate(invoices):
        resp = await client.post("/api/v1/internal/stars-payments/deliver", headers=INTERNAL, json={
            "payload_token": inv["payload_token"], "telegram_user_id": 830010,
            "telegram_payment_charge_id": f"muse-{i}", "total_amount": 40,
        })
        assert resp.status_code == 200, resp.text
    gifts = (await db_session.execute(select(UserMuseAccessory).where(UserMuseAccessory.user_muse_id == owned.id))).scalars().all()
    assert [g.accessory_id for g in gifts] == [dress.id]
    await db_session.refresh(user)
    assert user.balance == 4000  # the second paid copy came back as coins
    # Pre-checkout now refuses: she already has it.
    inv = (await client.post(f"{API}/{muse.id}/gifts/stars-invoice", headers=headers, json={"accessory_id": dress.id}))
    assert inv.status_code == 409


# --- spares -------------------------------------------------------------------------------------


async def test_sell_spare_copies_keeps_the_muse(client, db_session, bot_token):
    await _config(db_session, muse_spare_coins={"common": 10, "rare": 400, "epic": 1, "legendary": 1})
    muse = await _muse(db_session, rarity="rare")
    headers, user = await _register(client, db_session, 830011, bot_token, balance=0)
    row = await _own(db_session, user.id, muse, copies=3)

    resp = await client.post(f"{API}/{muse.id}/sell-spare", headers=headers, json={"count": 2})
    assert resp.status_code == 200, resp.text
    assert resp.json()["sold_coins"] == 800 and resp.json()["new_balance"] == 800
    await db_session.refresh(row)
    assert row.copies == 1
    assert (await client.post(f"{API}/{muse.id}/sell-spare", headers=headers, json={"count": 1})).status_code == 409


# --- admin --------------------------------------------------------------------------------------


async def _admin(client, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(999000001, bot_token))
    return {"Authorization": f"Bearer {resp.json()['admin_token']}"}


async def test_admin_creates_collection_muse_gift_and_grants(client, db_session, bot_token):
    await _config(db_session)
    admin = await _admin(client, bot_token)
    col = (await client.post("/api/v1/admin/muses/collections", headers=admin, json={"name": "Новые"})).json()
    payload = {"name": "Героиня", "title": "певица", "rarity": "epic", "collection_id": col["id"],
               "effect": "shot_pp", "effect_value": 5}
    muse = (await client.post("/api/v1/admin/muses/muses", headers=admin, json=payload)).json()
    assert muse["effect_label"] == "+5% к точности удара"
    bad = await client.post("/api/v1/admin/muses/muses", headers=admin, json={**payload, "effect": "nope"})
    assert bad.status_code == 409
    upd = await client.put(f"/api/v1/admin/muses/muses/{muse['id']}", headers=admin, json={**payload, "effect_value": 7})
    assert upd.json()["effect_value"] == 7
    gift = (await client.post("/api/v1/admin/muses/accessories", headers=admin,
                              json={"name": "Колье", "kind": "jewelry", "boost_pct": 30, "stars_price": 100})).json()
    assert gift["kind_label"] == "Украшение"

    _, user = await _register(client, db_session, 830012, bot_token)
    grant = await client.post(f"/api/v1/admin/muses/muses/{muse['id']}/grant", headers=admin, json={"user_id": user.id})
    assert grant.status_code == 200 and grant.json()["is_new"]
    catalog = (await client.get("/api/v1/admin/muses", headers=admin)).json()
    assert {c["name"] for c in catalog["collections"]} >= {"Новые"}
    assert any(m["name"] == "Героиня" for m in catalog["muses"]) and catalog["accessories"][0]["name"] == "Колье"
    assert (await client.get("/api/v1/admin/muses")).status_code in (401, 403)
    cfg = (await client.put("/api/v1/admin/games/config", headers=admin, json={"muse_max_pp": 9})).json()
    assert cfg["muse_max_pp"] == 9 and cfg["muses_enabled"] is True


# --- «Свидание» ------------------------------------------------------------------------------


async def _lose_hangman(client, headers, session_id, db_session):
    from app.models.game import GameSession

    session = await db_session.get(GameSession, session_id)
    await db_session.refresh(session)
    word = session.server_state["word"]
    body = None
    for letter in "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ":
        if letter in word:
            continue
        body = (await client.post(f"/api/v1/games/hangman/{session_id}/guess", headers=headers, json={"letter": letter})).json()
        if body.get("status") in ("lost", "won"):
            break
    return body


async def test_date_is_an_extra_attempt_pays_once_and_any_result_counts(client, db_session, bot_token):
    from datetime import datetime, timezone

    config = await _config(db_session, muse_date_games=["hangman"], muse_date_coins=150, hourly_game_limit=1)
    muse = await _muse(db_session)
    headers, user = await _register(client, db_session, 830020, bot_token, balance=0)
    await _own(db_session, user.id, muse)
    # The hourly attempt is already used up.
    user.hangman_hourly_attempts, user.hangman_hour_started_at = 1, datetime.now(timezone.utc)
    await db_session.commit()
    assert (await client.post("/api/v1/games/hangman/start", headers=headers)).status_code == 409
    # No date started yet: the muse flag is refused.
    assert (await client.post("/api/v1/games/hangman/start?muse_date=true", headers=headers)).status_code == 409

    date = (await client.post(f"{API}/date/start", headers=headers)).json()
    assert date["game"] == "hangman" and date["path"] == "/play/hangman?muse=1"
    start = await client.post("/api/v1/games/hangman/start?muse_date=true", headers=headers)
    assert start.status_code == 200, start.text
    await db_session.refresh(user)
    assert user.hangman_hourly_attempts == 1  # not burnt

    await _lose_hangman(client, headers, start.json()["session_id"], db_session)  # losing is fine
    claim = await client.post(f"/api/v1/games/hangman/{start.json()['session_id']}/claim", headers=headers)
    assert claim.status_code == 200, claim.text
    assert claim.json()["reward_coins"] == config.muse_date_coins
    await db_session.refresh(user)
    assert user.balance == 150 and user.hangman_rewarded_attempts_today == 0
    row = (await db_session.execute(select(MuseDate).where(MuseDate.user_id == user.id))).scalar_one()
    assert row.completed_at is not None and row.coins == 150

    assert (await client.post(f"{API}/date/start", headers=headers)).status_code == 409  # once a day
    assert (await client.post("/api/v1/games/hangman/start?muse_date=true", headers=headers)).status_code == 409
    album = (await client.get(API, headers=headers)).json()
    assert album["date"]["today"]["completed"] and album["date"]["inspired_until"]


async def test_date_needs_an_active_muse(client, db_session, bot_token):
    await _config(db_session)
    headers, _ = await _register(client, db_session, 830021, bot_token)
    assert (await client.post(f"{API}/date/start", headers=headers)).status_code == 409


async def test_required_date_keeps_the_bonus_alive(client, db_session, bot_token):
    from datetime import datetime, timedelta, timezone

    from app.core.timeutil import local_today

    await _config(db_session, muse_date_required=True, muse_inspiration_hours=36)
    muse = await _muse(db_session, effect="attack", effect_value=3)
    headers, user = await _register(client, db_session, 830022, bot_token)
    await _own(db_session, user.id, muse)
    assert await muse_service.effects_of(db_session, user.id) == {}  # misses her: no date yet
    row = MuseDate(user_id=user.id, date_day=local_today(), game="memory", completed_at=datetime.now(timezone.utc))
    db_session.add(row)
    await db_session.commit()
    assert await muse_service.effects_of(db_session, user.id) == {"attack": 3}
    row.completed_at = datetime.now(timezone.utc) - timedelta(hours=40)
    await db_session.commit()
    assert await muse_service.effects_of(db_session, user.id) == {}
