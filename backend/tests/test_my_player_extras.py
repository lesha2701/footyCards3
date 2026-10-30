"""«Мой игрок» extras: «Спонсор», celebrations' prices, numbered limited
items, gifts to friends (Stars only), the trophy cabinet and «Зал славы»."""
import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.career import Friendship
from app.models.enums import NotificationType, TransactionType
from app.models.my_player_extras import MyPlayerEdition, MyPlayerGift, MyPlayerSponsorContract
from app.models.notification import Notification
from app.models.player_career import PlayerCareerClubRecord
from app.models.user import User
from app.services import my_player_extras, wallet_service
from app.services.game_config_service import get_config
from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1"
LOOK = {"skin": 2, "hair": 12, "hair_color": 1, "beard": 1, "eye_color": 3, "kit": 4, "kit_pattern": 1}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _player(client, db_session, bot_token, tg_id, balance=20_000):
    headers = telegram_headers(tg_id, bot_token)
    await client.post(f"{API}/auth/session", headers=headers)
    resp = await client.post(f"{API}/my-player", headers=headers, json={
        "name": "Игрок " + "АБВГДЕЖЗИК"[tg_id % 10], "number": 9, "position": "ST", "appearance": LOOK,
    })
    assert resp.status_code == 200, resp.text
    user = await get_user_by_telegram_id(db_session, tg_id)
    user.balance = balance
    await db_session.commit()
    return user.id, headers


async def _befriend(db_session, a_id, b_id):
    db_session.add(Friendship(requester_id=a_id, addressee_id=b_id, user_low=min(a_id, b_id), user_high=max(a_id, b_id), status="accepted"))
    await db_session.commit()


async def _stars(client, monkeypatch, headers, tg_id, charge, **body):
    from app.services import stars_payment_service
    from tests.test_gifts import _deliver, _fake_invoice_link

    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    resp = await client.post(f"{API}/my-player/stars-invoice", headers=headers, json=body)
    if resp.status_code != 200:
        return resp
    token, stars = resp.json()["payload_token"], resp.json()["stars_amount"]
    delivered = await _deliver(client, token, tg_id, charge, stars)
    assert delivered.status_code == 200, delivered.text
    return delivered


