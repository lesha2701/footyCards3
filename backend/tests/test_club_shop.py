"""«Клубный магазин» and club-wide rewards each member claims for themselves."""
from datetime import timedelta

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.club import Club, ClubMember
from app.models.club_reward import ClubRewardGrant, ClubShopItem
from app.models.enums import NotificationType, Position, TransactionType
from app.models.notification import Notification
from app.models.transaction import CoinTransaction
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest.fixture(autouse=True)
async def _seed(db_session):
    rate_limit_module._hits.clear()
    for position in (Position.GK, Position.GK, Position.LB, Position.LB, Position.CB, Position.CB, Position.RB,
                     Position.RB, Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM, Position.LW,
                     Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _register(client, db_session, telegram_id, bot_token):
    headers = telegram_headers(telegram_id, bot_token)
    assert (await client.post("/api/v1/auth/session", headers=headers)).status_code == 200
    return headers, await get_user_by_telegram_id(db_session, telegram_id)


async def _setup(client, db_session, bot_token, base_id):
    cap_h, captain = await _register(client, db_session, base_id, bot_token)
    club_id = (await client.post("/api/v1/clubs", headers=cap_h, json={
        "name": f"Клуб {base_id}", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000",
    })).json()["id"]
    m_h, member = await _register(client, db_session, base_id + 1, bot_token)
    await client.post(f"/api/v1/clubs/{club_id}/join", headers=m_h)
    # Joined a moment "earlier" than anything bought below.
    for row in (await db_session.execute(select(ClubMember).where(ClubMember.club_id == club_id))).scalars():
        row.joined_at = row.joined_at - timedelta(minutes=5)
    item = ClubShopItem(name="Премия команде", price=1000, weekly_limit=1, reward_coins=300)
    db_session.add(item)
    club = await db_session.get(Club, club_id)
    club.budget = 5000
    await db_session.commit()
    return club_id, item, cap_h, captain, m_h, member


async def test_buy_once_a_week_and_every_member_claims(client, db_session, bot_token):
    club_id, item, cap_h, captain, m_h, member = await _setup(client, db_session, bot_token, 900000)

    shop = (await client.get("/api/v1/clubs/me/shop", headers=m_h)).json()
    assert shop["can_buy"] is False and shop["member_count"] == 2
    entry = next(i for i in shop["items"] if i["id"] == item.id)
    assert entry["reward"]["coins"] == 300 and entry["bought_this_week"] == 0
    assert (await client.post(f"/api/v1/clubs/me/shop/{item.id}/buy", headers=m_h)).status_code == 403

    resp = await client.post(f"/api/v1/clubs/me/shop/{item.id}/buy", headers=cap_h)
    assert resp.status_code == 200, resp.text
    assert resp.json()["budget"] == 4000
    assert (await client.post(f"/api/v1/clubs/me/shop/{item.id}/buy", headers=cap_h)).status_code == 409

    notes = (await db_session.execute(select(Notification).where(
        Notification.type == NotificationType.club_reward_available,
    ))).scalars().all()
    assert {n.user_id for n in notes} == {captain.id, member.id}

    rewards = (await client.get("/api/v1/clubs/me/shop", headers=m_h)).json()["rewards"]
    assert len(rewards) == 1 and rewards[0]["title"] == "Премия команде"
    assert (await client.get("/api/v1/clubs/me", headers=m_h)).json()["rewards_unclaimed"] == 1

    balance = member.balance
    claimed = await client.post(f"/api/v1/clubs/me/rewards/{rewards[0]['id']}/claim", headers=m_h)
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["coins"] == 300 and claimed.json()["new_balance"] == balance + 300
    assert (await client.post(f"/api/v1/clubs/me/rewards/{rewards[0]['id']}/claim", headers=m_h)).status_code == 409
    assert (await client.get("/api/v1/clubs/me", headers=m_h)).json()["rewards_unclaimed"] == 0
    tx = (await db_session.execute(select(CoinTransaction).where(
        CoinTransaction.user_id == member.id, CoinTransaction.type == TransactionType.club_reward,
    ))).scalar_one()
    assert tx.amount == 300

    assert (await client.post(f"/api/v1/clubs/me/rewards/{rewards[0]['id']}/claim", headers=cap_h)).status_code == 200


async def test_late_joiner_cannot_claim_earlier_rewards(client, db_session, bot_token):
    club_id, item, cap_h, _captain, _m_h, _member = await _setup(client, db_session, bot_token, 900010)
    await client.post(f"/api/v1/clubs/me/shop/{item.id}/buy", headers=cap_h)
    grant = (await db_session.execute(select(ClubRewardGrant))).scalar_one()

    late_h, _late = await _register(client, db_session, 900019, bot_token)
    await client.post(f"/api/v1/clubs/{club_id}/join", headers=late_h)
    assert (await client.get("/api/v1/clubs/me/shop", headers=late_h)).json()["rewards"] == []
    assert (await client.post(f"/api/v1/clubs/me/rewards/{grant.id}/claim", headers=late_h)).status_code == 409


async def test_insufficient_budget_and_admin_crud(client, db_session, bot_token):
    club_id, item, cap_h, *_ = await _setup(client, db_session, bot_token, 900020)
    club = await db_session.get(Club, club_id)
    club.budget = 10
    await db_session.commit()
    assert (await client.post(f"/api/v1/clubs/me/shop/{item.id}/buy", headers=cap_h)).status_code != 200

    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(999000001, bot_token))
    admin = {"Authorization": f"Bearer {resp.json()['admin_token']}"}
    body = {"name": "Сборы", "description": "", "price": 7000, "weekly_limit": 2,
            "reward": {"coins": 0, "card_rarity": "rare"}, "is_active": True, "sort_order": 5}
    created = await client.post("/api/v1/admin/club-shop-items", headers=admin, json=body)
    assert created.status_code == 200, created.text
    assert created.json()["reward"]["card_rarity"] == "rare"
    empty = await client.post("/api/v1/admin/club-shop-items", headers=admin, json={**body, "reward": {"coins": 0}})
    assert empty.status_code == 409
    upd = await client.put(f"/api/v1/admin/club-shop-items/{created.json()['id']}", headers=admin, json={**body, "is_active": False})
    assert upd.json()["is_active"] is False
    shop = (await client.get("/api/v1/clubs/me/shop", headers=cap_h)).json()
    assert all(i["name"] != "Сборы" for i in shop["items"])
