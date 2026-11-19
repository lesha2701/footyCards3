"""«Рабочие места» in the town (town_service.JOBS): employer buildings bought
and levelled for coins, workers assigned by themselves (residents not on the
«Менеджер» staff, at most the jobs), their extra tax inside the rent, the
≥ 60-day payback of every default level and the club fans of the population."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.game_config import DEFAULT_TOWN_JOBS, GameConfig
from app.models.manager_club import ManagerClub, ManagerStaff
from app.models.town import TownLedger, UserTownJob, UserTownResident
from app.services import manager_finance, town_service
from tests.test_manager import _no_season_at_the_real_clock, _reset_rate_limits  # noqa: F401
from tests.test_manager_finance import _club_row, _keep_loaded, _setup  # noqa: F401
from tests.test_town import API, _config, _login, _resident, _town

JOBS_CFG = {"factory": {"price": 100, "jobs": 10, "levels": 3, "growth_pct": 50}}


def _default(column: str):
    return GameConfig.__table__.c[column].default.arg


def _defaults() -> SimpleNamespace:
    return SimpleNamespace(
        town_jobs={k: dict(v) for k, v in DEFAULT_TOWN_JOBS.items()},
        town_resident_rent=_default("town_resident_rent"),
        town_job_tax_pct=_default("town_job_tax_pct"),
        town_fans_k=_default("town_fans_k"),
        town_fans_cap=_default("town_fans_cap"),
    )


async def _people(db_session, user_id, copies, name="Рабочий"):
    resident = await _resident(db_session, name=name)
    db_session.add(UserTownResident(user_id=user_id, resident_id=resident.id, copies=copies, source="admin"))
    await db_session.commit()
    return resident


def test_every_default_level_pays_back_in_at_least_60_days():
    config = _defaults()
    assert set(DEFAULT_TOWN_JOBS) == set(town_service.JOBS)
    assert config.town_job_tax_pct == 50
    for code, values in DEFAULT_TOWN_JOBS.items():
        for level in range(1, values["levels"] + 1):
            days = town_service.payback_days(config, code, level)
            assert days is not None and days >= town_service.PAYBACK_MIN_DAYS, (code, level, days)
        assert 70 <= town_service.payback_days(config, code, 1) <= 80  # ~75 days for the first level


def test_fans_formula_and_cap():
    config = _defaults()
    assert town_service.fans_for(config, 0) == 0
    assert town_service.fans_for(config, 1) == 30
    assert town_service.fans_for(config, 10) == 94  # floor(30 × 3.162…)
    assert town_service.fans_for(config, 100) == 300
    assert town_service.fans_for(config, 10_000) == 1500  # capped


def test_employment_is_capped_by_residents_and_by_jobs():
    config = SimpleNamespace(town_jobs=JOBS_CFG, town_resident_rent=2, town_job_tax_pct=50)
    assert town_service.employment(config, 25, 0, {"factory": 2}) == \
        {"jobs": 20, "free": 25, "staff": 0, "employed": 20, "tax": 20}
    assert town_service.employment(config, 12, 4, {"factory": 2})["employed"] == 8  # staff residents don't work here
    assert town_service.employment(config, 3, 5, {"factory": 1})["free"] == 0


def test_jobs_settings_validation():
    assert town_service.validate_jobs({"port": {"price": 10, "jobs": 2, "levels": 1, "growth_pct": 0}}) == \
        {"port": {"price": 10, "jobs": 2, "levels": 1, "growth_pct": 0}}
    for bad in ({"bank": {}}, {"port": {"price": -1}}, {"port": {"levels": 0}}, {"port": {"jobs": "5"}}, {"port": 3}):
        with pytest.raises(ValueError):
            town_service.validate_jobs(bad)


async def test_buying_and_levelling_a_building(client, db_session, bot_token):
    await _config(db_session, town_jobs=JOBS_CFG)
    headers, user = await _login(client, db_session, bot_token, 991201, balance=1000)
    state = (await client.get(f"{API}/town", headers=headers)).json()
    factory = next(b for b in state["jobs"]["buildings"] if b["code"] == "factory")
    assert factory["level"] == 0 and factory["next_price"] == 100 and state["jobs"]["jobs"] == 0

    r = await client.post(f"{API}/town/jobs/factory/buy", headers=headers, json={"idempotency_key": "j1"})
    assert r.status_code == 200, r.text
    assert r.json()["new_balance"] == 900 and r.json()["jobs"]["jobs"] == 10
    replay = await client.post(f"{API}/town/jobs/factory/buy", headers=headers, json={"idempotency_key": "j1"})
    assert replay.json()["new_balance"] == 900  # never charged twice

    r = (await client.post(f"{API}/town/jobs/factory/buy", headers=headers, json={})).json()
    assert r["new_balance"] == 750 and r["jobs"]["jobs"] == 20  # level 2: 100 × 150%
    r = (await client.post(f"{API}/town/jobs/factory/buy", headers=headers, json={})).json()
    factory = next(b for b in r["jobs"]["buildings"] if b["code"] == "factory")
    assert r["new_balance"] == 550 and factory["level"] == 3 and factory["next_price"] is None
    assert (await client.post(f"{API}/town/jobs/factory/buy", headers=headers, json={})).status_code == 409
    assert (await client.post(f"{API}/town/jobs/bank/buy", headers=headers, json={})).status_code == 404

    row = (await db_session.execute(select(UserTownJob).where(UserTownJob.user_id == user.id)
                                    .execution_options(populate_existing=True))).scalar_one()
    assert row.level == 3 and row.coins_paid == 450
    kinds = (await db_session.execute(select(TownLedger.kind).where(TownLedger.user_id == user.id))).scalars().all()
    assert kinds.count("job") == 3


async def test_a_building_needs_coins_and_an_opened_town(client, db_session, bot_token):
    await _config(db_session, town_jobs=JOBS_CFG, town_unlock_coins=500)
    headers, _ = await _login(client, db_session, bot_token, 991202, balance=50)
    assert (await client.post(f"{API}/town/jobs/factory/buy", headers=headers, json={})).status_code == 409
    await _config(db_session, town_jobs=JOBS_CFG, town_unlock_coins=0)
    r = await client.post(f"{API}/town/jobs/factory/buy", headers=headers, json={})
    assert r.status_code in (400, 402, 409), r.text
    assert (await db_session.execute(select(UserTownJob))).scalars().all() == []


async def test_workers_pay_extra_tax_inside_the_rent(client, db_session, bot_token):
    await _config(db_session, town_jobs=JOBS_CFG, town_resident_rent=2, town_job_tax_pct=50,
                  town_income_max_hours=48, town_fans_k=30, town_fans_cap=1500)
    headers, user = await _login(client, db_session, bot_token, 991203)
    await _people(db_session, user.id, 15)
    state = (await client.get(f"{API}/town", headers=headers)).json()
    assert state["income"]["rate_per_day"] == 30 and state["jobs"]["employed"] == 0

    await client.post(f"{API}/town/jobs/factory/buy", headers=headers, json={})
    state = (await client.get(f"{API}/town", headers=headers)).json()
    jobs = state["jobs"]
    assert (jobs["jobs"], jobs["employed"], jobs["free_residents"], jobs["tax_per_day"]) == (10, 10, 15, 10)
    assert state["income"]["rate_per_day"] == 30 + 10
    assert jobs["club_fans"] == town_service.fans_for(SimpleNamespace(town_fans_k=30, town_fans_cap=1500), 15) == 116

    await client.post(f"{API}/town/jobs/factory/buy", headers=headers, json={})  # 20 jobs, only 15 residents
    state = (await client.get(f"{API}/town", headers=headers)).json()
    assert state["jobs"]["employed"] == 15 and state["income"]["rate_per_day"] == 30 + 15

    town = await _town(db_session, user.id)
    town.income_since = datetime.now(timezone.utc) - timedelta(days=1, minutes=1)
    await db_session.commit()
    claim = (await client.post(f"{API}/town/income/claim", headers=headers, json={})).json()
    assert claim["claimed"] == 45  # the tax accrues and is collected with the rent


@pytest.mark.usefixtures("trade_guards_off")
async def test_staff_residents_do_not_work_in_the_town_and_fans_reach_the_club(client, db_session, bot_token):
    uid, headers, club_id = await _setup(client, db_session, bot_token, 991204)
    await _config(db_session, town_jobs=JOBS_CFG, town_resident_rent=2, town_job_tax_pct=50,
                  town_fans_k=30, town_fans_cap=1500)
    club = await _club_row(db_session, club_id)
    fans_before = await manager_finance.fans_of(db_session, club)

    workers = await _people(db_session, uid, 9, name="Рабочий")
    doctor = await _people(db_session, uid, 1, name="Доктор")
    db_session.add(ManagerStaff(club_id=club_id, role="doctor", resident_id=doctor.id, rarity="common", wage=0))
    await db_session.commit()
    await client.post(f"{API}/town/jobs/factory/buy", headers=headers, json={})
    jobs = (await client.get(f"{API}/town", headers=headers)).json()["jobs"]
    assert (jobs["population"], jobs["staff"], jobs["free_residents"], jobs["employed"]) == (10, 1, 9, 9)
    assert workers.id != doctor.id

    club = (await db_session.execute(select(ManagerClub).where(ManagerClub.id == club_id))).scalar_one()
    assert await town_service.town_fans(db_session, uid) == 94  # floor(30 × √10)
    assert await manager_finance.fans_of(db_session, club) == fans_before + 94

    await _config(db_session, town_unlock_coins=1000)  # a closed town brings nobody
    assert await town_service.town_fans(db_session, uid) == 0