async def test_sponsor_week_goals_bonus_and_premium_top_up(client, db_session, bot_token, monkeypatch):
    user_id, headers = await _player(client, db_session, bot_token, 890001)
    view = (await client.get(f"{API}/my-player/sponsor", headers=headers)).json()
    assert len(view["offers"]) == 3 and view["contract"] is None
    assert (await client.get(f"{API}/my-player", headers=headers)).json()["attention"]["sponsor"] is True
    brand = view["offers"][0]
    assert [g["premium_only"] for g in brand["goals"]] == [False, False, False, True]
    assert (await client.post(f"{API}/my-player/sponsor", headers=headers, json={"brand": "nobody"})).status_code == 409

    view = (await client.post(f"{API}/my-player/sponsor", headers=headers, json={"brand": brand["code"]})).json()
    assert view["contract"]["code"] == brand["code"] and view["contract"]["premium"] is False
    assert (await client.post(f"{API}/my-player/sponsor", headers=headers, json={"brand": brand["code"]})).status_code == 409
    goals = [g["code"] for g in view["contract"]["goals"]]
    assert view["contract"]["goals"][3]["locked"] is True
    # The kit shows the sponsor.
    assert (await client.get(f"{API}/my-player", headers=headers)).json()["sponsor"]["code"] == brand["code"]

    config = await get_config(db_session)
    specs = config.my_player_sponsor_goals
    # Not done yet.
    assert (await client.post(f"{API}/my-player/sponsor/claim", headers=headers, json={"goal": goals[0]})).status_code == 409
    user = await wallet_service.lock_user_for_update(db_session, user_id)
    for code in goals:
        await my_player_extras.progress(db_session, user_id, code, specs[code]["target"])
    await db_session.commit()
    # The fourth goal is premium-only.
    assert (await client.post(f"{API}/my-player/sponsor/claim", headers=headers, json={"goal": goals[3]})).status_code == 409
    assert (await client.post(f"{API}/my-player/sponsor/claim", headers=headers, json={"goal": "bonus"})).status_code == 409
    before = (await db_session.get(User, user_id)).balance
    for code in goals[:3]:
        resp = await client.post(f"{API}/my-player/sponsor/claim", headers=headers, json={"goal": code})
        assert resp.status_code == 200, resp.text
    assert (await client.post(f"{API}/my-player/sponsor/claim", headers=headers, json={"goal": goals[0]})).status_code == 409
    resp = await client.post(f"{API}/my-player/sponsor/claim", headers=headers, json={"goal": "bonus"})
    assert resp.status_code == 200, resp.text
    paid_free = sum(specs[c]["coins"] for c in goals[:3]) + config.my_player_sponsor_bonus_coins
    assert resp.json()["balance"] == before + paid_free

    # Premium (Stars): what was paid is topped up to ×premium_pct, the 4th goal opens.
    delivered = await _stars(client, monkeypatch, headers, 890001, "sp-1", purchase="sponsor")
    assert delivered.json()["my_player_result"]["kind"] == "sponsor"
    pct = config.my_player_sponsor_premium_pct
    await db_session.refresh(user)
    assert user.balance == before + paid_free * pct // 100
    view = (await client.get(f"{API}/my-player/sponsor", headers=headers)).json()
    assert view["contract"]["premium"] and view["contract"]["goals"][3]["locked"] is False
    resp = await client.post(f"{API}/my-player/sponsor/claim", headers=headers, json={"goal": goals[3]})
    assert resp.status_code == 200
    assert resp.json()["balance"] == before + paid_free * pct // 100 + specs[goals[3]]["coins"] * pct // 100
    # Premium twice: refused.
    again = await client.post(f"{API}/my-player/stars-invoice", headers=headers, json={"purchase": "sponsor"})
    assert again.status_code == 409


async def test_sponsor_hooks_count_rewarded_games_only_with_a_contract(client, db_session, bot_token):
    user_id, headers = await _player(client, db_session, bot_token, 890002)
    user = await wallet_service.lock_user_for_update(db_session, user_id)
    await wallet_service.credit_coins(db_session, user, 10, TransactionType.game_reward, "test")
    await db_session.commit()  # no contract — nothing to count, no error
    db_session.add(MyPlayerSponsorContract(
        user_id=user_id, week=my_player_extras.week_key(), brand="volt",
        goals=["game_reward", "training", "duel_win", "career_win"], progress={}, paid={},
    ))
    await db_session.commit()
    user = await wallet_service.lock_user_for_update(db_session, user_id)
    for _ in range(3):
        await wallet_service.credit_coins(db_session, user, 10, TransactionType.game_reward, "test")
    await wallet_service.credit_coins(db_session, user, 10, TransactionType.trade_coins_received, "test")
    await db_session.commit()
    contract = (await db_session.execute(select(MyPlayerSponsorContract).where(MyPlayerSponsorContract.user_id == user_id))).scalar_one()
    await db_session.refresh(contract)
    assert contract.progress == {"game_reward": 3}


