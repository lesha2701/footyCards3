"""«Клубная база» (services/club_base_service.py): the HQ gate, timed
upgrades for coins, one construction queue with the «Академия», the
accounting discount, sponsor/merchandise income, Stars speed-up, the bot
sweep, the stadium look, capped effects, the leaderboard — and the career
effects frozen per season (matchday income, injuries, recovery,
familiarity, reputation)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import func, select

import app.core.rate_limit as rate_limit_module
from app.models.card import UserCard
from app.models.card_path import UserAcademy
from app.models.career import CareerParticipant, CareerSeason
from app.models.club_base import ClubBaseLedger, UserClubBase
from app.models.enums import CardSource, NotificationType, Position, TransactionType
from app.models.game_config import DEFAULT_CLUB_BASE_BUILDINGS, GameConfig
from app.models.notification import Notification
from app.models.transaction import CoinTransaction
from app.services import career_service, career_tactics_service, club_base_service
from app.services.club_formation_service import get_formation_slots
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1"
_serial = {"n": 780000}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _config(db_session, **overrides) -> GameConfig:
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
    for key, value in overrides.items():
        setattr(config, key, value)
    await db_session.commit()
    return config


async def _login(client, db_session, bot_token, telegram_id, balance=200_000):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post(f"{API}/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, telegram_id)
    user.balance = balance
    await db_session.commit()
    return headers, user


async def _base(db_session, user_id) -> UserClubBase:
    return (await db_session.execute(
        select(UserClubBase).where(UserClubBase.user_id == user_id).execution_options(populate_existing=True)
    )).scalar_one()


async def _finish_now(db_session, user_id):
    base = await _base(db_session, user_id)
    base.build_ends_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()


async def _set_levels(db_session, user_id, levels: dict, **fields):
    base = await db_session.get(UserClubBase, user_id)
    if base is None:
        base = UserClubBase(user_id=user_id, appearance={}, income_accrued=0)
        db_session.add(base)
    base.levels, base.total_level = levels, sum(levels.values())
    for key, value in fields.items():
        setattr(base, key, value)
    await db_session.commit()


def _building(state, code):
    return next(b for b in state["buildings"] if b["code"] == code)


async def test_hq_first_then_timer_idempotency_and_lazy_completion(client, db_session, bot_token):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 970101, balance=10_000)
    gated = await client.post(f"{API}/club-base/buildings/training/upgrade", headers=headers, json={})
    assert gated.status_code == 409 and "штаб" in gated.json()["error"]["message"]

    resp = await client.post(f"{API}/club-base/buildings/hq/upgrade", headers=headers, json={"idempotency_key": "b1"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["construction"]["building_code"] == "hq" and body["construction"]["to_level"] == 1
    assert body["construction"]["speedup_stars"] == 4 and body["new_balance"] == 9_300  # 2 h × 2 Stars; 700 coins
    replay = await client.post(f"{API}/club-base/buildings/hq/upgrade", headers=headers, json={"idempotency_key": "b1"})
    assert replay.status_code == 200 and replay.json()["new_balance"] == 9_300
    busy = await client.post(f"{API}/club-base/buildings/hq/upgrade", headers=headers, json={})
    assert busy.status_code == 409  # one construction at a time

    await _finish_now(db_session, user.id)
    state = (await client.get(f"{API}/club-base", headers=headers)).json()
    assert _building(state, "hq")["level"] == 1 and state["construction"] is None and state["level"] == 1
    assert _building(state, "training")["cap_level"] == 1
    entries = (await db_session.execute(
        select(ClubBaseLedger.kind).where(ClubBaseLedger.user_id == user.id).order_by(ClubBaseLedger.id)
    )).scalars().all()
    assert entries == ["upgrade", "complete"]

    assert (await client.post(f"{API}/club-base/buildings/training/upgrade", headers=headers, json={})).status_code == 200
    await _finish_now(db_session, user.id)
    capped = await client.post(f"{API}/club-base/buildings/training/upgrade", headers=headers, json={})
    assert capped.status_code == 409 and "штаб" in capped.json()["error"]["message"]  # HQ 1 → others max 1


async def test_one_queue_with_the_academy(client, db_session, bot_token):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 970102)
    assert (await client.post(f"{API}/club-base/buildings/hq/upgrade", headers=headers, json={})).status_code == 200
    blocked = await client.post(f"{API}/academy/wings/scout/upgrade", headers=headers, json={})
    assert blocked.status_code == 409 and "Штаб-квартира" in blocked.json()["error"]["message"]

    await _finish_now(db_session, user.id)
    assert (await client.post(f"{API}/academy/wings/scout/upgrade", headers=headers, json={})).status_code == 200
    blocked = await client.post(f"{API}/club-base/buildings/stadium/upgrade", headers=headers, json={})
    assert blocked.status_code == 409 and "Академия" in blocked.json()["error"]["message"]
    state = (await client.get(f"{API}/club-base", headers=headers)).json()
    assert state["construction"]["owner"] == "academy" and state["academy_level"] == 0


async def test_accounting_discount_on_base_and_academy(client, db_session, bot_token):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 970103, balance=100_000)
    await _set_levels(db_session, user.id, {"hq": 25, "accounting": 25})  # −15%
    state = (await client.get(f"{API}/club-base", headers=headers)).json()
    assert _building(state, "stadium")["next_cost"] == 1_530 and _building(state, "stadium")["next_cost_full"] == 1_800
    resp = await client.post(f"{API}/club-base/buildings/stadium/upgrade", headers=headers, json={})
    assert resp.json()["new_balance"] == 100_000 - 1_530
    await _finish_now(db_session, user.id)
    academy = (await client.get(f"{API}/academy", headers=headers)).json()
    cost = next(w for w in academy["wings"] if w["code"] == "hall")["next_cost"]
    resp = await client.post(f"{API}/academy/wings/hall/upgrade", headers=headers, json={})
    assert resp.status_code == 200 and resp.json()["new_balance"] == 100_000 - 1_530 - cost
    config = await db_session.get(GameConfig, 1)
    assert cost == club_base_service.discounted(config.academy_buildings["hall"]["costs"][0], 15)


async def test_income_accrues_is_capped_and_claimed_once(client, db_session, bot_token):
    await _config(db_session, club_base_income_max_days=3)
    headers, user = await _login(client, db_session, bot_token, 970104, balance=0)
    now = datetime.now(timezone.utc)
    await _set_levels(db_session, user.id, {"hq": 1, "marketing": 1, "shop": 1},
                      income_since=now - timedelta(days=2, minutes=1))
    state = (await client.get(f"{API}/club-base", headers=headers)).json()
    assert state["income"]["daily"] == 35 and state["income"]["pending"] == 70 and state["income"]["cap"] == 105
    claim = await client.post(f"{API}/club-base/income/claim", headers=headers, json={"idempotency_key": "i1"})
    assert claim.status_code == 200, claim.text
    assert claim.json()["claimed"] == 70 and claim.json()["new_balance"] == 70
    again = await client.post(f"{API}/club-base/income/claim", headers=headers, json={"idempotency_key": "i1"})
    assert again.status_code == 200 and again.json()["new_balance"] == 70  # replay, not paid twice
    assert (await client.post(f"{API}/club-base/income/claim", headers=headers, json={})).status_code == 409

    base = await _base(db_session, user.id)
    base.income_since = now - timedelta(days=10)
    await db_session.commit()
    claim = await client.post(f"{API}/club-base/income/claim", headers=headers, json={})
    assert claim.json()["claimed"] == 105  # three days at most
    tx = (await db_session.execute(select(func.count(CoinTransaction.id)).where(
        CoinTransaction.user_id == user.id, CoinTransaction.type == TransactionType.club_base_income,
    ))).scalar_one()
    assert tx == 2


def test_income_settles_at_the_old_rate_when_a_building_finishes():
    config = NS(club_base_enabled=True, club_base_buildings=DEFAULT_CLUB_BASE_BUILDINGS, club_base_caps={},
                club_base_income_max_days=3)
    start = datetime.now(timezone.utc) - timedelta(days=2)
    base = UserClubBase(user_id=1, levels={"hq": 2, "marketing": 1}, income_accrued=0, income_since=start,
                        building_code="marketing", building_to_level=2, build_started_at=start,
                        build_ends_at=start + timedelta(days=1))
    club_base_service._finish(base, config)
    assert base.levels["marketing"] == 2 and base.income_accrued == 20  # one day at level 1
    assert club_base_service.pending_income(base, 32, config, datetime.now(timezone.utc)) == 20 + 32


def test_effects_sum_and_are_capped():
    config = NS(club_base_enabled=True, club_base_caps={"injury_pct": 50, "daily": 100},
                club_base_buildings={**DEFAULT_CLUB_BASE_BUILDINGS,
                                     "medical": {"costs": [1], "hours": [1], "injury_pct": [90], "recovery": [3]}})
    fx = club_base_service.effects_from_levels({"medical": 1, "marketing": 25, "shop": 25, "hotel": 25}, config)
    assert fx["injury_pct"] == 50 and fx["recovery"] == 3
    assert fx["daily"] == 100  # 300 + 210 clamped
    assert fx["matchday_pct"] == 80  # hotel 55 + tickets 25
    assert "cap" not in fx and "capacity" not in fx
    config.club_base_enabled = False
    assert club_base_service.effects_from_levels({"medical": 1}, config) == {}


def test_career_effect_helpers():
    fx = {"matchday": 110, "matchday_pct": 75, "injury_pct": 40, "familiarity_pct": 50, "prep_pct": 20, "rep_pct": 25}
    assert club_base_service.matchday_income(fx) == 192
    assert club_base_service.injury_chance(3, fx) == pytest.approx(1.8)
    assert club_base_service.prep_boost(1.25, fx) == pytest.approx(1.30)
    assert club_base_service.prep_boost(1.0, fx) == 1.0
    assert club_base_service.reputation_gain(20, fx) == 25 and club_base_service.reputation_gain(-10, fx) == -10
    cfg = NS(career_familiarity_step_tenths=20, career_familiarity_max_tenths=90)
    assert career_tactics_service.familiarity_after_match(0, cfg) == 20
    assert career_tactics_service.familiarity_after_match(0, cfg, bonus_pct=50) == 30
    assert career_tactics_service.familiarity_after_match(80, cfg, bonus_pct=50) == 90


def test_medical_centre_in_after_match():
    cfg = NS(career_fatigue_per_match=35, career_fatigue_recovery=40, career_injury_chance_pct=100,
             career_yellow_chance_pct=0, career_red_chance_pct=0, career_yellows_for_ban=3, career_form_max=2)

    class Rng:
        def random(self):
            return 0.6

        def randint(self, a, b):
            return a

    part = CareerParticipant(squad_card_ids=[1, 2], condition={"2": {"fatigue": 60}})
    report = career_service._after_match(part, {1}, 1, 0, 0, cfg, Rng(), {1: "A", 2: "B"},
                                         base_fx={"injury_pct": 50, "recovery": 10})
    assert report["injured"] == []  # 60 ≥ 100 × 50%
    assert career_service._condition(part, 2)["fatigue"] == 10  # 60 − (40 + 10)
    part = CareerParticipant(squad_card_ids=[1], condition={})
    assert career_service._after_match(part, {1}, 1, 0, 0, cfg, Rng(), {1: "A"})["injured"] == ["A"]


async def test_stars_speedup_finishes_a_base_construction(client, db_session, bot_token, monkeypatch):
    from app.services import stars_payment_service

    async def fake_link(*args, **kwargs):
        return "https://t.me/invoice/x"

    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", fake_link)
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 970105)
    await _set_levels(db_session, user.id, {"hq": 2})
    await client.post(f"{API}/club-base/buildings/stadium/upgrade", headers=headers, json={})
    inv = await client.post(f"{API}/club-base/speedup-invoice", headers=headers)
    assert inv.status_code == 200, inv.text
    token, stars = inv.json()["payload_token"], inv.json()["stars_amount"]
    assert stars == 12  # 6 h × 2 Stars
    ok, _ = await stars_payment_service.validate_pre_checkout(db_session, token, stars)
    assert ok
    await stars_payment_service.deliver_payment(db_session, token, user.telegram_id, "ch-base-1", stars)
    base = await _base(db_session, user.id)
    assert base.levels == {"hq": 2, "stadium": 1} and base.building_code is None
    status = await client.get(f"{API}/club-base/stars-invoices/{token}", headers=headers)
    assert status.json()["path_result"]["kind"] == "base_speedup"
    # A repeat delivery is a no-op.
    await stars_payment_service.deliver_payment(db_session, token, user.telegram_id, "ch-base-1", stars)
    speedups = (await db_session.execute(select(func.count(ClubBaseLedger.id)).where(
        ClubBaseLedger.user_id == user.id, ClubBaseLedger.kind == "speedup",
    ))).scalar_one()
    assert speedups == 1


async def test_sweep_completes_and_notifies_once(client, db_session, bot_token):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 970106)
    await client.post(f"{API}/club-base/buildings/hq/upgrade", headers=headers, json={})
    assert await club_base_service.sweep_due(db_session) == 0  # not due yet
    await _finish_now(db_session, user.id)
    assert await club_base_service.sweep_due(db_session) == 1
    assert await club_base_service.sweep_due(db_session) == 0
    notes = (await db_session.execute(select(Notification).where(
        Notification.user_id == user.id, Notification.type == NotificationType.club_base_built,
    ))).scalars().all()
    assert len(notes) == 1 and "Штаб-квартира" in notes[0].body
    assert (await _base(db_session, user.id)).levels == {"hq": 1}


async def test_stadium_look_is_unlocked_by_level(client, db_session, bot_token):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 970107)
    assert (await client.put(f"{API}/club-base/stadium/look", headers=headers, json={"seats": "blue"})).status_code == 409
    await _set_levels(db_session, user.id, {"hq": 12, "stadium": 12})
    ok = await client.put(f"{API}/club-base/stadium/look", headers=headers,
                          json={"seats": "blue", "roof": "canopy", "lights": True})
    assert ok.status_code == 200, ok.text
    assert ok.json()["stadium"]["look"] == {"seats": "blue", "roof": "canopy", "lights": True, "screen": False}
    for bad in ({"roof": "full"}, {"screen": True}, {"seats": "gold"}):
        assert (await client.put(f"{API}/club-base/stadium/look", headers=headers, json=bad)).status_code in (409, 422)


async def test_leaderboard_counts_base_and_academy(client, db_session, bot_token):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 970108)
    await _set_levels(db_session, user.id, {"hq": 3, "stadium": 2})
    db_session.add(UserAcademy(user_id=user.id, levels={"scout": 4}, total_level=4))
    await db_session.commit()
    resp = await client.get(f"{API}/leaderboard/ranking", headers=headers, params={"metric": "base_level"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["me"]["value"] == 9


async def test_quick_sell_and_training_get_the_base_bonus(client, db_session, bot_token):
    from app.services import collection_service

    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 970109, balance=0)
    await _set_levels(db_session, user.id, {"hq": 25, "shop": 25})  # +10%
    player = await create_player(db_session, rating=60, position=Position.ST)
    player.quick_sell_price = 100
    _serial["n"] += 1
    card = UserCard(owner_id=user.id, player_id=player.id, source=CardSource.seed, serial_number=_serial["n"])
    _serial["n"] += 1
    spare = UserCard(owner_id=user.id, player_id=player.id, source=CardSource.seed, serial_number=_serial["n"])
    db_session.add_all([card, spare])
    await db_session.commit()
    result = await collection_service.sell_cards(db_session, user, [card.id], confirm_last_copy=True)
    assert result["coins_earned"] == 110


# --- career: the base effects are frozen per season ----------------------------------------------

async def _career_player(client, db_session, bot_token, tg_id):
    await client.post(f"{API}/auth/session", headers=telegram_headers(tg_id, bot_token))
    user = await get_user_by_telegram_id(db_session, tg_id)
    positions = [s.ideal_position for s in get_formation_slots("4-3-3")]
    positions += [Position.GK, Position.CB, Position.CM, Position.ST, Position.RW]
    for pos in positions:
        player = await create_player(db_session, rating=75, position=pos)
        _serial["n"] += 1
        db_session.add(UserCard(owner_id=user.id, player_id=player.id, source=CardSource.seed, serial_number=_serial["n"]))
    await db_session.commit()
    return user.id, telegram_headers(tg_id, bot_token)


async def _matchday_total(db_session, user_id) -> tuple[int, int]:
    rows = (await db_session.execute(select(CoinTransaction.amount).where(
        CoinTransaction.user_id == user_id, CoinTransaction.type == TransactionType.club_base_matchday,
    ))).scalars().all()
    return len(rows), sum(rows)


async def test_stadium_pays_every_home_match_with_effects_frozen_at_the_start(client, db_session, bot_token):
    await _config(db_session)
    user_id, headers = await _career_player(client, db_session, bot_token, 970201)
    await _set_levels(db_session, user_id, {"hq": 25, "stadium": 25, "hotel": 25, "marketing": 25})
    resp = await client.post(f"{API}/career/seasons", headers=headers, json={"difficulty": "amateur"})
    assert resp.status_code == 200, resp.text
    season_id = resp.json()["season"]["id"]
    first = datetime.fromisoformat(resp.json()["season"]["schedule"][0])
    await career_service.resolve_due(db_session, season_id, now=first + timedelta(minutes=30))
    # The base changes after the first round: this season keeps its effects.
    await _set_levels(db_session, user_id, {"hq": 25})
    later = datetime.now(timezone.utc) + timedelta(days=8)
    await career_service.resolve_due(db_session, season_id, now=later)

    db_session.expire_all()
    part = (await db_session.execute(select(CareerParticipant).where(CareerParticipant.season_id == season_id))).scalar_one()
    assert part.base_effects["matchday"] == 150 and part.base_effects["matchday_pct"] == 80
    count, total = await _matchday_total(db_session, user_id)
    assert count == 7 and total == 7 * 270  # 7 home league matches × 150 × 1.8
    season = await db_session.get(CareerSeason, season_id)
    assert season.status == "finished"


async def test_a_season_started_before_the_base_gets_nothing(client, db_session, bot_token):
    await _config(db_session)
    user_id, headers = await _career_player(client, db_session, bot_token, 970202)
    resp = await client.post(f"{API}/career/seasons", headers=headers, json={"difficulty": "amateur"})
    season_id = resp.json()["season"]["id"]
    part = (await db_session.execute(select(CareerParticipant).where(CareerParticipant.season_id == season_id))).scalar_one()
    part.base_effects = {}  # what migration 0179 writes for seasons already under way
    await db_session.commit()
    await _set_levels(db_session, user_id, {"hq": 25, "stadium": 25})
    await career_service.resolve_due(db_session, season_id, now=datetime.now(timezone.utc) + timedelta(days=8))
    assert await _matchday_total(db_session, user_id) == (0, 0)


# --- admin --------------------------------------------------------------------------------------

async def _admin(client, bot_token) -> dict:
    session = await client.post(f"{API}/auth/session", headers=telegram_headers(999000001, bot_token))
    return {"Authorization": f"Bearer {session.json()['admin_token']}"}


async def test_admin_settings_are_validated_and_logged(client, db_session, bot_token):
    await _config(db_session)
    auth = await _admin(client, bot_token)
    bad = {"club_base_buildings": {"hotel": {"costs": [100, 200], "hours": [1], "matchday_pct": [5, 10]}}}
    resp = await client.put(f"{API}/admin/games/config", headers=auth, json=bad)
    assert resp.status_code == 409 and "Клубная база" in resp.json()["error"]["message"]
    unknown = {"club_base_buildings": {"hotel": {"costs": [100], "hours": [1], "daily": [5]}}}
    assert (await client.put(f"{API}/admin/games/config", headers=auth, json=unknown)).status_code == 409
    good = {"club_base_buildings": {**DEFAULT_CLUB_BASE_BUILDINGS, "hotel": {"costs": [100, 200], "hours": [0, 1],
                                                                          "matchday_pct": [7, 9]}},
            "club_base_stars_per_hour": 3}
    resp = await client.put(f"{API}/admin/games/config", headers=auth, json=good)
    assert resp.status_code == 200, resp.text
    assert resp.json()["club_base_buildings"]["hotel"]["matchday_pct"] == [7, 9]
    assert resp.json()["club_base_stars_per_hour"] == 3


async def test_admin_art_upload_and_journal(client, db_session, bot_token, monkeypatch, tmp_path):
    from app.services import image_service

    monkeypatch.setattr(image_service, "CLUB_BASE_DIR", tmp_path)
    monkeypatch.setattr(image_service, "STATIC_DIR", tmp_path.parent)
    await _config(db_session)
    auth = await _admin(client, bot_token)
    png = ("art.png", b"\x89PNG\r\n\x1a\nfake-bytes", "image/png")
    resp = await client.post(f"{API}/admin/club-base/art/stadium", headers=auth, files={"file": png})
    assert resp.status_code == 200, resp.text
    path = resp.json()["art"]["buildings"]["stadium"]
    assert path.startswith("club_base/uploads/")
    assert (await client.post(f"{API}/admin/club-base/art/nowhere", headers=auth, files={"file": png})).status_code == 404

    headers, user = await _login(client, db_session, bot_token, 970110)
    state = (await client.get(f"{API}/club-base", headers=headers)).json()
    assert state["art"]["buildings"]["stadium"] == path and state["art"]["background"] is None
    resp = await client.delete(f"{API}/admin/club-base/art/stadium", headers=auth)
    assert resp.status_code == 200 and "stadium" not in resp.json()["art"]["buildings"]

    await client.post(f"{API}/club-base/buildings/hq/upgrade", headers=headers, json={})
    ledger = (await client.get(f"{API}/admin/club-base/ledger", headers=auth, params={"user_id": user.id})).json()
    assert [e["kind"] for e in ledger] == ["upgrade"] and ledger[0]["building_name"] == "Штаб-квартира"
    assert (await client.get(f"{API}/admin/club-base/ledger", headers=headers)).status_code in (401, 403)
