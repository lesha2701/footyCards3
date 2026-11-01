"""«Кубок менеджеров» and friendlies."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.exceptions import ConflictError, RateLimitedError
from app.models.manager_club import ManagerCup, ManagerLedger
from app.services import manager_cup as cup, manager_finance as finance, manager_service
from app.services.game_config_service import get_config
from tests.test_manager import API, M, _next_season_start, _no_season_at_the_real_clock, _reset_rate_limits  # noqa: F401
from tests.test_manager_finance import _club_row, _keep_loaded, _setup, _squad, _user  # noqa: F401

pytestmark = pytest.mark.usefixtures("trade_guards_off")


async def test_cup_draw_rounds_prizes_and_winner(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    clubs = [await _setup(client, db_session, bot_token, 899100 + i, name=f"Клуб {i}") for i in range(5)]
    start = _next_season_start(config)
    assert await manager_service.ensure_season(db_session, start)
    row = await db_session.get(ManagerCup, manager_service.season_key(start))
    assert row is not None and row.status == "active"
    # 5 clubs → a bracket of 8: three byes, one match in the first round, three rounds.
    first = row.state["rounds"][0]
    assert sum(1 for m in first if m["b"] is None) == 3 and len(first) == 4 and row.state["total"] == 3

    view = await cup.view(db_session, await _user(db_session, clubs[0][0]), start)
    assert view["cup"]["clubs"] == 5 and view["cup"]["mine"]["alive"] is True and view["cup"]["played"] == 0

    assert await cup.resolve(db_session, start + timedelta(days=6)) == 3
    row = await db_session.get(ManagerCup, manager_service.season_key(start), populate_existing=True)
    assert row.status == "finished" and row.state["winner"] in {c[2] for c in clubs}
    winner = row.state["winner"]
    paid = dict((await db_session.execute(
        select(ManagerLedger.club_id, func.sum(ManagerLedger.amount)).where(ManagerLedger.kind == "cup").group_by(ManagerLedger.club_id)
    )).all())
    grant = finance.grant_of((await _club_row(db_session, winner)).division, config)
    assert paid[winner] == grant * 40 // 100
    assert sorted(paid.values(), reverse=True)[1] == grant * 20 // 100  # the finalist
    # Resolving again pays nothing twice.
    assert await cup.resolve(db_session, start + timedelta(days=7)) == 0
    view = await cup.view(db_session, await _user(db_session, clubs[0][0]), start + timedelta(days=7))
    assert view["cup"]["winner"] and view["history"][0]["winner"] == view["cup"]["winner"]


async def test_friendly_plays_at_once_with_a_daily_limit(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    a_uid, a_headers, a_id = await _setup(client, db_session, bot_token, 899201, name="Совы")
    _b_uid, _b_headers, b_id = await _setup(client, db_session, bot_token, 899202, name="Ястребы")
    with pytest.raises(ConflictError):
        await cup.friendly(db_session, await _user(db_session, a_uid), a_id)
    resp = await client.post(f"{API}/manager/friendlies/{b_id}", headers=a_headers)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["match"]["home"] == "Совы" and out["match"]["hs"] >= 0
    assert sum(out["h2h"][k] for k in ("wins", "draws", "losses")) == 1
    limit = finance.cfg(config)["friendly_per_day"]
    assert out["left_today"] == limit - 1
    for _ in range(limit - 1):
        await cup.friendly(db_session, await _user(db_session, a_uid), b_id)
    with pytest.raises(RateLimitedError):
        await cup.friendly(db_session, await _user(db_session, a_uid), b_id)
    h2h = (await client.get(f"{API}/manager/friendlies/{b_id}", headers=a_headers)).json()
    assert len(h2h["h2h"]["last"]) == limit and h2h["left_today"] == 0


async def test_league_newspaper_and_its_picture(client, db_session, bot_token):
    from app.services import manager_news, share_card_service

    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    uid, headers, club_id = await _setup(client, db_session, bot_token, 899301, name="Совы")
    assert (await client.get(f"{API}/manager/news", headers=headers)).status_code == 404  # no season yet
    start = _next_season_start(config)
    assert await manager_service.ensure_season(db_session, start)
    league_id = (await _club_row(db_session, club_id)).league_id
    await manager_service.resolve_league(db_session, league_id, now=start + timedelta(hours=30))
    resp = await client.get(f"{API}/manager/news", headers=headers)
    assert resp.status_code == 200, resp.text
    page = resp.json()
    assert "Совы" in page["headline"] and page["my_place"] and page["leader"] and page["biggest"]
    assert len(page["rounds"]) >= 1 and all(m["hs"] >= 0 for m in page["matches"])
    lines = manager_news.lines_of(page, manager_service.money)
    image = share_card_service.render_manager_news(league=page["league"], date=page["date"], headline=page["headline"],
                                                   lines=lines, bot_username="victorfc_bot")
    assert image[:2] == b"\xff\xd8"  # a JPEG
