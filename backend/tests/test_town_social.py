"""«Город»: residents' quests and guests (services/town_social_service.py):
daily quests paid once when done, visits, a like a day per town, gifts that
cost the guest more than they bring the owner and come with the rent."""
from sqlalchemy import select

from app.models.town import TownVisit, UserTownQuest
from app.services import town_social_service
from tests.test_town import API, _config, _login, _reset_rate_limits, _town  # noqa: F401

SOCIAL = {"quests_per_day": 3, "quest_coins": 60, "gift_price": 300, "gift_rent": 100,
          "gifts_per_day": 3, "gifts_received_per_day": 1}


async def _with_house(client, headers, code="surf"):
    bought = await client.post(f"{API}/town/houses/beach/{code}/buy", headers=headers, json={})
    assert bought.status_code == 200, bought.text


async def test_quests_are_given_once_a_day_and_paid_once_when_done(client, db_session, bot_token):
    await _config(db_session, town_districts={"beach": {"price": 0, "rent": 100}}, town_price_growth_pct=0,
                  town_social=SOCIAL)
    headers, user = await _login(client, db_session, bot_token, 990301, balance=0)
    await _with_house(client, headers)

    first = (await client.get(f"{API}/town/quests", headers=headers)).json()
    again = (await client.get(f"{API}/town/quests", headers=headers)).json()
    assert [q["id"] for q in first["quests"]] == [q["id"] for q in again["quests"]]
    assert len(first["quests"]) == 3
    kinds = [q["kind"] for q in first["quests"]]
    assert kinds[0] == "claim" and kinds[1] in ("visit", "like") and kinds[2].startswith("play:")
    claim = first["quests"][0]
    assert claim["label"] == "Собери ренту города" and claim["done"] is False and claim["reward_coins"] == 60

    assert (await client.post(f"{API}/town/quests/{claim['id']}/claim", headers=headers)).status_code == 409
    town = await _town(db_session, user.id)
    town.income_accrued = 5
    await db_session.commit()
    assert (await client.post(f"{API}/town/income/claim", headers=headers, json={})).status_code == 200

    paid = await client.post(f"{API}/town/quests/{claim['id']}/claim", headers=headers)
    assert paid.status_code == 200, paid.text
    assert paid.json()["paid"] == 60 and paid.json()["new_balance"] == 65
    assert paid.json()["quests"][0]["claimed"] is True
    assert (await client.post(f"{API}/town/quests/{claim['id']}/claim", headers=headers)).status_code == 409
    rows = (await db_session.execute(select(UserTownQuest).where(UserTownQuest.user_id == user.id))).scalars().all()
    assert len(rows) == 3


async def test_guests_visit_like_once_a_day_and_gift_with_the_rent(client, db_session, bot_token):
    await _config(db_session, town_districts={"beach": {"price": 0, "rent": 100}}, town_price_growth_pct=0,
                  town_social=SOCIAL)
    owner_headers, owner = await _login(client, db_session, bot_token, 990311, balance=0)
    guest_headers, guest = await _login(client, db_session, bot_token, 990312, balance=1000)
    other_headers, other = await _login(client, db_session, bot_token, 990313, balance=1000)
    await _with_house(client, owner_headers)

    listed = (await client.get(f"{API}/town/guests", headers=guest_headers)).json()
    assert [t["user_id"] for t in listed["towns"]] == [owner.id]
    assert listed["towns"][0]["houses"] == 1 and listed["gifts_left"] == 3

    view = await client.get(f"{API}/town/visit/{owner.id}", headers=guest_headers)
    assert view.status_code == 200, view.text
    beach = next(d for d in view.json()["districts"] if d["code"] == "beach")
    assert beach["owned"] == 1 and view.json()["can_gift"] is True
    assert (await client.get(f"{API}/town/visit/{owner.id}", headers=guest_headers)).status_code == 200
    assert (await client.get(f"{API}/town/visit/{other.id}", headers=guest_headers)).status_code == 404  # no town
    assert (await client.get(f"{API}/town/visit/{owner.id}", headers=owner_headers)).status_code == 409  # own town

    liked = await client.post(f"{API}/town/visit/{owner.id}/like", headers=guest_headers)
    assert liked.status_code == 200 and liked.json()["likes_today"] == 1 and liked.json()["liked"] is True
    assert (await client.post(f"{API}/town/visit/{owner.id}/like", headers=guest_headers)).status_code == 409

    gifted = await client.post(f"{API}/town/visit/{owner.id}/gift", headers=guest_headers)
    assert gifted.status_code == 200, gifted.text
    assert gifted.json()["new_balance"] == 700 and gifted.json()["gifted"] is True
    assert (await client.post(f"{API}/town/visit/{owner.id}/gift", headers=guest_headers)).status_code == 409
    # The town took its one gift of the day.
    assert (await client.post(f"{API}/town/visit/{owner.id}/gift", headers=other_headers)).status_code == 409

    town = await _town(db_session, owner.id)
    assert town.gifts_pending == 100
    state = (await client.get(f"{API}/town", headers=owner_headers)).json()
    assert state["income"]["gifts"] == 100 and state["income"]["pending"] >= 100
    claimed = await client.post(f"{API}/town/income/claim", headers=owner_headers, json={})
    assert claimed.status_code == 200 and claimed.json()["claimed"] >= 100
    assert (await _town(db_session, owner.id)).gifts_pending == 0

    visits = (await db_session.execute(select(TownVisit).where(TownVisit.visitor_id == guest.id))).scalars().all()
    assert len(visits) == 1 and visits[0].liked and visits[0].gift_coins == 100