async def test_celebrations_coins_only_for_the_simplest_and_numbered_limited(client, db_session, bot_token, monkeypatch):
    user_id, headers = await _player(client, db_session, bot_token, 890003)
    catalog = {c["code"]: c for c in (await client.get(f"{API}/my-player", headers=headers)).json()["cosmetics"]["catalog"]}
    celebrations = {c: v for c, v in catalog.items() if v["kind"] == "celebration"}
    assert [c for c, v in celebrations.items() if v["price"] > 0] == ["cel_fist"]
    assert celebrations["cel_siu"]["stars_price"] > 0 and celebrations["cel_siu"]["price"] == 0
    assert all(v["stars_price"] > 0 for c, v in celebrations.items() if c != "cel_fist")
    assert (await client.post(f"{API}/my-player/cosmetics/buy", headers=headers, json={"code": "cel_siu"})).status_code == 409
    resp = await client.post(f"{API}/my-player/cosmetics/buy", headers=headers, json={"code": "cel_fist"})
    assert resp.status_code == 200 and "cel_fist" in resp.json()["cosmetics"]["owned"]
    assert {"walkout", "showcase"} <= {c["kind"] for c in catalog.values()}

    gold = celebrations["cel_siu_gold"]
    assert gold["supply"] == 100 and gold["sold"] == 0 and gold["price"] == 0
    await _stars(client, monkeypatch, headers, 890003, "lim-1", purchase="cosmetic", code="cel_siu_gold")
    other_id, other_headers = await _player(client, db_session, bot_token, 890004)
    await _stars(client, monkeypatch, other_headers, 890004, "lim-2", purchase="cosmetic", code="cel_siu_gold")
    numbers = dict((await db_session.execute(select(MyPlayerEdition.user_id, MyPlayerEdition.number))).all())
    assert numbers == {user_id: 1, other_id: 2}
    item = next(c for c in (await client.get(f"{API}/my-player", headers=other_headers)).json()["cosmetics"]["catalog"]
                if c["code"] == "cel_siu_gold")
    assert item["owned"] and item["edition"] == 2 and item["sold"] == 2

    # Sold out: a new invoice is refused.
    config = await get_config(db_session)
    config.my_player_limited_supply = {**config.my_player_limited_supply, "cel_siu_gold": 2}
    await db_session.commit()
    _, third_headers = await _player(client, db_session, bot_token, 890005)
    resp = await client.post(f"{API}/my-player/stars-invoice", headers=third_headers, json={"purchase": "cosmetic", "code": "cel_siu_gold"})
    assert resp.status_code == 409 and "распродан" in resp.text


async def test_gifts_to_friends_for_stars_and_patron(client, db_session, bot_token, monkeypatch):
    sender_id, sender_headers = await _player(client, db_session, bot_token, 890006)
    friend_id, friend_headers = await _player(client, db_session, bot_token, 890007)
    stranger_id, _ = await _player(client, db_session, bot_token, 890008)
    assert (await client.get(f"{API}/my-player/gifts/{friend_id}", headers=sender_headers)).status_code == 409  # not a friend yet
    await _befriend(db_session, sender_id, friend_id)

    view = (await client.get(f"{API}/my-player/gifts", headers=sender_headers)).json()
    assert [f["user_id"] for f in view["friends"]] == [friend_id] and view["patron"]["level"] == 0
    options = (await client.get(f"{API}/my-player/gifts/{friend_id}", headers=sender_headers)).json()["options"]
    codes = {o["code"] for o in options}
    assert {"training", "cosmetic:cel_siu"} <= codes
    assert "cosmetic:cel_fist" not in codes  # coins-only items can't be gifted (gifts are Stars only)
    assert all(o["stars"] > 0 for o in options)

    bad = await client.post(f"{API}/my-player/stars-invoice", headers=sender_headers,
                            json={"purchase": "gift", "item_id": stranger_id, "code": "training"})
    assert bad.status_code == 409
    delivered = await _stars(client, monkeypatch, sender_headers, 890006, "gift-1", purchase="gift", item_id=friend_id, code="cosmetic:cel_siu")
    assert delivered.json()["my_player_result"]["kind"] == "gift"
    await _stars(client, monkeypatch, sender_headers, 890006, "gift-2", purchase="gift", item_id=friend_id, code="training")

    friend_view = (await client.get(f"{API}/my-player", headers=friend_headers)).json()
    assert "cel_siu" in friend_view["cosmetics"]["owned"] and friend_view["training"]["extra_credits"] == 1
    received = (await client.get(f"{API}/my-player/gifts", headers=friend_headers)).json()["received"]
    assert [g["kind"] for g in received] == ["training", "cosmetic"]
    note = (await db_session.execute(select(Notification).where(
        Notification.user_id == friend_id, Notification.type == NotificationType.my_player_gift,
    ))).scalars().all()
    assert len(note) == 2
    # Already owned: can't be gifted again.
    again = await client.post(f"{API}/my-player/stars-invoice", headers=sender_headers,
                              json={"purchase": "gift", "item_id": friend_id, "code": "cosmetic:cel_siu"})
    assert again.status_code == 409
    patron = (await client.get(f"{API}/my-player/gifts", headers=sender_headers)).json()["patron"]
    assert patron == {"level": 1, "name": "Меценат I", "sent": 2, "next_at": 5}
    public = (await client.get(f"{API}/my-player/users/{sender_id}", headers=friend_headers)).json()
    assert public["cabinet"]["patron"]["level"] == 1
    assert (await db_session.execute(select(MyPlayerGift))).scalars().all()[0].sender_id == sender_id


