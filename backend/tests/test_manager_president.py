"""«Менеджер» — the president's decisions: the season budget by articles
(plan, overspend, bonus), the hands-on meter, achievements, the analyst's
finance review, the assistant's fine rules (separate limits, untouchables,
the minimum sale, the «только советовать» mode with one-tap advice), the
sporting director, staff conflicts and the targets of «Сегодня в клубе»."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.manager_club import ManagerEvent
from app.services import manager_assistant as assistant, manager_budget as budget, manager_conflicts as conflicts
from app.services import manager_finance as finance, manager_perks as perks, manager_staff as staff
from app.services.game_config_service import get_config
from tests.test_manager import API, _next_season_start, _no_season_at_the_real_clock, _reset_rate_limits  # noqa: F401
from tests.test_manager_finance import _club_row, _keep_loaded, _ledger_sum, _setup, _squad  # noqa: F401
from tests.test_manager_staff import _resident

pytestmark = pytest.mark.usefixtures("trade_guards_off")


async def test_season_budget_plan_overspend_and_bonus(client, db_session, bot_token):
    config = await get_config(db_session)
    uid, headers, club_id = await _setup(client, db_session, bot_token, 899801)
    view = (await client.get(f"{API}/manager/decisions", headers=headers)).json()["budget"]
    assert view["window"] and view["plan"] is None and {a["code"] for a in view["articles"]} == {"wages", "transfers", "club"}
    pot = view["pot"]
    assert (await client.put(f"{API}/manager/budget", headers=headers, json={"alloc": {"wages": pot + 1}})).status_code == 409
    r = await client.put(f"{API}/manager/budget", headers=headers, json={"alloc": {"wages": pot // 2, "transfers": 1000, "club": 1000}})
    assert r.status_code == 200, r.text
    b = r.json()["budget"]
    assert b["plan"]["transfers"] == 1000 and b["reserve"] == pot - pot // 2 - 2000
    key = b["key"]

    # Transfers far over the plan → fans lost, no bonus.
    club = await _club_row(db_session, club_id)
    await finance.book(db_session, club, "npc_loan", -50_000, key)
    fans = int(club.fans_bonus or 0)
    lines = await budget.season_end(db_session, club, key, config)
    assert any("перерасход" in line for line in lines)
    assert club.fans_bonus == max(0, fans + int(finance.cfg(config)["budget_fans_penalty"]) * -1) or club.fans_bonus == 0
    assert budget.plan_of(club, key)["result"]["over"] == ["transfers"]
    assert await _ledger_sum(db_session, club_id, "budget_bonus") == 0
    await budget.season_end(db_session, club, key, config)  # judged once
    assert budget.plan_of(club, key)["result"]["over"] == ["transfers"]

    # Inside every article → a bonus from the unspent plan, once.
    plan = {"pot": 10_000_000, "alloc": {"wages": 1_000_000, "transfers": 1_000_000, "club": 1_000_000}}
    result = budget._judge(plan, {"wages": 900_000}, config, cap=10**9)
    assert result["ok"] and result["bonus"] == int(2_100_000 * finance.cfg(config)["budget_bonus_pct"] / 100)
    assert budget._judge(plan, {"wages": 1_050_000}, config, cap=10**9)["ok"]  # within the tolerance
    assert budget._judge(plan, {"wages": 2_000_000}, config, cap=10**9)["over"] == ["wages"]


async def test_hands_on_meter_and_bonus(client, db_session, bot_token):
    config = await get_config(db_session)
    uid, headers, club_id = await _setup(client, db_session, bot_token, 899802)
    club = await _club_row(db_session, club_id)
    key = "2099-W01"
    for _ in range(4):
        budget.act(club, key)
    token = budget.ACTOR.set("assistant")
    try:
        budget.act(club, key)
    finally:
        budget.ACTOR.reset(token)
    assert budget.acts_of(club, key) == {"me": 4, "assistant": 1, "total": 5, "share": 80}
    reward = budget.hands_on_reward(club, key, config)
    assert reward["money"] > 0 and reward["fans"] == round(finance.cfg(config)["hands_on_fans"] * 0.8)
    await budget.season_end(db_session, club, key, config)
    assert await _ledger_sum(db_session, club_id, "hands_on") == reward["money"]
    await budget.season_end(db_session, club, key, config)
    assert await _ledger_sum(db_session, club_id, "hands_on") == reward["money"]  # once
    assert int(staff.office(club).get("hands_on_full", 0)) == 0  # the assistant decided once

    # Too few decisions → nothing.
    assert budget.hands_on_reward(club, "2099-W02", config) == {"fans": 0, "money": 0}


async def test_achievements_are_claimed_once(client, db_session, bot_token):
    config = await get_config(db_session)
    uid, headers, club_id = await _setup(client, db_session, bot_token, 899803)
    view = (await client.get(f"{API}/manager/decisions", headers=headers)).json()
    promo = next(a for a in view["achievements"] if a["code"] == "promotion")
    assert not promo["done"] and not promo["claimed"]
    assert (await client.post(f"{API}/manager/achievements/promotion/claim", headers=headers)).status_code == 409
    club = await _club_row(db_session, club_id)
    await finance.book(db_session, club, "promotion", 1, await finance.club_key(db_session, club))
    await db_session.commit()
    before = (await _club_row(db_session, club_id)).budget
    r = await client.post(f"{API}/manager/achievements/promotion/claim", headers=headers)
    assert r.status_code == 200, r.text
    got = next(a for a in r.json()["achievements"] if a["code"] == "promotion")
    assert got["claimed"] and (await _club_row(db_session, club_id)).budget == before + got["reward"]
    assert (await client.post(f"{API}/manager/achievements/promotion/claim", headers=headers)).status_code == 409
    assert (await client.post(f"{API}/manager/achievements/nope/claim", headers=headers)).status_code == 404


async def test_analyst_finance_review(client, db_session, bot_token):
    config = await get_config(db_session)
    uid, headers, club_id = await _setup(client, db_session, bot_token, 899804)
    assert (await client.get(f"{API}/manager/decisions", headers=headers)).json()["review"] is None  # needs «Аналитик»
    club = await _club_row(db_session, club_id)
    perks.extend(club, "analytics", 30)
    await finance.book(db_session, club, "grant", 1_000_000, "2000-W01")
    await finance.book(db_session, club, "wages", -900_000, "2000-W01")
    await finance.book(db_session, club, "venture_out", -300_000, "2000-W01")
    await db_session.commit()
    review = (await client.get(f"{API}/manager/decisions", headers=headers)).json()["review"]
    assert review["key"] == "2000-W01" and review["profit"] == 100_000  # the venture is money moved, not a cost
    text = " ".join(review["advice"])
    assert "Зарплаты" in text and "Венчурный" in text
    assert review["costs"][0]["label"] == finance.KINDS["wages"][1]
    assert any(d["code"] == "venture" and d["net"] == -300_000 for d in review["deals"])


async def test_assistant_fine_rules_and_advise_mode(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    uid, headers, club_id = await _setup(client, db_session, bot_token, 899805)
    assert (await client.post(f"{API}/manager/assistant/trial", headers=headers)).status_code == 200
    r = await client.put(f"{API}/manager/assistant/rules", headers=headers,
                         json={"mode": "advise", "transfer_limit": 0, "min_sale": 500_000, "keep": ["npc:1", "bad", "live:2"]})
    assert r.status_code == 200, r.text
    office = (await client.get(f"{API}/manager/assistant", headers=headers)).json()
    rules = office["rules"]
    assert rules["mode"] == "advise" and rules["transfer_limit"] == 0 and rules["min_sale"] == 500_000
    assert rules["keep"] == ["npc:1", "live:2"] and isinstance(office["squad"], list)
    assert (await client.put(f"{API}/manager/assistant/rules", headers=headers, json={"mode": "auto"})).status_code == 422

    # The next window may close more than the free week away (by the weekday).
    club = await _club_row(db_session, club_id)
    perks.extend(club, "assistant", 14)
    await db_session.commit()
    db_session.expunge(club)  # the sweep's own sessions write the office
    near = _next_season_start(config) - timedelta(minutes=30)
    assert await assistant.window_sweep(db_session, near) == 1
    key = await finance.upcoming_key(db_session, near)
    assert not await finance._taken(db_session, club_id, "sponsor", key)  # advice only
    office = (await client.get(f"{API}/manager/assistant", headers=headers)).json()
    advice = [e for e in office["report"]["entries"] if e.get("action")]
    assert advice and office["report"]["todo"] == len([e for e in advice if not e.get("done")])
    sponsor = next(e for e in advice if e["action"]["kind"] == "sponsor")
    assert not any(e["action"]["kind"] == "loan" for e in advice)  # the transfer limit is 0

    summary = (await client.get(f"{API}/manager/summary", headers=headers)).json()
    item = next(i for i in summary["today"] if i["code"] == "advice")
    assert item["tab"] == "staff" and item["target"] == "advice"

    r = await client.post(f"{API}/manager/assistant/advice/{sponsor['id']}", headers=headers)
    assert r.status_code == 200, r.text
    assert next(e for e in r.json()["report"]["entries"] if e["id"] == sponsor["id"])["done"]
    assert await finance._taken(db_session, club_id, "sponsor", await finance.upcoming_key(db_session, datetime.now(timezone.utc)))
    assert (await client.post(f"{API}/manager/assistant/advice/{sponsor['id']}", headers=headers)).status_code == 409
    assert (await client.post(f"{API}/manager/assistant/advice/nope", headers=headers)).status_code == 404
    # The president did it himself — counted as his decision.
    club = await _club_row(db_session, club_id)
    assert budget.acts_of(club, await finance.upcoming_key(db_session, datetime.now(timezone.utc)))["me"] >= 1


async def test_sporting_director_brings_replacements(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    uid, headers, club_id = await _setup(client, db_session, bot_token, 899806)
    assert (await client.get(f"{API}/manager/staff/director", headers=headers)).status_code == 409
    who = await _resident(db_session, uid, "epic", "Директор Карпин")
    r = await client.post(f"{API}/manager/staff/hire", headers=headers, json={"resident_id": who, "role": "director"})
    assert r.status_code == 200, r.text
    assert next(s for s in r.json()["staff"] if s["role"] == "director")["effect_text"].startswith(str(staff.effect_of("director", "epic", config)))
    r = await client.post(f"{API}/manager/staff/director/budget", headers=headers, json={"budget": 10**12})
    assert r.status_code == 200, r.text
    view = r.json()
    assert view["name"] == "Директор Карпин" and view["count"] == staff.effect_of("director", "epic", config)
    assert view["budget"] == view["grant"] * 2  # capped
    for need in view["needs"]:
        assert len(need["options"]) <= view["count"]
        assert all(o["can_loan"] or o["can_buy"] for o in need["options"])


async def test_staff_conflict_needs_both_roles(client, db_session, bot_token):
    config = await get_config(db_session)
    uid, headers, club_id = await _setup(client, db_session, bot_token, 899807)
    club = await _club_row(db_session, club_id)
    round_ = int(finance.cfg(config)["conflict_rounds"][0])
    league = SimpleNamespace(id=1, season_key="2099-W03", rounds_played=round_)
    await conflicts.after_round(db_session, club, league, config)
    assert not (await db_session.execute(select(ManagerEvent).where(ManagerEvent.club_id == club_id))).scalars().all()
    for role, name in (("physio", "Доктор Ватсон"), ("coach", "Тренер Петрович")):
        rid = await _resident(db_session, uid, "rare", name)
        assert (await client.post(f"{API}/manager/staff/hire", headers=headers, json={"resident_id": rid, "role": role})).status_code == 200
    club = await _club_row(db_session, club_id)
    await conflicts.after_round(db_session, club, league, config)
    await conflicts.after_round(db_session, club, league, config)  # one per round
    rows = (await db_session.execute(select(ManagerEvent).where(ManagerEvent.club_id == club_id))).scalars().all()
    assert len(rows) == 1 and rows[0].code == "conflict_injury" and rows[0].slot == conflicts.CONFLICT_SLOT + round_
    assert "Ватсон" in rows[0].data["text"] and "Петрович" in rows[0].data["text"]
    # Not after another round.
    league.rounds_played = round_ + 1
    await conflicts.after_round(db_session, club, league, config)
    assert len((await db_session.execute(select(ManagerEvent).where(ManagerEvent.club_id == club_id))).scalars().all()) == 1


async def test_today_items_carry_a_target(client, db_session, bot_token):
    uid, headers, club_id = await _setup(client, db_session, bot_token, 899808)
    summary = (await client.get(f"{API}/manager/summary", headers=headers)).json()
    assert summary["today"] and all(i.get("target") for i in summary["today"])
    assert any(i["code"] == "budget" and i["tab"] == "office" for i in summary["today"])
    steps = summary["club"]["checklist"]["steps"]
    assert all("tab" in s for s in steps)
