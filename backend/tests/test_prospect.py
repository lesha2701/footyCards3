from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.core.timeutil import local_today
from app.models.academy_prospect import AcademyProspect
from app.models.enums import Position
from app.services import prospect_service as ps
from app.services import stars_payment_service
from tests.factories import get_user_by_telegram_id
from tests.test_free_kick import _register
from tests.test_otvetka import _play_all
from tests.utils import telegram_headers

C = ps.cfg(SimpleNamespace(prospect={}))
NEW = {"name": "Лёва Мяч", "number": 7, "position": "ST", "foot": "left", "appearance": {}}


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    rate_limit_module._hits.clear()
    yield
    rate_limit_module._hits.clear()


def _kid(days_old: int = 0, xp: int = 0, potential: int = 3) -> AcademyProspect:
    created = datetime.now(timezone.utc) - timedelta(days=days_old)
    return AcademyProspect(id=1, user_id=1, name="Кид", number=9, position=Position.ST, foot="right", appearance={},
                           potential=potential, xp=xp, xp_today=0, created_at=created, memories=[], stats={},
                           cosmetics={}, rival_seed=5, potential_revealed=False)


# --- pure progression ----------------------------------------------------------

def test_age_and_stages_follow_the_calendar():
    assert ps.age_of(0, C) == 6 and ps.stage_index(6, C) == 0
    assert ps.age_of(24, C) == 9 and ps.stage_index(9, C) == 1
    assert ps.stage_index(ps.age_of(48, C), C) == 2
    assert ps.stage_index(ps.age_of(72, C), C) == 3
    assert ps.stage_index(ps.age_of(96, C), C) == 4
    assert ps.days_to_peak(C) == 96


def test_peak_from_potential_stays_under_ninety():
    assert ps.peak_of(1, C) == 82
    assert ps.peak_of(5, C) == 90
    assert ps.peak_of(5, C, 12) == 99


def test_the_stage_caps_the_rating_and_xp_is_banked():
    today = local_today()
    rich = 100 * C["xp_per_point"]
    assert ps.rating_of(_kid(0, rich), C, today) == 38
    assert ps.rating_of(_kid(30, rich), C, today) == 52
    # Debut: the peak, whatever the banked XP.
    assert ps.rating_of(_kid(100, rich, potential=5), C, today) == 90
    assert ps.rating_of(_kid(100, rich, potential=1), C, today) == 82
    assert ps.rating_of(_kid(100, 0), C, today) == C["start_rating"]


def test_a_steady_player_peaks_in_about_a_hundred_days():
    """Matches up to the daily cap plus the free training: the peak (★5)
    comes by the debut age, not long before."""
    per_day = C["daily_xp_cap"] + C["training_xp"]
    need = (ps.peak_of(5, C) - C["start_rating"]) * C["xp_per_point"]
    assert 60 <= need / per_day <= 100
    assert ps.days_to_peak(C) <= 100


def test_daily_cap_limits_matches_but_not_bonus():
    today = local_today()
    kid = _kid()
    assert ps.grant_xp(kid, 300, C, today, bonus_pct=10) == 330
    assert ps.grant_xp(kid, 300, C, today, bonus_pct=10) == 22  # 20 left under the cap + 10%
    assert ps.grant_xp(kid, 300, C, today) == 0
    assert ps.grant_xp(kid, 60, C, today, capped=False) == 60


def test_match_rating_rewards_being_ahead_of_the_curve():
    today = local_today()
    on_curve = _kid(40, xp=0)
    ahead = _kid(40, xp=40 * C["xp_per_point"])
    assert ps.match_rating(ahead, C, today) > ps.match_rating(on_curve, C, today)
    assert 40 <= ps.match_rating(on_curve, C, today) <= 99


def test_story_comes_every_other_day_and_is_stable():
    today = local_today()
    kid = _kid(5)
    story = ps.current_story(kid, C, today)
    assert story is not None and story["stages"][0] == 0
    assert ps.current_story(kid, C, today)["code"] == story["code"]
    kid.story_day = today - timedelta(days=1)
    assert ps.current_story(kid, C, today) is None
    kid.story_day = today - timedelta(days=2)
    assert ps.current_story(kid, C, today) is not None
    assert ps.current_story(_kid(0), C, today) is None


