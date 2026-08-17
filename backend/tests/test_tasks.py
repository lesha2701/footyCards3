from datetime import datetime, timezone

from app.models.enums import TaskCategory, TaskConditionType
from app.models.task import TaskDefinition, UserTask
from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


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


async def test_claim_regular_task_credits_coins_and_refills_slot(client, db_session, bot_token):
    await _create_regular_tasks(db_session, 6)
    user = await _register(client, db_session, 810003, bot_token)
    headers = telegram_headers(810003, bot_token)

    tasks_before = (await client.get("/api/v1/tasks", headers=headers)).json()["regular"]
    target = tasks_before[0]
    codes_before = {t["code"] for t in tasks_before}

    # Simulate the task's condition being met.
    user_task = await db_session.get(UserTask, target["user_task_id"])
    user_task.progress = 1
    user_task.completed_at = datetime.now(timezone.utc)
    db_session.add(user_task)
    await db_session.commit()

    claim_resp = await client.post(f"/api/v1/tasks/{target['user_task_id']}/claim", headers=headers)
    assert claim_resp.status_code == 200
    body = claim_resp.json()
    assert body["reward_coins"] == target["reward_coins"]
    assert body["refilled_task"] is not None
    assert body["refilled_task"]["code"] not in codes_before

    await db_session.refresh(user)
    assert user.balance == 500 + target["reward_coins"]

    tasks_after = (await client.get("/api/v1/tasks", headers=headers)).json()["regular"]
    assert len(tasks_after) == 5
    assert target["code"] not in {t["code"] for t in tasks_after}


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

    # Referral progress is only credited once the referred user completes a
    # real paid purchase (not on bare registration) — see pack_service.open_pack.
    from app.models.enums import Rarity
    from tests.factories import create_pack, create_player

    await create_player(db_session, rarity=Rarity.common)
    pack = await create_pack(db_session, "basic", price=100, card_count=1, probabilities={Rarity.common: 1.0})
    resp = await client.post(f"/api/v1/packs/{pack.id}/open", headers=new_user_headers, json={})
    assert resp.status_code == 200

    tasks_after = (await client.get("/api/v1/tasks", headers=referrer_headers)).json()["regular"]
    invite_task_after = next(t for t in tasks_after if t["code"] == "invite_test")
    assert invite_task_after["is_completed"] is True
    assert invite_task_after["progress"] == 1
