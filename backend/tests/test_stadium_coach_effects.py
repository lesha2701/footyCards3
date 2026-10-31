"""Stadiums and coaches against the opponent (Card Arena), their card
collections and «Карты за звёзды» for coaches, stadiums and Muses."""
from types import SimpleNamespace as NS

from sqlalchemy import func, select

import app.core.rate_limit as rate_limit_module
from app.models.card_collection import CardCollection, UserCollectionReward
from app.models.coach import Coach, CoachBoost
from app.models.enums import CoachBoostType, Rarity
from app.models.muse import Muse, UserMuse
from app.models.pack import StarsInvoice
from app.models.stadium import Stadium
from app.models.user_coach_card import UserCoachCard
from app.models.user_stadium_card import UserStadiumCard
from app.services import coach_boost_service, coach_service, shop_product_service
from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers

ADMIN = "/api/v1/admin/card-offers"


def _coach(*boosts):
    return NS(boosts=[NS(boost_type=t, magnitude=m) for t, m in boosts])


def test_opponent_malus_sums_coach_and_stadium():
    coach = _coach((CoachBoostType.OPP_ATTACK, 4), (CoachBoostType.OPP_TEAM, 2), (CoachBoostType.DEFENCE_CENTRAL, 8))
    assert coach_boost_service.arena_opponent_malus(coach, 5) == {"FWD": 11, "MID": 7, "DEF": 7, "GK": 7}
    assert coach_boost_service.arena_opponent_malus(None, 0) == {}
    assert coach_boost_service.arena_opponent_malus(None, 5) == {"FWD": 5, "MID": 5, "DEF": 5, "GK": 5}


def test_malus_lowers_lines_and_strength_in_proportion():
    strength, lines = coach_boost_service.apply_opponent_malus(800, {"FWD": 80, "MID": 80, "DEF": 80, "GK": 80}, {"FWD": 8})
    assert lines == {"FWD": 72, "MID": 80, "DEF": 80, "GK": 80}
    assert strength == 780  # the average fell by 2 of 80 → −2.5 %
    assert coach_boost_service.apply_opponent_malus(800, {"FWD": 80}, {}) == (800, {"FWD": 80})


def test_team_rating_and_effect_lines():
    mourinho = NS(boosts=[
        NS(boost_type=CoachBoostType.OPP_ATTACK, magnitude=4), NS(boost_type=CoachBoostType.OPP_TEAM, magnitude=2),
        NS(boost_type=CoachBoostType.TEAM_RATING, magnitude=2),
    ])
    assert coach_boost_service.arena_team_rating_bonus(mourinho) == 2
    assert coach_service.coach_effect_lines(mourinho) == [
        "−4 к атаке соперника", "−2 к рейтингу соперника", "+2 к рейтингу всей команды",
    ]
    assert coach_service.magnitude_for(CoachBoostType.OPP_ATTACK, Rarity.legendary) == 4


async def _user(client, db_session, bot_token, telegram_id):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    return headers, await get_user_by_telegram_id(db_session, telegram_id)


async def _admin(client, bot_token):
    rate_limit_module._hits.clear()
    session = await client.post("/api/v1/auth/session", headers=telegram_headers(999000001, bot_token))
    return {"Authorization": f"Bearer {session.json()['admin_token']}"}


async def _buy(client, db_session, admin, user, offer_json, token):
    created = await client.post(ADMIN, headers=admin, json={**offer_json, "stars_price": 100, "per_user_limit": 0})
    assert created.status_code == 200, created.text
    invoice = StarsInvoice(user_id=user.id, payload_token=token, stars_amount=100,
                           shop_product=f"card_offer:{created.json()['id']}")
    db_session.add(invoice)
    await db_session.flush()
    ok, reason = await shop_product_service.validate(db_session, invoice)
    assert ok, reason
    await shop_product_service.deliver(db_session, user, invoice, f"charge-{token}")
    await db_session.commit()
    return created.json()


async def test_coach_stadium_and_muse_sell_for_stars_and_complete_a_collection(client, db_session, bot_token):
    admin = await _admin(client, bot_token)
    collection = CardCollection(name="Ночь живых Легенд (тест)", reward_coins=777)
    db_session.add(collection)
    await db_session.flush()
    coach = Coach(display_name="Жозе (тест)", rarity=Rarity.legendary, collection_id=collection.id)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.OPP_ATTACK, magnitude=4)]
    stadium = Stadium(display_name="Проклятый (тест)", rarity=Rarity.legendary, boost_pct=0, opp_malus=5,
                      collection_id=collection.id)
    muse = Muse(name="Муза (тест)", effect="daily_coins", effect_value=100)
    db_session.add_all([coach, stadium, muse])
    await db_session.commit()

    headers, user = await _user(client, db_session, bot_token, 991001)
    balance = user.balance
    offer = await _buy(client, db_session, admin, user, {"coach_id": coach.id}, "sc-1")
    assert offer["kind"] == "coach" and offer["item"]["effects"] == ["−4 к атаке соперника"]
    shop = (await client.get("/api/v1/card-offers", headers=headers)).json()
    assert shop[0]["kind"] == "coach" and shop[0]["player"] is None and shop[0]["item"]["name"] == "Жозе (тест)"
    assert (await db_session.execute(select(func.count()).select_from(UserCollectionReward))).scalar_one() == 0

    # The stadium completes the collection (2 of 2): its reward is paid.
    await _buy(client, db_session, admin, user, {"stadium_id": stadium.id}, "sc-2")
    await _buy(client, db_session, admin, user, {"muse_id": muse.id}, "sc-3")
    owned = [
        (await db_session.execute(select(func.count()).select_from(model).where(model.user_id == user.id))).scalar_one()
        for model in (UserCoachCard, UserStadiumCard, UserMuse)
    ]
    assert owned == [1, 1, 1]
    await db_session.refresh(user)
    assert user.balance == balance + 777

    album = (await client.get(f"/api/v1/collection/album/{collection.id}", headers=headers)).json()
    assert album["is_complete"] and {s["kind"]: s["owned"] for s in album["staff"]} == {"coach": True, "stadium": True}
    assert "−5 к рейтингу соперника" in next(s for s in album["staff"] if s["kind"] == "stadium")["effects"]

    bad = await client.post(ADMIN, headers=admin, json={"coach_id": coach.id, "stadium_id": stadium.id, "stars_price": 5})
    assert bad.status_code == 409