async def test_cabinet_and_hall_of_fame(client, db_session, bot_token):
    a_id, a_headers = await _player(client, db_session, bot_token, 890010)
    b_id, _ = await _player(client, db_session, bot_token, 890011)
    c_id, c_headers = await _player(client, db_session, bot_token, 890012)
    db_session.add_all([
        PlayerCareerClubRecord(user_id=a_id, club_key="x", club_name="X", seasons=2, matches=28, goals=20, assists=5, titles=1),
        PlayerCareerClubRecord(user_id=a_id, club_key="y", club_name="Y", seasons=1, matches=14, goals=6, assists=2, titles=0),
        PlayerCareerClubRecord(user_id=b_id, club_key="x", club_name="X", seasons=3, matches=42, goals=30, assists=1, titles=2),
    ])
    await db_session.commit()
    hall = (await client.get(f"{API}/my-player/hall-of-fame", headers=a_headers, params={"metric": "goals"})).json()
    assert [(e["user_id"], e["value"]) for e in hall["entries"]] == [(b_id, 30), (a_id, 26)]
    assert hall["me"] == {"place": 2, "value": 26}
    titles = (await client.get(f"{API}/my-player/hall-of-fame", headers=c_headers, params={"metric": "titles"})).json()
    assert titles["entries"][0]["user_id"] == b_id and titles["me"] is None
    assert (await client.get(f"{API}/my-player/hall-of-fame", headers=a_headers, params={"metric": "x"})).status_code == 409
    trophies = (await client.get(f"{API}/my-player/hall-of-fame", headers=a_headers, params={"metric": "golden_ball"})).json()
    assert trophies["entries"] == []

    resp = await client.post(f"{API}/my-player/cosmetics/buy", headers=a_headers, json={"code": "sc_marble"})
    assert resp.status_code == 200
    cabinet = resp.json()["cabinet"]
    assert cabinet["showcase"] == "sc_marble" and set(cabinet["totals"]) >= {"goals", "titles", "seasons"}


async def test_admin_validates_sponsor_config(client, db_session, bot_token):
    admin = await client.post(f"{API}/auth/session", headers=telegram_headers(999000001, bot_token))
    headers = {"Authorization": f"Bearer {admin.json()['admin_token']}"}
    config = await get_config(db_session)
    brands = [dict(b) for b in config.my_player_sponsors]
    brands[0] = {**brands[0], "goals": ["training", "training", "duel_win", "career_win"]}
    resp = await client.put(f"{API}/admin/games/config", headers=headers, json={"my_player_sponsors": brands})
    assert resp.status_code == 409 and "Спонсоры" in resp.text
    resp = await client.put(f"{API}/admin/games/config", headers=headers,
                            json={"my_player_sponsor_goals": {**config.my_player_sponsor_goals, "fly": {"target": 1, "coins": 1}}})
    assert resp.status_code == 409
    resp = await client.put(f"{API}/admin/games/config", headers=headers, json={"my_player_sponsor_stars": 59})
    assert resp.status_code == 200 and resp.json()["my_player_sponsor_stars"] == 59
