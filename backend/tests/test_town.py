"""«Город» (services/town_service.py): houses bought for coins (each owned
house makes the next one dearer), the daily rent capped at
town_income_max_hours, idempotent purchases and claims, the admin switch
and the district settings validation; opening and renaming for Stars and
the hotel that pays for the cards held."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

import app.core.rate_limit as rate_limit_module
from app.models.enums import CardSource, Rarity, TransactionType
from app.models.game_config import DEFAULT_TOWN_DISTRICTS, GameConfig
from app.models.card_offer import CardOffer
from app.models.town import TownResident, UserTown, UserTownHouse, UserTownResident
from app.models.transaction import CoinTransaction
from app.services import town_service
from app.services.card_creation import create_user_card
from tests.factories import create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1"

FRONTEND_CODES = {
    # Kept in step with frontend/src/lib/town.ts (the drawn tap zones).
    "center": 12, "favela": 12, "beach": 12, "mountains": 12, "business": 12,
}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _config(db_session, **overrides) -> GameConfig:
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
    overrides.setdefault("town_unlock_coins", 0)  # open for everyone unless a test sells it
    for key, value in overrides.items():
        setattr(config, key, value)
    await db_session.commit()
    return config


async def _login(client, db_session, bot_token, telegram_id, balance=100_000):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post(f"{API}/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, telegram_id)
    user.balance = balance
    await db_session.commit()
    return headers, user


async def _town(db_session, user_id) -> UserTown:
    return (await db_session.execute(
        select(UserTown).where(UserTown.user_id == user_id).execution_options(populate_existing=True)
    )).scalar_one()


def test_catalog_matches_the_drawn_districts():
    assert {k: len(v) for k, v in town_service.HOUSES.items()} == FRONTEND_CODES
    assert set(town_service.DISTRICT_NAMES) == set(town_service.HOUSES) == set(DEFAULT_TOWN_DISTRICTS)


async def test_buying_houses_gets_dearer_and_never_charges_twice(client, db_session, bot_token):
    await _config(db_session, town_price_growth_pct=10,
                  town_districts={"favela": {"price": 1000, "rent": 20}})
    headers, user = await _login(client, db_session, bot_token, 990101, balance=5000)

    state = (await client.get(f"{API}/town", headers=headers)).json()
    favela = next(d for d in state["districts"] if d["code"] == "favela")
    assert state["enabled"] and state["owned_total"] == 0 and state["total_houses"] == 60
    assert favela["next_price"] == 1000 and favela["rent"] == 20

    first = await client.post(f"{API}/town/houses/favela/church/buy", headers=headers, json={"idempotency_key": "h1"})
    assert first.status_code == 200, first.text
    assert first.json()["new_balance"] == 4000 and first.json()["owned_total"] == 1
    replay = await client.post(f"{API}/town/houses/favela/church/buy", headers=headers, json={"idempotency_key": "h1"})
    assert replay.status_code == 200 and replay.json()["new_balance"] == 4000
    again = await client.post(f"{API}/town/houses/favela/church/buy", headers=headers, json={})
    assert again.status_code == 409

    second = (await client.post(f"{API}/town/houses/favela/samba/buy", headers=headers, json={})).json()
    assert second["new_balance"] == 4000 - 1100  # +10% for the one house already owned
    assert second["income"]["rate_per_day"] == 40
    assert {"district": "favela", "code": "samba"} in second["houses"]

    assert (await client.post(f"{API}/town/houses/favela/nowhere/buy", headers=headers, json={})).status_code == 404
    assert (await client.post(f"{API}/town/houses/moon/church/buy", headers=headers, json={})).status_code == 404
    spent = (await db_session.execute(select(func.count(CoinTransaction.id)).where(
        CoinTransaction.user_id == user.id, CoinTransaction.type == TransactionType.town_house,
    ))).scalar_one()
    assert spent == 2


async def test_not_enough_coins_buys_nothing(client, db_session, bot_token):
    await _config(db_session, town_districts={"business": {"price": 6000, "rent": 60}})
    headers, user = await _login(client, db_session, bot_token, 990102, balance=100)
    res = await client.post(f"{API}/town/houses/business/twist/buy", headers=headers, json={})
    assert res.status_code == 400 and res.json()["error"]["code"] == "insufficient_balance"
    count = (await db_session.execute(select(func.count(UserTownHouse.id)).where(UserTownHouse.user_id == user.id))).scalar_one()
    assert count == 0


async def test_rent_accrues_is_capped_and_collected_once(client, db_session, bot_token):
    await _config(db_session, town_income_max_hours=24, town_price_growth_pct=0,
                  town_districts={"beach": {"price": 100, "rent": 48}})
    headers, user = await _login(client, db_session, bot_token, 990103, balance=1000)
    assert (await client.post(f"{API}/town/houses/beach/lighthouse/buy", headers=headers, json={})).status_code == 200
    assert (await client.post(f"{API}/town/income/claim", headers=headers, json={})).status_code == 409

    town = await _town(db_session, user.id)
    town.income_since = datetime.now(timezone.utc) - timedelta(hours=12, minutes=1)
    await db_session.commit()
    state = (await client.get(f"{API}/town", headers=headers)).json()
    assert state["income"] == {"rate_per_day": 48, "pending": 24, "cap": 48, "max_hours": 24}
    claim = await client.post(f"{API}/town/income/claim", headers=headers, json={"idempotency_key": "r1"})
    assert claim.status_code == 200, claim.text
    assert claim.json()["claimed"] == 24 and claim.json()["new_balance"] == 900 + 24
    replay = await client.post(f"{API}/town/income/claim", headers=headers, json={"idempotency_key": "r1"})
    assert replay.json()["claimed"] == 0 and replay.json()["new_balance"] == 924

    town = await _town(db_session, user.id)
    town.income_since = datetime.now(timezone.utc) - timedelta(days=5)
    await db_session.commit()
    claim = (await client.post(f"{API}/town/income/claim", headers=headers, json={})).json()
    assert claim["claimed"] == 48  # one day at most


async def test_a_new_house_pays_from_the_moment_it_is_bought(client, db_session, bot_token):
    await _config(db_session, town_income_max_hours=48, town_price_growth_pct=0,
                  town_districts={"center": {"price": 100, "rent": 24}})
    headers, user = await _login(client, db_session, bot_token, 990104, balance=1000)
    await client.post(f"{API}/town/houses/center/bank/buy", headers=headers, json={})
    town = await _town(db_session, user.id)
    town.income_since = datetime.now(timezone.utc) - timedelta(days=1, minutes=1)
    await db_session.commit()
    await client.post(f"{API}/town/houses/center/cinema/buy", headers=headers, json={})
    town = await _town(db_session, user.id)
    assert town.income_accrued == 24  # the day before was paid at one house's rent
    state = (await client.get(f"{API}/town", headers=headers)).json()
    assert state["income"]["rate_per_day"] == 48 and state["income"]["pending"] == 24


async def test_closed_town_and_blocked_rewards(client, db_session, bot_token):
    await _config(db_session, town_enabled=False)
    headers, user = await _login(client, db_session, bot_token, 990105)
    assert (await client.get(f"{API}/town", headers=headers)).json()["enabled"] is False
    assert (await client.post(f"{API}/town/houses/favela/church/buy", headers=headers, json={})).status_code == 409

    await _config(db_session, town_enabled=True, town_price_growth_pct=0, town_districts={"favela": {"price": 0, "rent": 24}})
    user.game_rewards_blocked = True
    await db_session.commit()
    await client.post(f"{API}/town/houses/favela/church/buy", headers=headers, json={})
    town = await _town(db_session, user.id)
    town.income_since = datetime.now(timezone.utc) - timedelta(hours=13)
    await db_session.commit()
    claim = (await client.post(f"{API}/town/income/claim", headers=headers, json={})).json()
    assert claim["claimed"] == 0


def test_district_settings_validation():
    assert town_service.validate_districts({"beach": {"price": 10, "rent": 1}}) == {"beach": {"price": 10, "rent": 1}}
    for bad in ({"moon": {"price": 1, "rent": 1}}, {"beach": {"price": -1, "rent": 1}}, {"beach": {"price": "x"}}):
        with pytest.raises(ValueError):
            town_service.validate_districts(bad)



async def _fake_invoice_link(monkeypatch):
    from app.services import stars_payment_service

    async def fake_link(*args, **kwargs):
        return "https://t.me/invoice/x"

    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", fake_link)
    return stars_payment_service


async def test_town_opens_for_coins_once(client, db_session, bot_token):
    await _config(db_session, town_unlock_coins=5000)
    headers, user = await _login(client, db_session, bot_token, 990106, balance=6000)

    state = (await client.get(f"{API}/town", headers=headers)).json()
    assert state["unlocked"] is False and state["unlock_coins"] == 5000 and state["name"] is None
    assert (await client.post(f"{API}/town/houses/favela/church/buy", headers=headers, json={})).status_code == 409
    assert (await client.post(f"{API}/town/income/claim", headers=headers, json={})).status_code == 409

    opened = await client.post(f"{API}/town/unlock", headers=headers, json={"idempotency_key": "u1"})
    assert opened.status_code == 200, opened.text
    assert opened.json()["unlocked"] is True and opened.json()["new_balance"] == 1000
    replay = await client.post(f"{API}/town/unlock", headers=headers, json={"idempotency_key": "u1"})
    assert replay.json()["new_balance"] == 1000
    assert (await client.post(f"{API}/town/unlock", headers=headers, json={})).status_code == 409
    assert (await client.post(f"{API}/town/houses/favela/church/buy", headers=headers, json={})).status_code == 200
    spent = (await db_session.execute(select(func.count(CoinTransaction.id)).where(
        CoinTransaction.user_id == user.id, CoinTransaction.type == TransactionType.town_unlock,
    ))).scalar_one()
    assert spent == 1


async def test_unlock_needs_the_coins(client, db_session, bot_token):
    await _config(db_session, town_unlock_coins=5000)
    headers, _ = await _login(client, db_session, bot_token, 990108, balance=100)
    res = await client.post(f"{API}/town/unlock", headers=headers, json={})
    assert res.status_code == 400 and res.json()["error"]["code"] == "insufficient_balance"
    assert (await client.get(f"{API}/town", headers=headers)).json()["unlocked"] is False


async def test_town_is_renamed_for_stars(client, db_session, bot_token, monkeypatch):
    stars_payment_service = await _fake_invoice_link(monkeypatch)
    await _config(db_session, town_unlock_coins=10, town_rename_stars=50)
    headers, user = await _login(client, db_session, bot_token, 990109)
    assert (await client.post(f"{API}/town/rename-invoice", headers=headers, json={"name": "Рио"})).status_code == 409
    await client.post(f"{API}/town/unlock", headers=headers, json={})

    for bad in ("x", "https://spam.ru", "Город @evil", "a" * 25):
        assert (await client.post(f"{API}/town/rename-invoice", headers=headers, json={"name": bad})).status_code == 409
    first = (await client.post(f"{API}/town/rename-invoice", headers=headers, json={"name": "  Рио  де  Жанейро "})).json()
    second = (await client.post(f"{API}/town/rename-invoice", headers=headers, json={"name": "Порту"})).json()
    assert first["stars_amount"] == 50
    token = first["payload_token"]
    assert (await stars_payment_service.validate_pre_checkout(db_session, token, 50))[0]
    await stars_payment_service.deliver_payment(db_session, second["payload_token"], user.telegram_id, "ch-town-2", 50)
    await stars_payment_service.deliver_payment(db_session, token, user.telegram_id, "ch-town-3", 50)
    await stars_payment_service.deliver_payment(db_session, token, user.telegram_id, "ch-town-3", 50)
    assert (await client.get(f"{API}/town", headers=headers)).json()["name"] == "Рио де Жанейро"
    status = (await client.get(f"{API}/town/stars-invoices/{token}", headers=headers)).json()
    assert status["status"] == "completed" and status["path_result"]["kind"] == "town_rename"


async def _resident(db_session, **kw) -> TownResident:
    row = TownResident(**{"name": "Рыбак", "rarity": "common", **kw})
    db_session.add(row)
    await db_session.commit()
    return row


async def test_resident_pack_fills_the_town_and_pays_rent(client, db_session, bot_token):
    await _config(db_session, town_resident_rent=2, town_price_growth_pct=0, town_income_max_hours=48,
                  town_districts={"beach": {"price": 0, "rent": 100}})
    common = await _resident(db_session, name="Рыбак")
    captain = await _resident(db_session, name="Капитан", rarity="legendary", bonus="rent_pct", bonus_value=50)
    await _resident(db_session, name="Не выпадает", is_pack_droppable=False)
    pack = await create_pack(db_session, "residents-test", 100, 3, {Rarity.common: 1.0}, resident_drop_chance=1)
    headers, user = await _login(client, db_session, bot_token, 990110, balance=1000)

    listed = next(p for p in (await client.get(f"{API}/packs", headers=headers)).json() if p["id"] == pack.id)
    assert listed["expected_value"] is None  # the players' card value means nothing here
    opened = await client.post(f"{API}/packs/{pack.id}/open", headers=headers, json={})
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert body["cards"] == [] and len(body["muses"]) == 3
    assert {m["kind"] for m in body["muses"]} == {"resident"}
    assert {m["muse"]["name"] for m in body["muses"]} == {"Рыбак"}  # common slots: the only droppable common
    assert sorted(m["is_new"] for m in body["muses"]) == [False, False, True]
    assert body["muses"][0]["muse"]["effect_label"] == "+2 монет в день"

    state = (await client.get(f"{API}/town", headers=headers)).json()
    assert state["residents"]["population"] == 3 and state["income"]["rate_per_day"] == 6

    # A legendary resident adds his bonus once (two copies) — to the houses' rent.
    await town_service.grant(db_session, user.id, captain, "admin")
    await town_service.grant(db_session, user.id, captain, "admin")
    await db_session.commit()
    await client.post(f"{API}/town/houses/beach/surf/buy", headers=headers, json={})
    state = (await client.get(f"{API}/town", headers=headers)).json()
    assert state["residents"]["population"] == 5 and state["residents"]["rent_pct"] == 50
    assert state["income"]["rate_per_day"] == 150 + 10  # house 100 × 150% + 5 residents × 2

    album = (await client.get(f"{API}/town/residents", headers=headers)).json()
    assert album["population"] == 5 and album["owned_count"] == 2 and album["total_count"] == 3
    assert album["residents"][0]["name"] == "Капитан" and album["residents"][0]["bonus_label"] == "+50% к ренте домов"

    sold = await client.post(f"{API}/town/residents/{common.id}/sell-spare", headers=headers, json={"count": 2})
    assert sold.status_code == 200, sold.text
    assert sold.json()["sold_coins"] == 20 and sold.json()["population"] == 3
    assert (await client.post(f"{API}/town/residents/{common.id}/sell-spare", headers=headers, json={})).status_code == 409
    row = (await db_session.execute(select(UserTownResident).where(
        UserTownResident.user_id == user.id, UserTownResident.resident_id == common.id,
    ).execution_options(populate_existing=True))).scalar_one()
    assert row.copies == 1


async def test_resident_bonuses_are_capped_and_residents_switch_off(client, db_session, bot_token):
    await _config(db_session, town_resident_rent=1, town_resident_max_daily_coins=30, town_resident_bonus_max_pct=40,
                  town_hotel_price=0, town_hotel_rent_per_100_cards=100)
    headers, user = await _login(client, db_session, bot_token, 990111)
    for i, (bonus, value) in enumerate((("daily_coins", 25), ("daily_coins", 25), ("hotel_pct", 30), ("hotel_pct", 30))):
        resident = await _resident(db_session, name=f"Леген {i}", rarity="legendary", bonus=bonus, bonus_value=value)
        await town_service.grant(db_session, user.id, resident, "admin")
    await db_session.commit()
    player = await create_player(db_session)
    for _ in range(100):
        await create_user_card(db_session, user.id, player.id, CardSource.pack)
    await db_session.commit()
    await client.post(f"{API}/town/hotel/buy", headers=headers, json={})
    state = (await client.get(f"{API}/town", headers=headers)).json()
    assert state["residents"]["daily_coins"] == 30 and state["residents"]["hotel_pct"] == 40
    assert state["income"]["rate_per_day"] == 4 + 30 + 140  # residents, their coins, hotel 100 × 140%

    await _config(db_session, town_residents_enabled=False)
    assert (await client.get(f"{API}/town", headers=headers)).json()["income"]["rate_per_day"] == 100


async def test_a_resident_is_sold_in_the_shop(client, db_session, bot_token):
    from app.services import card_offer_service

    await _config(db_session)
    resident = await _resident(db_session, name="Бабушка Роза", rarity="legendary", bonus="daily_coins", bonus_value=20)
    db_session.add(CardOffer(resident_id=resident.id, stars_price=30))
    await db_session.commit()
    _, user = await _login(client, db_session, bot_token, 990112)
    offers = await card_offer_service.list_live(db_session, user)
    offer = next(o for o in offers if o.kind == "resident")
    assert offer.item.name == "Бабушка Роза" and offer.item.effects == ["Житель города", "+20 монет в день"]


def test_spare_coins_validation():
    assert town_service.validate_spare_coins({"rare": 5}) == {"rare": 5}
    for bad in ({"diamond": 1}, {"rare": -1}, {"rare": "x"}):
        with pytest.raises(ValueError):
            town_service.validate_spare_coins(bad)


async def test_hotel_pays_for_the_cards_held(client, db_session, bot_token):
    await _config(db_session, town_hotel_price=500, town_hotel_rent_per_100_cards=48, town_hotel_max_cards=4,
                  town_income_max_hours=24)
    headers, user = await _login(client, db_session, bot_token, 990107, balance=1000)
    player = await create_player(db_session)
    cards = [await create_user_card(db_session, user.id, player.id, CardSource.pack) for _ in range(6)]
    await db_session.commit()

    state = (await client.get(f"{API}/town", headers=headers)).json()
    assert state["hotel"] == {"owned": False, "price": 500, "cards": 6, "max_cards": 4,
                              "rent_per_100_cards": 48, "rent": 1}  # 4 counted × 48 / 100
    bought = await client.post(f"{API}/town/hotel/buy", headers=headers, json={"idempotency_key": "ho1"})
    assert bought.status_code == 200, bought.text
    assert bought.json()["new_balance"] == 500 and bought.json()["hotel"]["owned"] is True
    assert bought.json()["income"]["rate_per_day"] == 1
    assert (await client.post(f"{API}/town/hotel/buy", headers=headers, json={"idempotency_key": "ho1"})).json()["new_balance"] == 500
    assert (await client.post(f"{API}/town/hotel/buy", headers=headers, json={})).status_code == 409

    await _config(db_session, town_hotel_rent_per_100_cards=2400, town_hotel_max_cards=1000)
    assert (await client.get(f"{API}/town", headers=headers)).json()["income"]["rate_per_day"] == 144  # 6 × 24
    for card in cards[:4]:
        await db_session.delete(card)  # sold: the hotel has fewer guests
    await db_session.commit()
    state = (await client.get(f"{API}/town", headers=headers)).json()
    assert state["hotel"]["cards"] == 2 and state["income"]["rate_per_day"] == 48


async def test_a_closed_place_opens_once_and_adds_to_the_houses_rent(client, db_session, bot_token):
    await _config(db_session, town_price_growth_pct=0, town_districts={"beach": {"price": 0, "rent": 100}},
                  town_decor={"pier": {"price": 3000, "rent_pct": 10}})
    headers, user = await _login(client, db_session, bot_token, 990120, balance=5000)
    await client.post(f"{API}/town/houses/beach/surf/buy", headers=headers, json={})
    state = (await client.get(f"{API}/town", headers=headers)).json()
    pier = next(d for d in state["decor"] if d["code"] == "pier")
    assert pier == {"code": "pier", "name": "Пирс с колесом обозрения", "price": 3000, "rent_pct": 10, "owned": False}
    assert {d["code"] for d in state["decor"]} == set(town_service.DECOR)

    bought = await client.post(f"{API}/town/decor/pier/buy", headers=headers, json={"idempotency_key": "d1"})
    assert bought.status_code == 200, bought.text
    body = bought.json()
    assert body["new_balance"] == 2000 and body["decor_pct"] == 10
    assert body["income"]["rate_per_day"] == 110
    assert next(d for d in body["districts"] if d["code"] == "beach")["rent"] == 110
    # A place is not a house: the count and the next house's price stay.
    assert body["owned_total"] == 1 and len(body["houses"]) == 1
    assert (await client.post(f"{API}/town/decor/pier/buy", headers=headers, json={"idempotency_key": "d1"})).json()["new_balance"] == 2000
    assert (await client.post(f"{API}/town/decor/pier/buy", headers=headers, json={})).status_code == 409
    assert (await client.post(f"{API}/town/decor/moon/buy", headers=headers, json={})).status_code == 404
    res = await client.post(f"{API}/town/decor/island/buy", headers=headers, json={})
    assert res.status_code == 400 and res.json()["error"]["code"] == "insufficient_balance"


async def test_a_closed_place_needs_an_opened_town(client, db_session, bot_token):
    await _config(db_session, town_unlock_coins=100)
    headers, _ = await _login(client, db_session, bot_token, 990121)
    assert (await client.post(f"{API}/town/decor/park/buy", headers=headers, json={})).status_code == 409


def test_decor_settings_validation():
    assert town_service.validate_decor({"park": {"price": 5, "rent_pct": 2}}) == {"park": {"price": 5, "rent_pct": 2}}
    for bad in ({"moon": {"price": 1}}, {"park": {"price": -1}}, {"park": 3}):
        with pytest.raises(ValueError):
            town_service.validate_decor(bad)


def test_seeded_residents_have_pictures_and_valid_bonuses():
    """Migration 0267 seeds the first residents: every one has its picture in
    static/, a known rarity and bonus, and the bonuses sit on the legendary ones."""
    import importlib.util
    from pathlib import Path

    from app.services import town_service

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("m0267", root / "alembic" / "versions" / "0267_town.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    slugs = [r[0] for r in module.RESIDENTS]
    assert len(slugs) == len(set(slugs)) >= 40
    for slug, name, title, description, icon, rarity, bonus, value in module.RESIDENTS:
        assert (root / "static" / "residents" / "town" / f"{slug}.webp").is_file(), slug
        assert rarity in town_service.RARITIES and bonus in town_service.RESIDENT_BONUSES
        assert len(name) <= 64 and len(title) <= 64 and len(description) <= 255 and len(icon) <= 16
        assert (bonus != "none") == (rarity == "legendary") and (value > 0) == (bonus != "none")
    assert {r[5] for r in module.RESIDENTS} == set(town_service.RARITIES)
    assert {o[0] for o in module.RESIDENT_OFFERS} <= set(slugs)


async def test_sport_and_build_bonuses_work_outside_the_town(client, db_session, bot_token):
    """xp_pct → «Мой игрок» XP, game_attempts → every mini-game's rewarded
    attempts, build_pct → the build time of «Клубная база» (and «Академия»)."""
    from app.services import my_player_service
    from app.services.club_pass_service import extra_rewarded_attempts

    config = await _config(db_session, town_resident_bonus_max_pct=100)
    headers, user = await _login(client, db_session, bot_token, 990130)
    hq_hours = (await client.get(f"{API}/club-base", headers=headers)).json()["buildings"][0]
    assert hq_hours["code"] == "hq"
    for i, (bonus, value) in enumerate((("xp_pct", 10), ("game_attempts", 2), ("build_pct", 25))):
        resident = await _resident(db_session, name=f"Спорт {i}", rarity="legendary", bonus=bonus, bonus_value=value)
        await town_service.grant(db_session, user.id, resident, "admin")
    await db_session.commit()

    assert await extra_rewarded_attempts(db_session, user.id, config) == 2
    assert await my_player_service.xp_bonus_pct(db_session, user.id) == 10
    state = (await client.get(f"{API}/club-base", headers=headers)).json()
    assert state["buildings"][0]["next_hours"] == hq_hours["next_hours"] * 0.75
    started = await client.post(f"{API}/club-base/buildings/hq/upgrade", headers=headers, json={})
    assert started.status_code == 200, started.text
    remaining = started.json()["construction"]["remaining_seconds"]
    assert abs(remaining - hq_hours["next_hours"] * 3600 * 0.75) < 60

    await _config(db_session, town_residents_enabled=False)
    assert await extra_rewarded_attempts(db_session, user.id, config) == 0
    assert await my_player_service.xp_bonus_pct(db_session, user.id) == 0


def test_build_hours_never_go_below_a_tenth():
    assert town_service.build_hours(2, 25) == 1.5
    assert town_service.build_hours(0, 50) == 0 and town_service.build_hours(3, 0) == 3
    config = GameConfig(id=1, town_resident_bonus_max_pct=100, town_resident_rent=1, town_resident_max_daily_coins=0)
    row = UserTownResident(copies=1)
    row.resident = TownResident(name="x", rarity="legendary", bonus="build_pct", bonus_value=200, is_active=True)
    assert town_service.resident_effects(config, [row])["build_pct"] == 90
