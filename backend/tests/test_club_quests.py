"""«Задания недели» клуба: goals scaled by club size, lazy completion,
budget reward + a reward every member claims."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.club import Club, ClubMember
from app.models.club_budget import ClubBudgetTransaction
from app.models.club_quest import ClubQuestCompletion, ClubQuestTemplate
from app.models.club_reward import ClubRewardGrant
from app.models.enums import ClubBudgetTransactionType, GameSessionStatus, Position
from app.models.game import GameSession
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest.fixture(autouse=True)
async def _seed(db_session):
    rate_limit_module._hits.clear()
    for position in (Position.GK, Position.GK, Position.LB, Position.LB, Position.CB, Position.CB, Position.RB,
                     Position.RB, Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM, Position.LW,
                     Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)
    db_session.add(ClubQuestTemplate(title="Сыграть вместе", metric="games", target_per_member=3,
                                     reward_budget=1500, reward_coins=150, sort_order=0))
    db_session.add(ClubQuestTemplate(title="Открыть паки", metric="packs", target_per_member=2,
                                     reward_budget=2000, reward_card_rarity="rare", sort_order=1))
    await db_session.commit()


async def _register(client, db_session, telegram_id, bot_token):
    headers = telegram_headers(telegram_id, bot_token)
    assert (await client.post("/api/v1/auth/session", headers=headers)).status_code == 200
    return headers, await get_user_by_telegram_id(db_session, telegram_id)


def _games(db_session, user_id, count):
    now = datetime.now(timezone.utc)
    for _ in range(count):
        db_session.add(GameSession(user_id=user_id, game_type="memory_sequence", status=GameSessionStatus.won, created_at=now))


async def test_quest_goal_scales_and_completes_once(client, db_session, bot_token):
    cap_h, captain = await _register(client, db_session, 910000, bot_token)
    club_id = (await client.post("/api/v1/clubs", headers=cap_h, json={
        "name": "Квестовый клуб", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000",
    })).json()["id"]
    m_h, member = await _register(client, db_session, 910001, bot_token)
    await client.post(f"/api/v1/clubs/{club_id}/join", headers=m_h)
    for row in (await db_session.execute(select(ClubMember).where(ClubMember.club_id == club_id))).scalars():
        row.joined_at = row.joined_at - timedelta(hours=1)
    await db_session.commit()
    budget = (await db_session.get(Club, club_id)).budget

    body = (await client.get("/api/v1/clubs/me/quests", headers=m_h)).json()
    games = next(q for q in body["quests"] if q["metric"] == "games")
    assert body["enabled"] and games["target"] == 6 and games["progress"] == 0 and not games["completed"]

    _games(db_session, captain.id, 2)
    _games(db_session, member.id, 3)
    await db_session.commit()
    games = next(q for q in (await client.get("/api/v1/clubs/me/quests", headers=m_h)).json()["quests"] if q["metric"] == "games")
    assert games["progress"] == 5 and not games["completed"]

    _games(db_session, member.id, 1)
    await db_session.commit()
    # Opening the club is enough to complete it.
    detail = (await client.get("/api/v1/clubs/me", headers=cap_h)).json()
    assert detail["budget"] == budget + 1500
    assert detail["rewards_unclaimed"] == 1
    body = (await client.get("/api/v1/clubs/me/quests", headers=m_h)).json()
    games = next(q for q in body["quests"] if q["metric"] == "games")
    assert games["completed"] and games["target"] == 6
    assert {m["user_id"]: m["games"] for m in body["members"]} == {captain.id: 2, member.id: 4}

    # Paid exactly once however often it's read.
    await client.get("/api/v1/clubs/me/quests", headers=cap_h)
    assert len((await db_session.execute(select(ClubQuestCompletion))).scalars().all()) == 1
    tx = (await db_session.execute(select(ClubBudgetTransaction).where(
        ClubBudgetTransaction.type == ClubBudgetTransactionType.quest_reward,
    ))).scalars().all()
    assert [t.amount for t in tx] == [1500]
    grant = (await db_session.execute(select(ClubRewardGrant))).scalar_one()
    assert grant.source == "quest" and grant.coins == 150

    claimed = await client.post(f"/api/v1/clubs/me/rewards/{grant.id}/claim", headers=m_h)
    assert claimed.status_code == 200 and claimed.json()["coins"] == 150


async def test_quests_switch_off(client, db_session, bot_token):
    from app.services.game_config_service import get_config

    cap_h, _captain = await _register(client, db_session, 910010, bot_token)
    await client.post("/api/v1/clubs", headers=cap_h, json={
        "name": "Без заданий", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000",
    })
    config = await get_config(db_session)
    config.club_quests_enabled = False
    await db_session.commit()
    body = (await client.get("/api/v1/clubs/me/quests", headers=cap_h)).json()
    assert body["enabled"] is False and body["quests"] == []
