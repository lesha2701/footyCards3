from datetime import datetime, timezone

from sqlalchemy import select

from app.models.enums import TaskCategory, TaskConditionType
from app.models.task import TaskDefinition, UserTask
from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def _admin_auth(client, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    token = session_resp.json()["admin_token"]
    return {"Authorization": f"Bearer {token}"}


async def _create_regular_tasks(db_session, count: int) -> list[TaskDefinition]:
    tasks = []
    for i in range(count):
        t = TaskDefinition(
            code=f"regular_{i}", name=f"Task {i}", description="test task",
            category=TaskCategory.regular, condition_type=TaskConditionType.metric_counter,
            metric="packs_opened", target_value=1, reward_coins=10 + i,
        )
        db_session.add(t)
        tasks.append(t)
    await db_session.commit()
    for t in tasks:
        await db_session.refresh(t)
    return tasks


async def test_list_tasks_assigns_five_regular_slots(client, db_session, bot_token):
    await _create_regular_tasks(db_session, 8)
    await _register(client, db_session, 810001, bot_token)
    headers = telegram_headers(810001, bot_token)

    resp = await client.get("/api/v1/tasks", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["regular"]) == 5
    assert len({t["code"] for t in body["regular"]}) == 5


async def test_list_tasks_returns_fewer_than_five_when_pool_is_small(client, db_session, bot_token):
    await _create_regular_tasks(db_session, 3)
    await _register(client, db_session, 810002, bot_token)
    headers = telegram_headers(810002, bot_token)

    resp = await client.get("/api/v1/tasks", headers=headers)
    assert len(resp.json()["regular"]) == 3


async def _complete(db_session, user_task_id):
    user_task = await db_session.get(UserTask, user_task_id)
    user_task.progress = 1
    user_task.completed_at = datetime.now(timezone.utc)
    db_session.add(user_task)
    await db_session.commit()


async def test_claim_regular_task_credits_coins_and_keeps_it_as_done(client, db_session, bot_token):
    await _create_regular_tasks(db_session, 6)
    user = await _register(client, db_session, 810003, bot_token)
    headers = telegram_headers(810003, bot_token)

    tasks_before = (await client.get("/api/v1/tasks", headers=headers)).json()["regular"]
    target = tasks_before[0]
    await _complete(db_session, target["user_task_id"])

    claim_resp = await client.post(f"/api/v1/tasks/{target['user_task_id']}/claim", headers=headers)
    assert claim_resp.status_code == 200
    body = claim_resp.json()
    assert body["reward_coins"] == target["reward_coins"]
    assert body["refilled_task"] is None
    assert body["points_added"] == 20

    await db_session.refresh(user)
    assert user.balance == 500 + target["reward_coins"]

    after = (await client.get("/api/v1/tasks", headers=headers)).json()
    # The day's set is not refilled: the claimed task stays, shown as done.
    assert [t["code"] for t in after["regular"]] == [t["code"] for t in tasks_before]
    assert next(t for t in after["regular"] if t["code"] == target["code"])["is_claimed"] is True
    assert after["daily_track"]["points"] == 20
    assert after["daily_track"]["chests"][0]["is_available"] is True


async def test_tasks_renew_on_a_new_day(client, db_session, bot_token):
    await _create_regular_tasks(db_session, 6)
    await _register(client, db_session, 810020, bot_token)
    headers = telegram_headers(810020, bot_token)

    first = (await client.get("/api/v1/tasks", headers=headers)).json()["regular"]
    target = first[0]
    await _complete(db_session, target["user_task_id"])
    assert (await client.post(f"/api/v1/tasks/{target['user_task_id']}/claim", headers=headers)).status_code == 200

    # Pretend the set was handed out yesterday.
    rows = (await db_session.execute(select(UserTask).where(UserTask.slot_index.isnot(None)))).scalars().all()
    for row in rows:
        row.period_key = "2000-01-01"
        db_session.add(row)
    await db_session.commit()

    renewed = (await client.get("/api/v1/tasks", headers=headers)).json()
    assert len(renewed["regular"]) == 5
    assert all(not t["is_claimed"] and not t["is_completed"] for t in renewed["regular"])


async def test_weekly_tasks_get_their_own_slots(client, db_session, bot_token):
    await _create_regular_tasks(db_session, 6)
    for i in range(4):
        db_session.add(TaskDefinition(
            code=f"weekly_{i}", name=f"Week {i}", description="", category=TaskCategory.regular,
            condition_type=TaskConditionType.metric_counter, metric="packs_opened", target_value=5,
            reward_coins=100, period="weekly", points=30,
        ))
    await db_session.commit()
    await _register(client, db_session, 810021, bot_token)

    body = (await client.get("/api/v1/tasks", headers=telegram_headers(810021, bot_token))).json()
    assert len(body["regular"]) == 5 and all(t["period"] == "daily" for t in body["regular"])
    assert len(body["weekly"]) == 3 and all(t["period"] == "weekly" for t in body["weekly"])
    assert body["weekly"][0]["route"] == "/packs"
    assert len(body["weekly_track"]["chests"]) == 3


async def test_chest_opens_once_after_its_threshold(client, db_session, bot_token):
    await _create_regular_tasks(db_session, 6)
    user = await _register(client, db_session, 810022, bot_token)
    headers = telegram_headers(810022, bot_token)

    closed = await client.post("/api/v1/tasks/chests/daily/0/claim", headers=headers)
    assert closed.status_code == 409

    tasks = (await client.get("/api/v1/tasks", headers=headers)).json()["regular"]
    await _complete(db_session, tasks[0]["user_task_id"])
    await client.post(f"/api/v1/tasks/{tasks[0]['user_task_id']}/claim", headers=headers)
    await db_session.refresh(user)
    balance = user.balance

    opened = await client.post("/api/v1/tasks/chests/daily/0/claim", headers=headers)
    assert opened.status_code == 200
    assert opened.json()["rewards"]["coins"] == 100
    await db_session.refresh(user)
    assert user.balance == balance + 100

    again = await client.post("/api/v1/tasks/chests/daily/0/claim", headers=headers)
    assert again.status_code == 409
    still_closed = await client.post("/api/v1/tasks/chests/daily/1/claim", headers=headers)
    assert still_closed.status_code == 409

    track = (await client.get("/api/v1/tasks", headers=headers)).json()["daily_track"]
    assert track["chests"][0]["is_claimed"] is True


async def test_reroll_swaps_a_daily_task_once_a_day(client, db_session, bot_token):
    await _create_regular_tasks(db_session, 8)
    await _register(client, db_session, 810023, bot_token)
    headers = telegram_headers(810023, bot_token)

    body = (await client.get("/api/v1/tasks", headers=headers)).json()
    assert body["rerolls_left"] == 1
    codes = {t["code"] for t in body["regular"]}
    target = body["regular"][2]

    resp = await client.post(f"/api/v1/tasks/{target['user_task_id']}/reroll", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["rerolls_left"] == 0
    assert resp.json()["task"]["code"] not in codes

    after = (await client.get("/api/v1/tasks", headers=headers)).json()
    assert after["rerolls_left"] == 0
    assert after["regular"][2]["code"] == resp.json()["task"]["code"]

    second = await client.post(f"/api/v1/tasks/{after['regular'][0]['user_task_id']}/reroll", headers=headers)
    assert second.status_code == 409


async def test_completed_task_cannot_be_rerolled(client, db_session, bot_token):
    await _create_regular_tasks(db_session, 8)
    await _register(client, db_session, 810024, bot_token)
    headers = telegram_headers(810024, bot_token)

    target = (await client.get("/api/v1/tasks", headers=headers)).json()["regular"][0]
    await _complete(db_session, target["user_task_id"])
    resp = await client.post(f"/api/v1/tasks/{target['user_task_id']}/reroll", headers=headers)
    assert resp.status_code == 409


async def test_claim_regular_task_twice_is_rejected(client, db_session, bot_token):
    await _create_regular_tasks(db_session, 6)
    await _register(client, db_session, 810004, bot_token)
    headers = telegram_headers(810004, bot_token)

    tasks = (await client.get("/api/v1/tasks", headers=headers)).json()["regular"]
    target = tasks[0]

    user_task = await db_session.get(UserTask, target["user_task_id"])
    user_task.completed_at = datetime.now(timezone.utc)
    db_session.add(user_task)
    await db_session.commit()

    first = await client.post(f"/api/v1/tasks/{target['user_task_id']}/claim", headers=headers)
    assert first.status_code == 200
    second = await client.post(f"/api/v1/tasks/{target['user_task_id']}/claim", headers=headers)
    assert second.status_code == 409


async def test_task_reward_pack_grants_all_cards(client, db_session, bot_token):
    from app.models.enums import Rarity
    from tests.factories import create_pack, create_player

    for _ in range(3):
        await create_player(db_session, rarity=Rarity.common)
    pack = await create_pack(db_session, "task-reward-pack", price=0, card_count=3, probabilities={Rarity.common: 1.0})

    db_session.add(
        TaskDefinition(
            code="task_pack_reward", name="Task pack reward", description="test",
            category=TaskCategory.regular, condition_type=TaskConditionType.metric_counter,
            target_value=0, reward_coins=0, reward_pack_id=pack.id,
        )
    )
    await db_session.commit()

    await _register(client, db_session, 810013, bot_token)
    headers = telegram_headers(810013, bot_token)

    tasks = (await client.get("/api/v1/tasks", headers=headers)).json()["regular"]
    target = next(t for t in tasks if t["code"] == "task_pack_reward")

    resp = await client.post(f"/api/v1/tasks/{target['user_task_id']}/claim", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    # Previously only the last rolled card was returned even though the pack
    # grants card_count cards — all of them must come back, not just one.
    assert body["granted_pack"] is not None
    assert body["granted_pack"]["pack"]["name"] == "Task-Reward-Pack"
    assert len(body["granted_pack"]["cards"]) == 3


async def test_claim_incomplete_task_is_rejected(client, db_session, bot_token):
    await _create_regular_tasks(db_session, 6)
    await _register(client, db_session, 810005, bot_token)
    headers = telegram_headers(810005, bot_token)

    tasks = (await client.get("/api/v1/tasks", headers=headers)).json()["regular"]
    resp = await client.post(f"/api/v1/tasks/{tasks[0]['user_task_id']}/claim", headers=headers)
    assert resp.status_code == 409


async def test_premium_task_claim_blocked_without_subscription(client, db_session, bot_token, monkeypatch):
    async def fake_not_subscribed(*args, **kwargs):
        return False

    monkeypatch.setattr("app.services.task_service.check_channel_membership", fake_not_subscribed)

    db_session.add(
        TaskDefinition(
            code="premium_test", name="Premium", description="test", category=TaskCategory.premium,
            condition_type=TaskConditionType.metric_counter, target_value=0, reward_coins=0,
            channel_username="@test_channel",
        )
    )
    await db_session.commit()

    await _register(client, db_session, 810006, bot_token)
    headers = telegram_headers(810006, bot_token)

    tasks = (await client.get("/api/v1/tasks", headers=headers)).json()
    premium_task = tasks["premium"][0]
    assert premium_task["is_completed"] is True

    resp = await client.post(f"/api/v1/tasks/{premium_task['user_task_id']}/claim", headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"
    assert "details" in resp.json()["error"]
    assert resp.json()["error"]["details"]["channel_username"] == "@test_channel"


async def test_premium_task_claim_succeeds_when_subscribed(client, db_session, bot_token, monkeypatch):
    async def fake_subscribed(*args, **kwargs):
        return True

    monkeypatch.setattr("app.services.task_service.check_channel_membership", fake_subscribed)

    db_session.add(
        TaskDefinition(
            code="premium_test2", name="Premium 2", description="test", category=TaskCategory.premium,
            condition_type=TaskConditionType.metric_counter, target_value=0, reward_coins=77,
            channel_username="@test_channel2",
        )
    )
    await db_session.commit()

    user = await _register(client, db_session, 810007, bot_token)
    headers = telegram_headers(810007, bot_token)

    tasks = (await client.get("/api/v1/tasks", headers=headers)).json()
    premium_task = tasks["premium"][0]

    resp = await client.post(f"/api/v1/tasks/{premium_task['user_task_id']}/claim", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["reward_coins"] == 77

    await db_session.refresh(user)
    assert user.balance == 577


async def test_premium_task_reclaimable_after_bot_resets_it_on_clawback(client, db_session, bot_token, monkeypatch):
    """The premium-subscription clawback sweep (bot/services/premium_subscription_check.py,
    bot/db.py's reset_task_for_reclaim) resets a withdrawn task's row straight in Postgres —
    reward_claimed=False, reward_coins_granted=NULL, coins_withdrawn=False, completed_at
    untouched — to make it claimable again without going through this backend at all. This
    proves claim_task_reward correctly treats that reset state exactly like a fresh
    never-claimed completion: still-completed, not-yet-claimed, live membership re-checked."""
    async def fake_subscribed(*args, **kwargs):
        return True

    monkeypatch.setattr("app.services.task_service.check_channel_membership", fake_subscribed)

    db_session.add(
        TaskDefinition(
            code="premium_reclaim_test", name="Premium Reclaim", description="test", category=TaskCategory.premium,
            condition_type=TaskConditionType.metric_counter, target_value=0, reward_coins=77,
            channel_username="@test_channel_reclaim",
        )
    )
    await db_session.commit()

    user = await _register(client, db_session, 810071, bot_token)
    headers = telegram_headers(810071, bot_token)

    tasks = (await client.get("/api/v1/tasks", headers=headers)).json()
    premium_task = tasks["premium"][0]

    first = await client.post(f"/api/v1/tasks/{premium_task['user_task_id']}/claim", headers=headers)
    assert first.status_code == 200
    await db_session.refresh(user)
    assert user.balance == 577

    # Simulate the bot sweep clawing it back after the player unsubscribed, then resetting it.
    user_task = await db_session.get(UserTask, premium_task["user_task_id"])
    user.balance -= 77
    db_session.add(user)
    user_task.reward_claimed = False
    user_task.reward_coins_granted = None
    user_task.coins_withdrawn = False
    db_session.add(user_task)
    await db_session.commit()

    tasks_after_reset = (await client.get("/api/v1/tasks", headers=headers)).json()
    reset_task = next(t for t in tasks_after_reset["premium"] if t["code"] == "premium_reclaim_test")
    assert reset_task["is_completed"] is True
    assert reset_task["is_claimed"] is False

    second = await client.post(f"/api/v1/tasks/{reset_task['user_task_id']}/claim", headers=headers)
    assert second.status_code == 200
    assert second.json()["reward_coins"] == 77

    await db_session.refresh(user)
    assert user.balance == 577


async def test_premium_task_exposes_invite_link_and_checks_via_username(client, db_session, bot_token, monkeypatch):
    seen_usernames = []

    async def fake_check(telegram_user_id, channel_username):
        seen_usernames.append(channel_username)
        return True

    monkeypatch.setattr("app.services.task_service.check_channel_membership", fake_check)

    db_session.add(
        TaskDefinition(
            code="premium_invite_link", name="Premium invite link", description="test",
            category=TaskCategory.premium, condition_type=TaskConditionType.metric_counter,
            target_value=0, reward_coins=5,
            channel_username="@real_channel_username", invite_link="https://t.me/+BgFhDFVxaF1jOTJi",
        )
    )
    await db_session.commit()

    await _register(client, db_session, 810008, bot_token)
    headers = telegram_headers(810008, bot_token)

    tasks = (await client.get("/api/v1/tasks", headers=headers)).json()
    premium_task = tasks["premium"][0]
    # Users are shown the invite link (works for private channels), while
    # the subscription check always uses the real @username under the hood.
    assert premium_task["invite_link"] == "https://t.me/+BgFhDFVxaF1jOTJi"

    resp = await client.post(f"/api/v1/tasks/{premium_task['user_task_id']}/claim", headers=headers)
    assert resp.status_code == 200
    assert seen_usernames == ["@real_channel_username"]


async def test_premium_task_without_username_checks_via_chat_id(client, db_session, bot_token, monkeypatch):
    seen_chat_ids = []

    async def fake_check(telegram_user_id, chat_id):
        seen_chat_ids.append(chat_id)
        return True

    monkeypatch.setattr("app.services.task_service.check_channel_membership", fake_check)

    db_session.add(
        TaskDefinition(
            code="premium_private_channel", name="Premium private", description="test",
            category=TaskCategory.premium, condition_type=TaskConditionType.metric_counter,
            target_value=0, reward_coins=5,
            channel_username=None, channel_chat_id=-1001669902011,
            invite_link="https://t.me/+BgFhDFVxaF1jOTJi",
        )
    )
    await db_session.commit()

    await _register(client, db_session, 810009, bot_token)
    headers = telegram_headers(810009, bot_token)

    tasks = (await client.get("/api/v1/tasks", headers=headers)).json()
    premium_task = tasks["premium"][0]
    assert premium_task["channel_username"] is None
    assert premium_task["invite_link"] == "https://t.me/+BgFhDFVxaF1jOTJi"

    resp = await client.post(f"/api/v1/tasks/{premium_task['user_task_id']}/claim", headers=headers)
    assert resp.status_code == 200
    # No @username to check against, so the numeric chat id must be used.
    assert seen_chat_ids == [-1001669902011]


async def test_creating_premium_task_does_not_auto_notify(client, db_session, bot_token):
    """Creating a premium task must NOT spam every user — the admin sends a
    single broadcast afterwards via POST /admin/tasks/broadcast-premium
    instead (see test_premium_task_broadcast_* below)."""
    from sqlalchemy import select

    from app.models.enums import NotificationType
    from app.models.notification import Notification

    await _register(client, db_session, 810010, bot_token)

    admin_headers = telegram_headers(999000001, bot_token)
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    admin_token = session_resp.json()["admin_token"]

    resp = await client.post(
        "/api/v1/admin/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "code": "premium_broadcast_test", "name": "Premium Broadcast", "description": "test",
            "category": "premium", "condition_type": "metric_counter", "target_value": 0,
            "reward_coins": 0, "channel_username": "@test",
        },
    )
    assert resp.status_code == 200
    task_id = resp.json()["id"]

    notifications = (
        await db_session.execute(
            select(Notification).where(
                Notification.type == NotificationType.premium_task_available,
                Notification.related_object_id == task_id,
            )
        )
    ).scalars().all()
    assert notifications == []


async def test_premium_task_broadcast_notifies_all_users_with_pluralized_text(client, db_session, bot_token):
    from sqlalchemy import select

    from app.models.enums import NotificationType
    from app.models.notification import Notification

    await _register(client, db_session, 810011, bot_token)
    await _register(client, db_session, 810012, bot_token)

    admin_headers = telegram_headers(999000001, bot_token)
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    admin_token = session_resp.json()["admin_token"]

    resp = await client.post(
        "/api/v1/admin/tasks/broadcast-premium",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"task_count": 3, "message": "Успей до конца недели!"},
    )
    assert resp.status_code == 200
    assert resp.json()["recipients"] >= 2

    notifications = (
        await db_session.execute(
            select(Notification).where(Notification.type == NotificationType.premium_task_available)
        )
    ).scalars().all()
    assert len(notifications) >= 2
    assert all("Появилось 3 новых премиум задания! Успей получить награду" in n.body for n in notifications)
    assert all("Успей до конца недели!" in n.body for n in notifications)


async def test_premium_task_broadcast_rejects_zero_count(client, db_session, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    admin_token = session_resp.json()["admin_token"]

    resp = await client.post(
        "/api/v1/admin/tasks/broadcast-premium",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"task_count": 0},
    )
    assert resp.status_code == 422


async def test_disabling_premium_task_hides_it_from_players(client, db_session, bot_token):
    task = TaskDefinition(
        code="premium_disable_test", name="Premium Disable", description="test",
        category=TaskCategory.premium, condition_type=TaskConditionType.metric_counter,
        target_value=0, reward_coins=0,
    )
    db_session.add(task)
    await db_session.commit()

    await _register(client, db_session, 810014, bot_token)
    headers = telegram_headers(810014, bot_token)

    tasks = (await client.get("/api/v1/tasks", headers=headers)).json()
    assert any(t["code"] == "premium_disable_test" for t in tasks["premium"])

    admin_headers = telegram_headers(999000001, bot_token)
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    admin_token = session_resp.json()["admin_token"]
    toggle_resp = await client.post(
        f"/api/v1/admin/tasks/{task.id}/toggle-active",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["is_active"] is False

    tasks_after = (await client.get("/api/v1/tasks", headers=headers)).json()
    assert not any(t["code"] == "premium_disable_test" for t in tasks_after["premium"])


async def test_admin_task_list_reports_completed_and_claimed_counts(client, db_session, bot_token):
    task = TaskDefinition(
        code="premium_stats_test", name="Premium Stats", description="test",
        category=TaskCategory.premium, condition_type=TaskConditionType.metric_counter,
        target_value=0, reward_coins=5,
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    # Two users get the task auto-completed on assignment (target_value=0);
    # only one of them claims the reward.
    headers_a = telegram_headers(810020, bot_token)
    await client.post("/api/v1/auth/session", headers=headers_a)
    tasks_a = (await client.get("/api/v1/tasks", headers=headers_a)).json()
    premium_a = next(t for t in tasks_a["premium"] if t["code"] == "premium_stats_test")
    resp = await client.post(f"/api/v1/tasks/{premium_a['user_task_id']}/claim", headers=headers_a)
    assert resp.status_code == 200

    headers_b = telegram_headers(810021, bot_token)
    await client.post("/api/v1/auth/session", headers=headers_b)
    await client.get("/api/v1/tasks", headers=headers_b)

    admin_headers = telegram_headers(999000001, bot_token)
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    admin_token = session_resp.json()["admin_token"]

    resp = await client.get("/api/v1/admin/tasks", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    stats = next(t for t in resp.json() if t["id"] == task.id)
    assert stats["completed_count"] == 2
    assert stats["claimed_count"] == 1


async def test_referral_completion_progresses_referral_task(client, db_session, bot_token):
    db_session.add(
        TaskDefinition(
            code="invite_test", name="Invite test", description="test", category=TaskCategory.regular,
            condition_type=TaskConditionType.metric_counter, metric="referrals_count", target_value=1,
            reward_coins=50,
        )
    )
    await db_session.commit()

    referrer_headers = telegram_headers(810011, bot_token)
    await client.post("/api/v1/auth/session", headers=referrer_headers)
    referrer = await get_user_by_telegram_id(db_session, 810011)

    tasks = (await client.get("/api/v1/tasks", headers=referrer_headers)).json()["regular"]
    invite_task = next((t for t in tasks if t["code"] == "invite_test"), None)
    assert invite_task is not None
    assert invite_task["is_completed"] is False

    new_user_headers = telegram_headers(810012, bot_token)
    new_user_headers["X-Referral-Code"] = str(referrer.telegram_id)
    await client.post("/api/v1/auth/session", headers=new_user_headers)

    # Referral progress is only credited once the friend has really played
    # (referral_service.check_friend), not on bare registration.
    from datetime import timedelta

    from app.core.timeutil import local_today
    from app.models.user_activity import UserDailyActivity
    from app.services import referral_service

    friend = await get_user_by_telegram_id(db_session, 810012)
    for n in (1, 2):
        db_session.add(UserDailyActivity(user_id=friend.id, day=local_today() - timedelta(days=n)))
    await db_session.commit()
    await referral_service.check_friend(db_session, friend)

    tasks_after = (await client.get("/api/v1/tasks", headers=referrer_headers)).json()["regular"]
    invite_task_after = next(t for t in tasks_after if t["code"] == "invite_test")
    assert invite_task_after["is_completed"] is True
    assert invite_task_after["progress"] == 1


async def test_claim_stores_reward_coins_granted_snapshot(client, db_session, bot_token):
    """The premium-subscription clawback sweep (bot/services/
    premium_subscription_check.py) debits/credits whatever THIS claim
    actually granted, not the task definition's current reward_coins (an
    admin can edit that later) — so every claim must snapshot the amount."""
    await _create_regular_tasks(db_session, 6)
    user = await _register(client, db_session, 810101, bot_token)
    headers = telegram_headers(810101, bot_token)

    tasks_before = (await client.get("/api/v1/tasks", headers=headers)).json()["regular"]
    target = tasks_before[0]
    task_def = (
        await db_session.execute(select(TaskDefinition).where(TaskDefinition.code == target["code"]))
    ).scalar_one()

    user_task = await db_session.get(UserTask, target["user_task_id"])
    user_task.progress = task_def.target_value
    user_task.completed_at = datetime.now(timezone.utc)
    db_session.add(user_task)
    await db_session.commit()

    resp = await client.post(f"/api/v1/tasks/{target['user_task_id']}/claim", headers=headers)
    assert resp.status_code == 200

    await db_session.refresh(user_task)
    assert user_task.reward_coins_granted == task_def.reward_coins


async def test_claim_blocked_user_stores_zero_reward_coins_granted(client, db_session, bot_token):
    await _create_regular_tasks(db_session, 6)
    user = await _register(client, db_session, 810102, bot_token)
    headers = telegram_headers(810102, bot_token)
    user.game_rewards_blocked = True
    db_session.add(user)
    await db_session.commit()

    tasks_before = (await client.get("/api/v1/tasks", headers=headers)).json()["regular"]
    target = tasks_before[0]
    user_task = await db_session.get(UserTask, target["user_task_id"])
    user_task.progress = 999
    user_task.completed_at = datetime.now(timezone.utc)
    db_session.add(user_task)
    await db_session.commit()

    resp = await client.post(f"/api/v1/tasks/{target['user_task_id']}/claim", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["reward_coins"] == 0

    await db_session.refresh(user_task)
    assert user_task.reward_coins_granted == 0


async def test_admin_backfill_premium_coins_sets_reward_and_credits_claimed_users(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)

    definition = TaskDefinition(
        code="premium_legacy", name="Premium legacy", description="test", category=TaskCategory.premium,
        condition_type=TaskConditionType.metric_counter, target_value=0, reward_coins=0,
        channel_username="@legacy_channel",
    )
    db_session.add(definition)
    await db_session.commit()
    await db_session.refresh(definition)

    user = await _register(client, db_session, 810103, bot_token)
    # Simulate a claim made before this feature existed: reward_claimed is
    # True but reward_coins_granted was never snapshotted (NULL).
    db_session.add(
        UserTask(
            user_id=user.id, task_definition_id=definition.id, slot_index=None,
            completed_at=datetime.now(timezone.utc), reward_claimed=True,
        )
    )
    await db_session.commit()

    resp = await client.post("/api/v1/admin/tasks/backfill-premium-coins", headers=auth)
    assert resp.status_code == 200
    body = resp.json()
    assert body["definitions_updated"] == 1
    assert body["users_credited"] == 1

    await db_session.refresh(definition)
    assert definition.reward_coins == 1000

    await db_session.refresh(user)
    assert user.balance == 1500  # 500 starting balance + 1000 backfilled

    user_task = (
        await db_session.execute(select(UserTask).where(UserTask.task_definition_id == definition.id))
    ).scalar_one()
    assert user_task.reward_coins_granted == 1000


async def test_admin_backfill_premium_coins_is_idempotent(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)

    definition = TaskDefinition(
        code="premium_legacy2", name="Premium legacy 2", description="test", category=TaskCategory.premium,
        condition_type=TaskConditionType.metric_counter, target_value=0, reward_coins=0,
        channel_username="@legacy_channel2",
    )
    db_session.add(definition)
    await db_session.commit()
    await db_session.refresh(definition)

    user = await _register(client, db_session, 810104, bot_token)
    db_session.add(
        UserTask(
            user_id=user.id, task_definition_id=definition.id, slot_index=None,
            completed_at=datetime.now(timezone.utc), reward_claimed=True,
        )
    )
    await db_session.commit()

    first = await client.post("/api/v1/admin/tasks/backfill-premium-coins", headers=auth)
    assert first.json() == {"definitions_updated": 1, "users_credited": 1}

    second = await client.post("/api/v1/admin/tasks/backfill-premium-coins", headers=auth)
    assert second.json() == {"definitions_updated": 0, "users_credited": 0}

    await db_session.refresh(user)
    assert user.balance == 1500  # only credited once


async def test_admin_backfill_premium_coins_skips_definitions_with_existing_reward(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)

    definition = TaskDefinition(
        code="premium_configured", name="Premium configured", description="test", category=TaskCategory.premium,
        condition_type=TaskConditionType.metric_counter, target_value=0, reward_coins=250,
        channel_username="@configured_channel",
    )
    db_session.add(definition)
    await db_session.commit()
    await db_session.refresh(definition)

    resp = await client.post("/api/v1/admin/tasks/backfill-premium-coins", headers=auth)
    assert resp.json() == {"definitions_updated": 0, "users_credited": 0}

    await db_session.refresh(definition)
    assert definition.reward_coins == 250


async def test_required_premium_tasks_come_first(client, db_session, bot_token):
    db_session.add_all([
        TaskDefinition(code="prem_other", name="Other", description="", category=TaskCategory.premium,
                       condition_type=TaskConditionType.metric_counter, target_value=0, reward_coins=3000,
                       channel_username="@other", sort_order=0),
        TaskDefinition(code="prem_game_chat", name="Chat", description="", category=TaskCategory.premium,
                       condition_type=TaskConditionType.metric_counter, target_value=0, reward_coins=3000,
                       channel_username="@game_chat", sort_order=5, is_required=True),
    ])
    await db_session.commit()
    await _register(client, db_session, 810025, bot_token)

    premium = (await client.get("/api/v1/tasks", headers=telegram_headers(810025, bot_token))).json()["premium"]
    assert [t["code"] for t in premium] == ["prem_game_chat", "prem_other"]
    assert premium[0]["is_required"] is True and premium[1]["is_required"] is False
    assert premium[0]["route"] is None


async def test_badge_comes_with_the_last_required_subscription(client, db_session, bot_token, monkeypatch):
    from app.models.badge import Badge, UserBadge
    from app.services.game_config_service import get_config

    async def fake_subscribed(_telegram_id, _chat):
        return True

    monkeypatch.setattr("app.services.task_service.check_channel_membership", fake_subscribed)
    badge = Badge(name="Свой в клубе", icon="🤝")
    db_session.add(badge)
    db_session.add_all([
        TaskDefinition(code="req_channel", name="Канал", description="", category=TaskCategory.premium,
                       condition_type=TaskConditionType.metric_counter, target_value=0, reward_coins=3000,
                       channel_username="@game", is_required=True),
        TaskDefinition(code="req_chat", name="Чат", description="", category=TaskCategory.premium,
                       condition_type=TaskConditionType.metric_counter, target_value=0, reward_coins=3000,
                       channel_username="@game_chat", is_required=True),
    ])
    await db_session.commit()
    config = await get_config(db_session)
    config.task_required_badge_id = badge.id
    await db_session.commit()

    user = await _register(client, db_session, 810026, bot_token)
    headers = telegram_headers(810026, bot_token)
    body = (await client.get("/api/v1/tasks", headers=headers)).json()
    assert body["required_badge"]["name"] == "Свой в клубе"
    first, second = body["premium"]

    one = (await client.post(f"/api/v1/tasks/{first['user_task_id']}/claim", headers=headers)).json()
    assert one["granted_badge"] is None
    two = (await client.post(f"/api/v1/tasks/{second['user_task_id']}/claim", headers=headers)).json()
    assert two["granted_badge"]["name"] == "Свой в клубе"

    owned = (await db_session.execute(select(UserBadge).where(UserBadge.user_id == user.id))).scalars().all()
    assert [b.badge_id for b in owned] == [badge.id]
    await db_session.refresh(user)
    assert user.active_badge_id == badge.id
