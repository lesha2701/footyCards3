"""«Менеджер» monetization: Stars passes, gifts, stadium skins, the champion poster."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.exceptions import ConflictError, NotFoundError
from app.models.manager_club import ManagerDeal, ManagerLeague, ManagerStock
from app.models.notification import Notification
from app.services import manager_finance as finance, manager_news, manager_perks as perks, manager_service, manager_shop
from app.services import share_card_service
from app.services.game_config_service import get_config
from tests.test_manager import API, M, _next_season_start, _no_season_at_the_real_clock, _reset_rate_limits  # noqa: F401
from tests.test_manager_finance import _club_row, _keep_loaded, _setup, _squad, _user  # noqa: F401

pytestmark = pytest.mark.usefixtures("trade_guards_off")


def _invoice(user_id: int, code: str, stars: int):
    return SimpleNamespace(user_id=user_id, my_player_purchase=f"manager:{code}", stars_amount=stars)


async def test_passes_are_sold_for_stars_and_stack(client, db_session, bot_token):
    config = await get_config(db_session)
    uid, headers, club_id = await _setup(client, db_session, bot_token, 899401)
    shop = (await client.get(f"{API}/manager", headers=headers)).json()["shop"]
    passes = {p["code"]: p for p in shop["passes"]}
    assert set(passes) == {"assistant", "analytics"} and not passes["assistant"]["active"]
    stars = passes["assistant"]["stars"]
    key, _title, _about, price = await manager_shop.stars_order(db_session, uid, "assistant", config)
    assert key == "manager:assistant" and price == stars > 0
    assert not (await manager_shop.validate_stars(db_session, _invoice(uid, "assistant", stars + 1), config))[0]
    assert (await manager_shop.validate_stars(db_session, _invoice(uid, "assistant", stars), config))[0]
    user = await _user(db_session, uid)
    await manager_shop.deliver_stars(db_session, user, _invoice(uid, "assistant", stars), config)
    await db_session.commit()
    first = perks.until(await _club_row(db_session, club_id), "assistant")
    await manager_shop.deliver_stars(db_session, user, _invoice(uid, "assistant", stars), config)
    await db_session.commit()
    club = await _club_row(db_session, club_id)
    assert perks.active(club, "assistant") and perks.until(club, "assistant") - first == timedelta(days=passes["assistant"]["days"])
    assert not perks.active(club, "analytics")


async def test_assistant_signs_the_forgotten_sponsor_and_reminds_once(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    uid, _headers, club_id = await _setup(client, db_session, bot_token, 899411)
    _other_uid, _h, other_id = await _setup(client, db_session, bot_token, 899412, name="Ястребы")
    club = await _club_row(db_session, club_id)
    perks.extend(club, "assistant", 30)
    await db_session.commit()
    start = _next_season_start(config)
    # The reminder comes only within remind_hours of the window's end, and only once.
    early = start - timedelta(hours=60)
    assert await perks.remind(db_session, early) == 0
    near = start - timedelta(hours=5)
    assert await perks.remind(db_session, near) == 1
    assert await perks.remind(db_session, near + timedelta(hours=1)) == 0
    notes = (await db_session.execute(select(Notification.title).where(Notification.user_id == uid))).scalars().all()
    assert any("Окно закрывается" in t for t in notes)

    assert await manager_service.ensure_season(db_session, start)
    key = manager_service.season_key(start)
    deals = (await db_session.execute(select(ManagerDeal).where(ManagerDeal.kind == "sponsor", ManagerDeal.season_key == key))).scalars().all()
    assert [d.club_id for d in deals] == [club_id]  # only the club with the assistant
    assert deals[0].data["assistant"] is True and deals[0].amount > 0
    assert other_id not in [d.club_id for d in deals]


async def test_analytics_breakdown_and_price_alerts(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    uid, headers, club_id = await _setup(client, db_session, bot_token, 899421)
    other_uid, _h, other_id = await _setup(client, db_session, bot_token, 899422, name="Ястребы")
    assert (await client.get(f"{API}/manager/analytics", headers=headers)).status_code == 403
    club = await _club_row(db_session, club_id)
    perks.extend(club, "analytics", 30)
    await db_session.commit()
    start = _next_season_start(config)
    assert await manager_service.ensure_season(db_session, start)
    out = (await client.get(f"{API}/manager/analytics", headers=headers)).json()
    opp = out["opponent"]
    assert opp is not None and opp["name"] and [line["line"] for line in opp["lines"]] == ["GK", "DEF", "MID", "FWD"]
    assert any(line["mine"] for line in opp["lines"]) and opp["record"]["played"] == 0

    # A listed club's price jumps after a round: the holder with the pass hears about it.
    db_session.add(ManagerStock(club_id=other_id, shares_total=1000, floated=100, unsold=0, pool=0, base=100, price=130))
    await db_session.commit()
    league = await db_session.get(ManagerLeague, (await _club_row(db_session, club_id)).league_id)
    from app.models.manager_club import ManagerShare

    db_session.add(ManagerShare(club_id=other_id, holder_club_id=club_id, shares=10, cost=1000))
    await db_session.commit()
    await perks.price_alerts(db_session, league, {other_id: 100}, config)
    await db_session.commit()
    notes = (await db_session.execute(select(Notification.title).where(Notification.user_id == uid))).scalars().all()
    assert any("+30%" in t and "Ястребы" in t for t in notes)
    # The owner of the listed club has no pass: no alert.
    others = (await db_session.execute(select(Notification.title).where(Notification.user_id == other_uid))).scalars().all()
    assert not any("Акции" in t for t in others)


async def test_gift_a_style_item_to_another_club(client, db_session, bot_token):
    config = await get_config(db_session)
    uid, headers, club_id = await _setup(client, db_session, bot_token, 899431)
    friend_uid, _h, friend_id = await _setup(client, db_session, bot_token, 899432, name="Ястребы")
    gifts = (await client.get(f"{API}/manager/gifts/{friend_id}", headers=headers)).json()
    codes = {i["code"] for i in gifts["items"]}
    assert "stands_tifo" in codes and "stadium_name" not in codes and all(i["stars"] > 0 for i in gifts["items"])
    item = next(i for i in gifts["items"] if i["code"] == "stands_tifo")
    with pytest.raises(ConflictError):  # not to oneself
        await manager_shop.stars_order(db_session, uid, f"gift:{club_id}:stands_tifo", config)
    with pytest.raises(NotFoundError):
        await manager_shop.stars_order(db_session, uid, "gift:999999:stands_tifo", config)
    key, _t, _a, price = await manager_shop.stars_order(db_session, uid, f"gift:{friend_id}:stands_tifo", config)
    assert key == f"manager:gift:{friend_id}:stands_tifo" and price == item["stars"]
    invoice = SimpleNamespace(user_id=uid, my_player_purchase=key, stars_amount=price)
    assert (await manager_shop.validate_stars(db_session, invoice, config))[0]
    await manager_shop.deliver_stars(db_session, await _user(db_session, uid), invoice, config)
    await db_session.commit()
    assert "stands_tifo" in await manager_shop.owned(db_session, friend_id)
    assert "stands_tifo" not in await manager_shop.owned(db_session, club_id)
    assert not (await manager_shop.validate_stars(db_session, invoice, config))[0]  # already there
    notes = (await db_session.execute(select(Notification.title).where(Notification.user_id == friend_uid))).scalars().all()
    assert any("Подарок" in t for t in notes)
    # The friend wears it.
    resp = await client.patch(f"{API}/manager/look", headers=_h, json={"stands": "tifo"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["club"]["look"]["stands"] == "tifo"
    resp = await client.patch(f"{API}/manager/look", headers=headers, json={"stands": "tifo"})
    assert resp.status_code == 409  # not bought by this club


async def test_champion_poster(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    uid, headers, club_id = await _setup(client, db_session, bot_token, 899441)
    assert (await client.get(f"{API}/manager/champion", headers=headers)).status_code == 404
    start = _next_season_start(config)
    assert await manager_service.ensure_season(db_session, start)
    league = await db_session.get(ManagerLeague, (await _club_row(db_session, club_id)).league_id)
    await manager_service.resolve_league(db_session, league.id, now=start + timedelta(days=6))
    league = await db_session.get(ManagerLeague, league.id, populate_existing=True)
    me = next(t for t in league.state["teams"] if t["club_id"] == club_id)
    if league.state.get("champion") != me["name"]:  # make the test club the champion whatever the dice said
        league.state = {**league.state, "champion": me["name"]}
        club = await _club_row(db_session, club_id)
        club.titles = max(1, club.titles)
        await db_session.commit()
    resp = await client.get(f"{API}/manager/champion", headers=headers)
    assert resp.status_code == 200, resp.text
    page = resp.json()
    assert page["club"] == me["name"] and page["style"] == "classic" and page["won"] + page["drawn"] + page["lost"] > 0
    for style in ("classic", "neon", "gold"):
        image = share_card_service.render_manager_champion(
            club=page["club"], league=page["league"], season=page["season_key"], record="10–2–3 · 32 очк.",
            lines=["Титулов клуба: 1"], style=style, bot_username="victorfc_bot")
        assert image[:2] == b"\xff\xd8"