def test_sync_reveals_potential_at_u19_and_remembers_stages():
    today = local_today()
    kid = _kid(75)
    ps.sync(kid, C, today)
    assert kid.potential_revealed
    codes = {m["code"] for m in kid.memories}
    assert {"stage:school", "stage:youth", "stage:u19"} <= codes


def test_rival_grows_with_age():
    today = local_today()
    assert ps.rival_of(_kid(60), C, today)["rating"] > ps.rival_of(_kid(5), C, today)["rating"]


# --- API -------------------------------------------------------------------------

async def _create(client, db_session, tg_id, bot_token):
    user = await _register(client, db_session, tg_id, bot_token)
    headers = telegram_headers(tg_id, bot_token)
    res = await client.post("/api/v1/prospect", json=NEW, headers=headers)
    assert res.status_code == 200, res.text
    return user, headers, res.json()


async def _age(db_session, user_id: int, days: int) -> AcademyProspect:
    p = (await db_session.execute(select(AcademyProspect).where(AcademyProspect.user_id == user_id))).scalar_one()
    p.created_at = datetime.now(timezone.utc) - timedelta(days=days)
    db_session.add(p)
    await db_session.commit()
    return p


@pytest.mark.asyncio
async def test_create_once_and_view(client, db_session, bot_token):
    _, headers, view = await _create(client, db_session, 880101, bot_token)
    p = view["prospect"]
    assert (p["name"], p["age"], p["stage"], p["rating"]) == ("Лёва Мяч", 6, 0, 25)
    assert p["potential"] is None and view["story"] is None
    assert view["training"]["free_available"]
    again = await client.post("/api/v1/prospect", json=NEW, headers=headers)
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_training_once_a_day(client, db_session, bot_token):
    _, headers, view = await _create(client, db_session, 880102, bot_token)
    drill = view["training"]["drills"][0]["code"]
    res = await client.post("/api/v1/prospect/train", json={"drill": drill}, headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["xp"] > 0 and body["view"]["prospect"]["xp"] == body["xp"]
    assert not body["view"]["training"]["free_available"]
    assert (await client.post("/api/v1/prospect/train", json={"drill": drill}, headers=headers)).status_code == 409
    assert (await client.post("/api/v1/prospect/train", json={"drill": "nope"}, headers=headers)).status_code == 409


@pytest.mark.asyncio
async def test_story_answer_spends_coins_and_closes(client, db_session, bot_token):
    user, headers, _ = await _create(client, db_session, 880103, bot_token)
    await _age(db_session, user.id, 3)
    view = (await client.get("/api/v1/prospect", headers=headers)).json()
    story = view["story"]
    assert story is not None
    option = next((i for i, o in enumerate(story["options"]) if not o["coins"]), 0)
    res = await client.post("/api/v1/prospect/story", json={"code": story["code"], "option": option}, headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["view"]["story"] is None
    again = await client.post("/api/v1/prospect/story", json={"code": story["code"], "option": option}, headers=headers)
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_universal_until_youth_then_the_coach_offers_positions(client, db_session, bot_token):
    user, headers, view = await _create(client, db_session, 880104, bot_token)
    assert view["prospect"]["universal"] is True and view["position_pick"] is None
    drills = view["training"]["drills"]
    assert sorted(d["line"] for d in drills) == ["DEF", "FWD", "GK", "MID"]
    defence = next(d for d in drills if d["line"] == "DEF")
    assert (await client.post("/api/v1/prospect/train", json={"drill": defence["code"]}, headers=headers)).status_code == 200
    # Not chosen yet: a position in PATCH changes nothing.
    assert (await client.patch("/api/v1/prospect", json={"position": "ST"}, headers=headers)).status_code == 200
    early = await client.post("/api/v1/prospect/position", json={"position": "CB"}, headers=headers)
    assert early.status_code == 409

    await _age(db_session, user.id, 50)
    view = (await client.get("/api/v1/prospect", headers=headers)).json()
    options = view["position_pick"]["options"]
    assert len(options) == C["position_options"]
    assert options[0]["line"] == "DEF" and options[0]["drills"] == 1
    offered = {o["position"] for o in options}
    other = next(pos for pos in ("GK", "ST", "LW", "RW", "CM", "CDM", "CAM", "LM", "RM", "CB", "LB", "RB") if pos not in offered)
    bad = await client.post("/api/v1/prospect/position", json={"position": other}, headers=headers)
    assert bad.status_code == 409
    res = await client.post("/api/v1/prospect/position", json={"position": options[0]["position"]}, headers=headers)
    assert res.status_code == 200, res.text
    after = res.json()
    assert after["prospect"]["position"] == options[0]["position"] and after["prospect"]["universal"] is False
    assert after["position_pick"] is None and after["position_change"]["stars"] == C["position_change_stars"]
    assert all(d["line"] == "DEF" for d in after["training"]["drills"])
    again = await client.post("/api/v1/prospect/position", json={"position": options[1]["position"]}, headers=headers)
    assert again.status_code == 409
    free_change = await client.patch("/api/v1/prospect", json={"position": "ST"}, headers=headers)
    assert free_change.status_code == 409


@pytest.mark.asyncio
async def test_position_change_for_stars(client, db_session, bot_token, monkeypatch):
    async def fake_link(*_a, **_k):
        return "https://t.me/invoice/x"

    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", fake_link)
    user, headers, _ = await _create(client, db_session, 880110, bot_token)
    early = await client.post("/api/v1/prospect/stars-invoice", json={"purchase": "pos:GK"}, headers=headers)
    assert early.status_code == 409  # nothing to change before the coach's offer
    await _age(db_session, user.id, 50)
    view = (await client.get("/api/v1/prospect", headers=headers)).json()
    first = view["position_pick"]["options"][0]["position"]
    await client.post("/api/v1/prospect/position", json={"position": first}, headers=headers)
    target = "GK" if first != "GK" else "ST"
    same = await client.post("/api/v1/prospect/stars-invoice", json={"purchase": f"pos:{first}"}, headers=headers)
    assert same.status_code == 409
    inv = await client.post("/api/v1/prospect/stars-invoice", json={"purchase": f"pos:{target}"}, headers=headers)
    assert inv.status_code == 200, inv.text
    assert inv.json()["stars_amount"] == C["position_change_stars"] == 300
    data = inv.json()
    await stars_payment_service.deliver_payment(db_session, data["payload_token"], user.telegram_id, "ch-pos-1", data["stars_amount"])
    await stars_payment_service.deliver_payment(db_session, data["payload_token"], user.telegram_id, "ch-pos-1", data["stars_amount"])
    view = (await client.get("/api/v1/prospect", headers=headers)).json()
    assert view["prospect"]["position"] == target
    assert sum(1 for m in view["prospect"]["memories"] if m["code"].startswith("position:")) == 1


@pytest.mark.asyncio
async def test_first_child_is_at_least_three_stars(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(ps, "roll_potential", lambda *_a: 1)
    user, headers, _ = await _create(client, db_session, 880111, bot_token)
    p = (await db_session.execute(select(AcademyProspect).where(AcademyProspect.user_id == user.id))).scalar_one()
    assert p.generation == 1 and p.potential == C["first_min_potential"] == 3
    p.status = ps.RETIRED
    db_session.add(p)
    await db_session.commit()
    res = await client.post("/api/v1/prospect", json=NEW, headers=headers)
    assert res.status_code == 200, res.text
    second = (await db_session.execute(select(AcademyProspect).where(
        AcademyProspect.user_id == user.id, AcademyProspect.status == ps.GROWING))).scalar_one()
    assert second.generation == 2 and second.potential == 1  # the rule is for the first child only


@pytest.mark.asyncio
async def test_a_lucky_story_counts_one_win_in_the_stage_trial(client, db_session, bot_token, monkeypatch):
    user, headers, _ = await _create(client, db_session, 880113, bot_token)
    await _age(db_session, user.id, 30)  # «Детская школа»: a trial stage
    exam = next(st for st in ps.STORIES if st["code"] == "exam")
    monkeypatch.setattr(ps, "current_story", lambda *_a: exam)

    class Lucky:
        def randrange(self, _n):
            return 0

    monkeypatch.setattr(ps.random, "SystemRandom", Lucky)
    view = (await client.get("/api/v1/prospect", headers=headers)).json()
    assert view["story"]["options"][1]["trial"] is True
    res = await client.post("/api/v1/prospect/story", json={"code": "exam", "option": 1}, headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["won"] is True and body["trial_credit"] is True and body["potential_up"] is False
    school = body["view"]["growth"]["trial"]["stages"][0]
    assert (school["played"], school["wins"], school["story"]) == (1, 1, True)
    # Once a stage: the next lucky story only gives XP.
    assert body["view"]["story"]["options"][1]["trial"] is False
    p = (await db_session.execute(select(AcademyProspect).where(AcademyProspect.user_id == user.id)
                                  .execution_options(populate_existing=True))).scalar_one()
    p.story_day = None
    db_session.add(p)
    await db_session.commit()
    again = (await client.post("/api/v1/prospect/story", json={"code": "exam", "option": 1}, headers=headers)).json()
    assert again["trial_credit"] is False
    assert again["view"]["growth"]["trial"]["stages"][0]["wins"] == 1


@pytest.mark.asyncio
async def test_academy_levels_raise_the_peak(client, db_session, bot_token):
    from app.models.card_path import UserAcademy

    user, headers, _ = await _create(client, db_session, 880112, bot_token)
    db_session.add(UserAcademy(user_id=user.id, levels={"training": 12, "scout": 13}, total_level=25))
    await db_session.commit()
    view = (await client.get("/api/v1/prospect", headers=headers)).json()
    assert view["prospect"]["peak_bonus"] == {"dynasty": 0, "academy": 2}
    assert view["growth"]["peak"]["academy_level"] == 25 and view["growth"]["peak"]["next_level"] == 30


@pytest.mark.asyncio
async def test_coin_cosmetic_and_equip(client, db_session, bot_token):
    user, headers, _ = await _create(client, db_session, 880105, bot_token)
    user.balance = 10_000
    db_session.add(user)
    await db_session.commit()
    res = await client.post("/api/v1/prospect/cosmetics/bg_gym/buy", headers=headers)
    assert res.status_code == 200, res.text
    assert "bg_gym" in res.json()["prospect"]["owned_cosmetics"]
    assert (await client.post("/api/v1/prospect/cosmetics/bg_gym/buy", headers=headers)).status_code == 409
    assert (await client.post("/api/v1/prospect/cosmetics/bg_gold/buy", headers=headers)).status_code == 409
    eq = await client.put("/api/v1/prospect/cosmetics/equip", json={"kind": "background", "code": "bg_gym"}, headers=headers)
    assert eq.json()["prospect"]["background"] == "bg_gym"
    bad = await client.put("/api/v1/prospect/cosmetics/equip", json={"kind": "background", "code": "bg_gold"}, headers=headers)
    assert bad.status_code == 409
    fresh = await get_user_by_telegram_id(db_session, 880105)
    await db_session.refresh(fresh)
    assert fresh.balance == 7_000


@pytest.mark.asyncio
async def test_stars_coach_and_scout_delivered_once(client, db_session, bot_token, monkeypatch):
    async def fake_link(*_a, **_k):
        return "https://t.me/invoice/x"

    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", fake_link)
    user, headers, _ = await _create(client, db_session, 880106, bot_token)
    res = await client.post("/api/v1/prospect/stars-invoice", json={"purchase": "coach"}, headers=headers)
    assert res.status_code == 200, res.text
    token, stars = res.json()["payload_token"], res.json()["stars_amount"]
    assert (await stars_payment_service.validate_pre_checkout(db_session, token, stars))[0]
    await stars_payment_service.deliver_payment(db_session, token, user.telegram_id, "ch-pros-1", stars)
    await stars_payment_service.deliver_payment(db_session, token, user.telegram_id, "ch-pros-1", stars)
    view = (await client.get("/api/v1/prospect", headers=headers)).json()
    assert view["coach"]["active"] and view["bonus"]["coach"] == C["coach_xp_pct"]

    scout = (await client.post("/api/v1/prospect/stars-invoice", json={"purchase": "scout"}, headers=headers)).json()
    await stars_payment_service.deliver_payment(db_session, scout["payload_token"], user.telegram_id, "ch-pros-2", scout["stars_amount"])
    view = (await client.get("/api/v1/prospect", headers=headers)).json()
    assert view["prospect"]["potential"] in range(1, 6)
    again = await client.post("/api/v1/prospect/stars-invoice", json={"purchase": "scout"}, headers=headers)
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_extra_training_bought_for_stars(client, db_session, bot_token, monkeypatch):
    async def fake_link(*_a, **_k):
        return "https://t.me/invoice/x"

    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", fake_link)
    user, headers, view = await _create(client, db_session, 880107, bot_token)
    drill = view["training"]["drills"][0]["code"]
    await client.post("/api/v1/prospect/train", json={"drill": drill}, headers=headers)
    inv = (await client.post("/api/v1/prospect/stars-invoice", json={"purchase": "training"}, headers=headers)).json()
    await stars_payment_service.deliver_payment(db_session, inv["payload_token"], user.telegram_id, "ch-pros-3", inv["stars_amount"])
    res = await client.post("/api/v1/prospect/train", json={"drill": drill}, headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["view"]["training"]["extra_credits"] == 0


@pytest.mark.asyncio
async def test_prospect_plays_otvetka_and_gets_xp_once(client, db_session, bot_token):
    _, headers, _ = await _create(client, db_session, 880108, bot_token)
    res = await client.post("/api/v1/games/otvetka/start", json={"prospect": True}, headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["prospect_name"] == "Лёва Мяч"
    await _play_all(client, headers, db_session, data, True)
    claim = await client.post(f"/api/v1/games/otvetka/{data['session_id']}/claim", headers=headers)
    assert claim.status_code == 200, claim.text
    assert claim.json()["prospect_xp"] == C["otvetka_match_xp"]
    view = (await client.get("/api/v1/prospect", headers=headers)).json()
    assert view["prospect"]["xp"] == C["otvetka_match_xp"]
    assert view["prospect"]["stats"]["matches"] == 1


@pytest.mark.asyncio
async def test_otvetka_without_a_prospect_or_card_is_refused(client, db_session, bot_token):
    await _register(client, db_session, 880109, bot_token)
    headers = telegram_headers(880109, bot_token)
    assert (await client.post("/api/v1/games/otvetka/start", json={"prospect": True}, headers=headers)).status_code == 404
    assert (await client.post("/api/v1/games/otvetka/start", json={}, headers=headers)).status_code == 409


def test_peak_bonuses_from_dynasty_and_academy():
    today = local_today()
    rich = 100 * C["xp_per_point"]
    kid = _kid(100, rich, potential=5)
    kid.generation, kid.academy_peak = 3, 2
    assert ps.dynasty_peak(1, C) == 0 and ps.dynasty_peak(3, C) == 2 and ps.dynasty_peak(40, C) == C["dynasty_peak_max"]
    assert ps.academy_peak_for(29, C) == 2 and ps.academy_peak_for(30, C) == 3
    assert ps.rating_of(kid, C, today) == 90 + 2 + 2
    # The bonus lifts only the peak, not the younger stages' caps.
    young = _kid(30, rich, potential=5)
    young.generation, young.academy_peak = 3, 2
    assert ps.rating_of(young, C, today) == 52


def test_training_streak_raises_the_potential_up_to_the_limit():
    today = local_today()
    kid = _kid(potential=2)
    stats: dict = {}
    kid.training_streak = 13
    assert not ps._streak_potential(kid, C, stats, today)
    for n in range(1, C["potential_streak_max"] + 2):
        kid.training_streak = C["potential_streak_days"] * n
        ps._streak_potential(kid, C, stats, today)
    assert kid.potential == 2 + C["potential_streak_max"]
    assert stats["streak_potential"] == C["potential_streak_max"]


def test_stage_trial_passes_with_wins_and_fails_with_losses():
    today = local_today()
    kid = _kid(30, potential=3)  # «Детская школа»: a trial stage
    stats: dict = {}
    assert not ps._trial_match(kid, C, stats, True, today)
    assert ps._trial_match(kid, C, stats, True, today) and kid.potential == 4
    assert stats["trials"]["1"]["passed"] is True
    assert not ps._trial_match(kid, C, stats, True, today) and kid.potential == 4  # once per stage

    loser = _kid(30, potential=3)
    stats = {}
    ps._trial_match(loser, C, stats, False, today)
    ps._trial_match(loser, C, stats, False, today)
    assert stats["trials"]["1"]["passed"] is False and loser.potential == 3
    # No trial on «Двор».
    assert not ps._trial_match(_kid(0), C, {}, True, today)


def test_coach_offers_lean_on_drills_and_talents():
    kid = _kid()
    kid.stats = {"drills": {"FWD": 1, "MID": 2}}
    kid.specs = ["wall"]  # +3 to defence
    offers = ps.position_offers(kid, C, deficits={"GK"})
    assert [o["line"] for o in offers] == ["DEF", "DEF", "MID"]
    assert offers[0]["talents"] == ["Стена"]
    # Ties go to deficit lines.
    blank = _kid()
    blank.stats, blank.specs = {}, []
    offers = ps.position_offers(blank, C, deficits={"GK"})
    assert offers[0]["position"] == "GK" and offers[0]["deficit"] and offers[0]["xp_pct"] == C["deficit_xp_pct"]
    assert len(offers) == C["position_options"]


@pytest.mark.asyncio
async def test_deficit_lines_follow_the_prospects(db_session):
    assert await ps.deficit_lines(db_session, C) == set()
    for i in range(30):
        db_session.add(AcademyProspect(user_id=990000 + i, name=f"Нап{i}", number=9, position=Position.ST, position_set=True,
                                       foot="right", appearance={}, potential=3, rival_seed=1))
    await db_session.commit()
    assert await ps.deficit_lines(db_session, C) == {"GK", "DEF", "MID"}


def test_deficit_bonus_adds_to_the_manager_value():
    from app.services import manager_service

    kid = _kid()
    kid.stats = {"deficit": {"line": "GK", "xp_pct": 10, "value_pct": 15}}
    config = SimpleNamespace(manager_form_bonus_cap=0, manager_form_bonus_pct=0,
                             manager_value_ratings=[40, 90], manager_value_eur=[100_000, 10_000_000])
    plain = manager_service.live_value(70, None, config)
    assert manager_service.live_value(70, None, config, ps.value_pct(kid)) > plain


def test_cohort_key_is_iso_week():
    assert ps.cohort_key(datetime(2026, 11, 10, 12, tzinfo=timezone.utc)) == "2026-W46"
    assert isinstance(date.today(), date)


def test_admin_validate_keeps_known_sane_numbers():
    assert ps.validate({"daily_xp_cap": 500, "enabled": False}) == {"daily_xp_cap": 500, "enabled": False}
    assert ps.validate({"cosmetics": {"bg_gold": {"stars": 75}}})["cosmetics"]["bg_gold"] == {"coins": 0, "stars": 75}
    for bad in ({"nope": 1}, {"xp_per_point": -1}, {"stage_caps": [40, 50]}, {"stage_ages": [7, 9, 12, 15, 18]},
                {"cosmetics": {"unknown": {"coins": 1}}}, {"potential_weights": [0, 0, 0, 0, 0]}):
        with pytest.raises(ValueError):
            ps.validate(bad)
    tuned = ps.cfg(SimpleNamespace(prospect={"daily_xp_cap": 500, "cosmetics": {"bg_gold": {"coins": 0, "stars": 75}}}))
    assert tuned["daily_xp_cap"] == 500 and tuned["cosmetics"]["bg_gold"]["stars"] == 75
    assert tuned["cosmetics"]["bg_gym"]["coins"] == 3000
