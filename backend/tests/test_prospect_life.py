"""«Воспитанник Академии» — life around the child (prospect_life): talents,
graduation and the dynasty, the hall, «Турнир набора», friends' duels in
«Ответка», gifts and the birthday box, seasonal cosmetics, the bot digest,
the graduate in «Менеджер» and his own wage cap."""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.core.timeutil import app_timezone, local_today
from app.models.academy_prospect import AcademyProspect, ProspectDuel, ProspectLedger
from app.models.career import Friendship
from app.models.enums import NotificationType
from app.models.manager_club import ManagerContract
from app.models.notification import Notification
from app.models.user import User
from app.services import manager_service, prospect_life
from app.services import prospect_service as ps
from app.services import stars_payment_service
from tests.factories import get_user_by_telegram_id
from tests.test_otvetka import _play, _rig
from tests.utils import telegram_headers

API = "/api/v1"
C = ps.cfg(SimpleNamespace(prospect={}))
NEW = {"name": "Лёва Мяч", "number": 7, "position": "ST", "foot": "left", "appearance": {}}
pytestmark = pytest.mark.usefixtures("trade_guards_off")


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    rate_limit_module._hits.clear()
    yield
    rate_limit_module._hits.clear()


@pytest.fixture(autouse=True)
def _no_season_at_the_real_clock(monkeypatch):
    real = manager_service.ensure_season

    async def ensure(db, now=None):
        if now is None or abs(now - datetime.now(timezone.utc)) < timedelta(hours=1):
            return False
        return await real(db, now)

    monkeypatch.setattr(manager_service, "ensure_season", ensure)


@pytest.fixture
def fake_invoice_link(monkeypatch):
    async def fake_link(*_a, **_k):
        return "https://t.me/invoice/x"

    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", fake_link)


async def _user(client, db_session, tg_id: int, bot_token, balance: int = 50_000):
    headers = telegram_headers(tg_id, bot_token)
    assert (await client.post(f"{API}/auth/session", headers=headers)).status_code == 200
    user = await get_user_by_telegram_id(db_session, tg_id)
    user.balance = balance
    db_session.add(user)
    await db_session.commit()
    return user, headers


async def _create(client, db_session, tg_id: int, bot_token, **extra):
    user, headers = await _user(client, db_session, tg_id, bot_token, **extra)
    res = await client.post(f"{API}/prospect", json=NEW, headers=headers)
    assert res.status_code == 200, res.text
    return user, headers


async def _row(db_session, user_id: int, status: str = ps.GROWING) -> AcademyProspect:
    return (await db_session.execute(
        select(AcademyProspect).where(AcademyProspect.user_id == user_id, AcademyProspect.status == status)
        .execution_options(populate_existing=True)
    )).scalar_one()


async def _age(db_session, user_id: int, days: int, xp: int | None = None) -> AcademyProspect:
    p = await _row(db_session, user_id)
    p.created_at = datetime.now(timezone.utc) - timedelta(days=days)
    if xp is not None:
        p.xp = xp
    db_session.add(p)
    await db_session.commit()
    return p


async def _friends(db_session, a: int, b: int) -> None:
    db_session.add(Friendship(requester_id=a, addressee_id=b, user_low=min(a, b), user_high=max(a, b), status="accepted"))
    await db_session.commit()