def test_social_settings_are_validated():
    assert town_social_service.validate_social({"gift_price": 100, "gift_rent": 50}) == {"gift_price": 100, "gift_rent": 50}
    for bad in ({"gift_price": 10, "gift_rent": 50}, {"nope": 1}, {"quest_coins": -1}):
        try:
            town_social_service.validate_social(bad)
        except ValueError:
            continue
        raise AssertionError(bad)
    assert town_social_service.quest_label("play:arena", 2) == "Сыграй 2 раза в «Card Arena»"
    assert town_social_service.quest_label("visit", 2) == "Загляни в гости в 2 города"


async def test_town_week_counts_old_guests_and_pays_the_past_week_once(client, db_session, bot_token):
    from datetime import datetime, timedelta, timezone

    from app.models.transaction import CoinTransaction
    from app.models.town import TownWeekResult
    from app.core.timeutil import local_today

    await _config(db_session, town_districts={"beach": {"price": 0, "rent": 100}}, town_price_growth_pct=0,
                  town_social={**SOCIAL, "week_rewarded_places": 2, "week_reward_1": 500, "week_reward_2": 200})
    a_headers, a = await _login(client, db_session, bot_token, 990321, balance=0)
    b_headers, b = await _login(client, db_session, bot_token, 990322, balance=0)
    old_headers, old = await _login(client, db_session, bot_token, 990323, balance=0)
    fresh_headers, fresh = await _login(client, db_session, bot_token, 990324, balance=0)
    await _with_house(client, a_headers)
    await _with_house(client, b_headers)
    old.created_at = datetime.now(timezone.utc) - timedelta(days=30)
    await db_session.commit()

    last_week = local_today() - timedelta(days=7)
    db_session.add_all([
        TownVisit(visitor_id=old.id, owner_id=a.id, day=last_week, liked=True),
        TownVisit(visitor_id=old.id, owner_id=b.id, day=last_week, liked=False),
        TownVisit(visitor_id=fresh.id, owner_id=b.id, day=last_week, liked=True),  # a fresh account: not counted
    ])
    await db_session.commit()

    res = await client.get(f"{API}/town/week", headers=a_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["points"] == {"like": 10, "guest": 3, "house": 1}
    winners = body["last_week"]["winners"]
    assert [(w["user_id"], w["score"], w["coins"]) for w in winners] == [(a.id, 14, 500), (b.id, 4, 200)]
    assert body["last_week"]["mine"] == {"place": 1, "coins": 500}

    again = await client.get(f"{API}/town/week", headers=b_headers)
    assert again.status_code == 200
    rows = (await db_session.execute(select(TownWeekResult))).scalars().all()
    assert len(rows) == 2
    paid = (await db_session.execute(select(CoinTransaction).where(CoinTransaction.user_id == a.id,
                                                                   CoinTransaction.related_object_type == "town_week"))).scalars().all()
    assert len(paid) == 1

    # This week: a like from the old account puts the town on top.
    like = await client.post(f"{API}/town/visit/{b.id}/like", headers=old_headers)
    assert like.status_code == 200, like.text
    now = (await client.get(f"{API}/town/week", headers=b_headers)).json()
    assert now["top"][0]["user_id"] == b.id and now["top"][0]["score"] == 14 and now["top"][0]["reward"] == 500
    assert now["me"]["place"] == 1
    assert (await client.get(f"{API}/town/week", headers=fresh_headers)).json()["me"] is None
