import asyncio

import pytest

from services import premium_subscription_check as sweep


class _Stop(Exception):
    pass


def _run_once(monkeypatch, rows, members):
    calls = {"debits": [], "resets": [], "revoked": [], "notes": []}

    async def fetch():
        return rows

    async def is_member(_bot, chat_id, telegram_id):
        return members[telegram_id]

    async def adjust(user_id, delta, _reason):
        calls["debits"].append((user_id, delta))

    async def reset(user_task_id):
        calls["resets"].append(user_task_id)

    async def revoke(user_id):
        calls["revoked"].append(user_id)
        return True

    async def notify(user_id, _type, _title, body):
        calls["notes"].append((user_id, body))

    async def sleep(seconds):
        if seconds == sweep.CHECK_INTERVAL_SECONDS:
            raise _Stop

    monkeypatch.setattr(sweep.db, "fetch_claimed_premium_channel_tasks", fetch)
    monkeypatch.setattr(sweep.db, "adjust_coins_allow_negative", adjust)
    monkeypatch.setattr(sweep.db, "reset_task_for_reclaim", reset)
    monkeypatch.setattr(sweep.db, "revoke_task_required_badge", revoke, raising=False)
    monkeypatch.setattr(sweep.db, "create_notification", notify)
    monkeypatch.setattr(sweep, "_is_member", is_member)
    monkeypatch.setattr(sweep.asyncio, "sleep", sleep)
    with pytest.raises(_Stop):
        asyncio.run(sweep.run_premium_subscription_check(bot=None))
    return calls


def _row(user_task_id, user_id, telegram_id, required):
    return {"user_task_id": user_task_id, "user_id": user_id, "telegram_id": telegram_id, "reward_coins_granted": 3000,
            "channel_chat_id": None, "channel_username": "@game", "is_required": required}


def test_leaving_a_required_subscription_takes_coins_and_the_badge(monkeypatch):
    calls = _run_once(monkeypatch, [_row(1, 10, 100, True)], {100: False})
    assert calls["debits"] == [(10, -3000)] and calls["resets"] == [1] and calls["revoked"] == [10]
    assert "«Свой в клубе»" in calls["notes"][0][1]


def test_an_ordinary_subscription_keeps_the_badge_and_members_keep_everything(monkeypatch):
    calls = _run_once(monkeypatch, [_row(1, 10, 100, False), _row(2, 11, 101, True)], {100: False, 101: True})
    assert calls["debits"] == [(10, -3000)] and calls["revoked"] == []
    assert "«Свой в клубе»" not in calls["notes"][0][1]