async def _view(client, headers) -> dict:
    res = await client.get(f"{API}/prospect", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


# --- talents -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_talent_pick_at_each_stage(client, db_session, bot_token):
    user, headers = await _create(client, db_session, 881001, bot_token)
    assert (await _view(client, headers))["spec_pick"] is None
    await _age(db_session, user.id, 30, xp=20_000)  # «Детская школа»
    view = await _view(client, headers)
    options = [o["code"] for o in view["spec_pick"]["options"]]
    assert len(options) == 3 and len(set(options)) == 3
    before = view["prospect"]["atk_def"]
    assert (await client.post(f"{API}/prospect/spec", json={"code": "nope"}, headers=headers)).status_code == 409
    res = await client.post(f"{API}/prospect/spec", json={"code": options[0]}, headers=headers)
    assert res.status_code == 200, res.text
    after = res.json()
    assert [s["code"] for s in after["prospect"]["specs"]] == [options[0]]
    assert after["spec_pick"] is None  # the next one comes with «Юноши»
    effects = C["spec_effects"][options[0]]
    assert after["prospect"]["atk_def"] == [before[0] + effects.get("atk", 0), before[1] + effects.get("def", 0)]
    assert (await client.post(f"{API}/prospect/spec", json={"code": options[1]}, headers=headers)).status_code == 409


def test_talents_raise_their_xp_source():
    p = SimpleNamespace(specs=["finisher"])
    assert ps.with_spec(p, C, "goal_pct", 10) == 15
    assert ps.with_spec(p, C, "win_pct", 10) == 10


# --- graduation / dynasty / hall -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_graduation_freezes_the_rating_and_starts_a_dynasty(client, db_session, bot_token):
    user, headers = await _create(client, db_session, 881011, bot_token, balance=1000)
    assert (await client.post(f"{API}/prospect/graduate", headers=headers)).status_code == 409  # too young
    await _age(db_session, user.id, 100, xp=200_000)
    view = await _view(client, headers)
    assert view["graduation"]["available"]
    res = await client.post(f"{API}/prospect/graduate", headers=headers)
    assert res.status_code == 200, res.text
    after = res.json()
    assert after["prospect"] is None
    grad = after["graduate"]
    assert grad["rating"] == ps.peak_of((await _row(db_session, user.id, ps.GRADUATE)).potential, C)
    assert after["hall"]["mine"][0]["name"] == "Лёва Мяч" and after["hall"]["top"][0]["rating"] == grad["rating"]
    assert after["balance"] == 1000 + C["graduation_coins"]
    assert after["next_dynasty_peak"] == C["dynasty_peak_bonus"]
    # The next generation: «2-е поколение», + peak rating (not ★).
    second = await client.post(f"{API}/prospect", json={**NEW, "name": "Ваня Мяч"}, headers=headers)
    assert second.status_code == 200, second.text
    kid = await _row(db_session, user.id)
    assert kid.generation == 2
    assert second.json()["prospect"]["generation"] == 2
    assert second.json()["prospect"]["peak_bonus"]["dynasty"] == C["dynasty_peak_bonus"]
    # He graduates too: the first one retires to the hall.
    await _age(db_session, user.id, 100, xp=200_000)
    assert (await client.post(f"{API}/prospect/graduate", headers=headers)).status_code == 200
    statuses = sorted((r.name, r.status) for r in (await db_session.execute(
        select(AcademyProspect).where(AcademyProspect.user_id == user.id).execution_options(populate_existing=True)
    )).scalars())
    assert statuses == [("Ваня Мяч", ps.GRADUATE), ("Лёва Мяч", ps.RETIRED)]
    view = await _view(client, headers)
    assert [g["name"] for g in view["hall"]["mine"]] == ["Ваня Мяч", "Лёва Мяч"]


@pytest.mark.asyncio
async def test_the_graduate_plays_manager_and_keeps_the_prospect_contract(client, db_session, bot_token):
    from tests.test_manager import _accept_latest, _club, _player

    a_id, a_headers = await _player(client, db_session, bot_token, 881021)
    p_id, p_headers = await _player(client, db_session, bot_token, 881022)
    await _club(client, a_headers, "Совы")
    await client.post(f"{API}/prospect", json=NEW, headers=p_headers)
    await _age(db_session, p_id, 30, xp=20_000)
    await client.post(f"{API}/manager/market", headers=p_headers, json={"open": True, "subject": "prospect"})
    # His own (lower) wage cap.
    too_much = {"user_id": p_id, "subject": "prospect", "wage": C["manager_wage_max"] + 1, "seasons": 2}
    assert (await client.post(f"{API}/manager/offers", headers=a_headers, json=too_much)).status_code == 409
    ok = {"user_id": p_id, "subject": "prospect", "wage": C["manager_wage_max"], "seasons": 2}
    assert (await client.post(f"{API}/manager/offers", headers=a_headers, json=ok)).status_code == 200
    await _accept_latest(client, p_headers)
    await _age(db_session, p_id, 100, xp=200_000)
    assert (await client.post(f"{API}/prospect/graduate", headers=p_headers)).status_code == 200
    rows = (await db_session.execute(
        select(ManagerContract).where(ManagerContract.user_id == p_id).execution_options(populate_existing=True)
    )).scalars().all()
    assert [(r.subject, r.status) for r in rows] == [("graduate", "active")]
    mine = (await client.get(f"{API}/manager", headers=p_headers)).json()
    assert mine["graduate"]["contract"]["club_name"] == "Совы" and mine["prospect"] is None
    club = (await client.get(f"{API}/manager", headers=a_headers)).json()["club"]
    entry = next(p for p in [*club["squad"]["xi"], *club["squad"]["bench"]] if p.get("user_id") == p_id)
    assert entry["subject"] == "graduate" and entry["rating"] == mine["graduate"]["rating"]


@pytest.mark.asyncio
async def test_a_graduate_without_a_club_plays_for_his_owner(client, db_session, bot_token):
    from tests.test_manager import _club, _player

    a_id, a_headers = await _player(client, db_session, bot_token, 881031)
    await _club(client, a_headers, "Совы")
    await client.post(f"{API}/prospect", json=NEW, headers=a_headers)
    await _age(db_session, a_id, 100, xp=200_000)
    assert (await client.post(f"{API}/prospect/graduate", headers=a_headers)).status_code == 200
    club = (await client.get(f"{API}/manager", headers=a_headers)).json()["club"]
    kinds = {p["kind"] for p in [*club["squad"]["xi"], *club["squad"]["bench"]]}
    assert "graduate" in kinds and "prospect" not in kinds
    # On the market with «Ищу клуб».
    res = await client.post(f"{API}/manager/market", headers=a_headers, json={"open": True, "subject": "graduate"})
    assert res.status_code == 200 and res.json()["graduate"]["market_open"]


# --- «Турнир набора» -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_cohort_week_pays_its_top_once(client, db_session, bot_token):
    a, a_headers = await _create(client, db_session, 881041, bot_token, balance=0)
    b, b_headers = await _create(client, db_session, 881042, bot_token, balance=0)
    today = local_today()
    prev = ps.week_key(today - timedelta(days=7))
    start = datetime.now(timezone.utc) - timedelta(days=14)
    for uid, xp in ((a.id, 500), (b.id, 300)):
        p = await _row(db_session, uid)
        p.created_at = start
        p.week_key, p.week_xp = prev, xp
        db_session.add(p)
    await db_session.commit()
    await _view(client, b_headers)
    await _view(client, a_headers)
    await prospect_life.sweep(db_session)
    for uid, coins in ((a.id, C["week_prizes"][0]), (b.id, C["week_prizes"][1])):
        user = await db_session.get(User, uid, populate_existing=True)
        assert user.balance == coins
    notes = [n for n in (await db_session.execute(select(Notification).where(
        Notification.user_id == a.id, Notification.type == NotificationType.prospect_event,
    ))).scalars().all() if "Турнир" in n.title]
    assert len(notes) == 1 and "1 место" in notes[0].title


def test_week_xp_rolls_over():
    p = SimpleNamespace(week_key="2026-W45", week_xp=100, last_week_key=None, last_week_xp=0, xp=0)
    ps._bump_week(p, 30, date(2026, 11, 12))  # W46
    assert (p.last_week_key, p.last_week_xp, p.week_key, p.week_xp) == ("2026-W45", 100, "2026-W46", 30)


# --- duels ------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_duel_of_friends_in_otvetka(client, db_session, bot_token):
    a, a_headers = await _create(client, db_session, 881051, bot_token)
    b, b_headers = await _create(client, db_session, 881052, bot_token)
    assert (await client.post(f"{API}/prospect/duels", json={"friend_id": b.id}, headers=a_headers)).status_code == 409
    await _friends(db_session, a.id, b.id)
    res = await client.post(f"{API}/prospect/duels", json={"friend_id": b.id}, headers=a_headers)
    assert res.status_code == 200, res.text
    duel_id = res.json()["duel_id"]
    assert (await client.post(f"{API}/prospect/duels", json={"friend_id": b.id}, headers=a_headers)).status_code == 409
    incoming = (await _view(client, b_headers))["duels"][0]
    assert incoming["incoming"] and incoming["can_play"]

    async def play(headers, bot_goals):
        """The test player never scores: the bot's goals set the result."""
        start = await client.post(f"{API}/games/otvetka/start", json={"duel_id": duel_id}, headers=headers)
        assert start.status_code == 200, start.text
        assert start.json()["duel_id"] == duel_id
        sid, episode = start.json()["session_id"], start.json()["episode"]
        await _rig(db_session, sid, {i: i < bot_goals for i in range(10)})
        for _ in range(10):
            episode = (await _play(client, headers, db_session, sid, episode))["next_episode"]
        claim = await client.post(f"{API}/games/otvetka/{start.json()['session_id']}/claim", headers=headers)
        assert claim.status_code == 200, claim.text
        again = await client.post(f"{API}/games/otvetka/start", json={"duel_id": duel_id}, headers=headers)
        assert again.status_code == 409

    await play(a_headers, bot_goals=1)  # 0:1 beats 0:3
    await play(b_headers, bot_goals=3)
    duel = await db_session.get(ProspectDuel, duel_id, populate_existing=True)
    assert duel.status == "done" and duel.winner_id == a.id
    assert duel.challenger_result == {"for": 0, "against": 1, "won": False}
    view = await _view(client, a_headers)
    assert view["duels"][0]["won"] is True and view["prospect"]["stats"]["duel_wins"] == 1


@pytest.mark.asyncio
async def test_an_unplayed_duel_expires_as_a_walkover(client, db_session, bot_token):
    a, a_headers = await _create(client, db_session, 881061, bot_token)
    b, _ = await _create(client, db_session, 881062, bot_token)
    await _friends(db_session, a.id, b.id)
    duel_id = (await client.post(f"{API}/prospect/duels", json={"friend_id": b.id}, headers=a_headers)).json()["duel_id"]
    duel = await db_session.get(ProspectDuel, duel_id)
    duel.challenger_session_id = 1
    duel.challenger_result = {"for": 1, "against": 2, "won": False}
    db_session.add(duel)
    await db_session.commit()
    await prospect_life.sweep(db_session, datetime.now(timezone.utc) + timedelta(hours=C["duel_hours"] + 1))
    duel = await db_session.get(ProspectDuel, duel_id, populate_existing=True)
    assert duel.status == "expired" and duel.winner_id == a.id


# --- gifts / birthday / seasons ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_gift_to_a_friends_prospect(client, db_session, bot_token, fake_invoice_link):
    a, a_headers = await _user(client, db_session, 881071, bot_token)
    b, b_headers = await _create(client, db_session, 881072, bot_token)
    bad = await client.post(f"{API}/prospect/stars-invoice", json={"purchase": f"gift:coach:{b.id}"}, headers=a_headers)
    assert bad.status_code == 409  # not friends
    await _friends(db_session, a.id, b.id)
    inv = await client.post(f"{API}/prospect/stars-invoice", json={"purchase": f"gift:coach:{b.id}"}, headers=a_headers)
    assert inv.status_code == 200, inv.text
    token, stars = inv.json()["payload_token"], inv.json()["stars_amount"]
    assert stars == C["gift_coach_stars"]
    assert (await stars_payment_service.validate_pre_checkout(db_session, token, stars))[0]
    await stars_payment_service.deliver_payment(db_session, token, a.telegram_id, "ch-gift-1", stars)
    await stars_payment_service.deliver_payment(db_session, token, a.telegram_id, "ch-gift-1", stars)
    view = await _view(client, b_headers)
    assert view["coach"]["active"]
    assert any(m["code"] == f"gift:{a.id}" for m in view["prospect"]["memories"])


@pytest.mark.asyncio
async def test_the_birthday_box_once_a_year(client, db_session, bot_token, fake_invoice_link):
    user, headers = await _create(client, db_session, 881081, bot_token)
    assert (await client.post(f"{API}/prospect/stars-invoice", json={"purchase": "bday"}, headers=headers)).status_code == 409
    await _age(db_session, user.id, C["days_per_year"])
    view = await _view(client, headers)
    assert view["bday"]["today"] and not view["bday"]["opened"]
    inv = (await client.post(f"{API}/prospect/stars-invoice", json={"purchase": "bday"}, headers=headers)).json()
    await stars_payment_service.deliver_payment(db_session, inv["payload_token"], user.telegram_id, "ch-bday-1", inv["stars_amount"])
    view = await _view(client, headers)
    assert view["bday"]["opened"] and view["prospect"]["xp"] >= C["bday_xp"]
    assert len(view["prospect"]["owned_cosmetics"]) == 2
    assert (await client.post(f"{API}/prospect/stars-invoice", json={"purchase": "bday"}, headers=headers)).status_code == 409


def test_seasons_wrap_the_new_year():
    assert ps.season_active(C, "winter", date(2026, 12, 20))
    assert ps.season_active(C, "winter", date(2027, 1, 10))
    assert not ps.season_active(C, "winter", date(2026, 11, 15))
    assert ps.season_active(C, None, date(2026, 11, 15))


@pytest.mark.asyncio
async def test_seasonal_items_sell_only_in_season(client, db_session, bot_token, monkeypatch):
    user, headers = await _create(client, db_session, 881091, bot_token)
    monkeypatch.setattr(ps, "local_today", lambda *_a: date(2026, 11, 15))
    assert (await client.post(f"{API}/prospect/cosmetics/acc_scarf/buy", headers=headers)).status_code == 409
    monkeypatch.setattr(ps, "local_today", lambda *_a: date(2026, 12, 20))
    assert (await client.post(f"{API}/prospect/cosmetics/acc_scarf/buy", headers=headers)).status_code == 200


# --- the bot digest / admin / share -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_evening_digest_once_a_day(client, db_session, bot_token):
    user, headers = await _create(client, db_session, 881101, bot_token)
    user = await db_session.get(User, user.id, populate_existing=True)
    user.last_seen_at = datetime.now(timezone.utc)
    db_session.add(user)
    await db_session.commit()
    local = datetime.now(app_timezone()).replace(hour=C["notify_hour"] + 1, minute=0, second=0, microsecond=0)
    evening = local.astimezone(timezone.utc)
    morning = local.replace(hour=max(0, C["notify_hour"] - 10)).astimezone(timezone.utc)
    assert await prospect_life.remind_due(db_session, morning) == 0
    assert await prospect_life.remind_due(db_session, evening) == 1
    assert await prospect_life.remind_due(db_session, evening) == 0
    note = (await db_session.execute(select(Notification).where(
        Notification.user_id == user.id, Notification.type == NotificationType.prospect_event,
    ))).scalar_one()
    assert "Тренировка" in note.body
    ledger = (await db_session.execute(select(ProspectLedger).where(ProspectLedger.kind == "notice"))).scalars().all()
    assert len(ledger) == 1


@pytest.mark.asyncio
async def test_share_card_of_the_prospect(client, db_session, bot_token):
    _, headers = await _create(client, db_session, 881111, bot_token)
    res = await client.post(f"{API}/share/prepare", headers=headers, json={"kind": "prospect"})
    assert res.status_code == 200, res.text
    assert "Лёва Мяч" in res.json()["caption"] and res.json()["image_url"].startswith("/static/share/prospect_")
