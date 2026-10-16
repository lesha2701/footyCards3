"""Stars payment delivery in the bot: the receipt is recorded before
delivery, failures are retried by the loop, and nobody is left without a
message. The DB and the backend call are faked; tests are plain sync
functions running their coroutine with asyncio.run (no pytest plugin)."""
import asyncio
from datetime import datetime
from types import SimpleNamespace

import db
from handlers import payments, support
from services import stars_delivery


class FakeBot:
    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))


def _receipt(**over):
    row = {
        "id": 1, "payload_token": "tok", "telegram_user_id": 555, "telegram_payment_charge_id": "ch-1",
        "total_amount": 10, "attempts": 0, "status": "failed",
    }
    row.update(over)
    return row


def _patch_admins(monkeypatch, ids):
    monkeypatch.setattr(stars_delivery.settings.__class__, "admin_ids", property(lambda self: ids))


def test_success_text_matches_what_was_bought():
    assert "Подарок" in stars_delivery.success_text({"gift_result": {"id": 1}})
    assert "Монеты" in stars_delivery.success_text({"coin_result": {"coins_credited": 5}})
    assert "Колесо" in stars_delivery.success_text({"wheel_result": {}})
    assert "Пак" in stars_delivery.success_text({"result": {}})


def test_retry_loop_delivers_and_tells_the_player(monkeypatch):
    bot = FakeBot()

    async def fetch_due(max_attempts, limit=20):
        assert max_attempts == stars_delivery.MAX_AUTO_ATTEMPTS
        return [_receipt()]

    async def deliver(*args):
        return stars_delivery.DeliveryOutcome(ok=True, body={"coin_result": {"coins_credited": 100}}, status=200)

    monkeypatch.setattr(db, "fetch_due_stars_receipts", fetch_due)
    monkeypatch.setattr(stars_delivery, "deliver", deliver)

    assert asyncio.run(stars_delivery.retry_due_receipts(bot)) == 1
    assert bot.sent[0][0] == 555 and "Покупка начислена" in bot.sent[0][1]


def test_retry_loop_postpones_when_backend_is_unreachable(monkeypatch):
    bot = FakeBot()
    postponed = []

    async def fetch_due(max_attempts, limit=20):
        return [_receipt(id=7)]

    async def deliver(*args):
        return stars_delivery.DeliveryOutcome(ok=False, status=None, error="ClientConnectorError")

    async def postpone(receipt_id, seconds):
        postponed.append((receipt_id, seconds))

    monkeypatch.setattr(db, "fetch_due_stars_receipts", fetch_due)
    monkeypatch.setattr(db, "postpone_stars_receipt", postpone)
    monkeypatch.setattr(stars_delivery, "deliver", deliver)

    assert asyncio.run(stars_delivery.retry_due_receipts(bot)) == 0
    assert postponed == [(7, stars_delivery.UNREACHABLE_RETRY_SECONDS)]
    assert bot.sent == []


def test_retry_loop_hands_over_to_admins_after_last_attempt(monkeypatch):
    bot = FakeBot()
    _patch_admins(monkeypatch, [42])

    async def fetch_due(max_attempts, limit=20):
        return [_receipt(attempts=stars_delivery.MAX_AUTO_ATTEMPTS - 1)]

    async def deliver(*args):
        return stars_delivery.DeliveryOutcome(ok=False, status=409, error="Gift set not found")

    monkeypatch.setattr(db, "fetch_due_stars_receipts", fetch_due)
    monkeypatch.setattr(stars_delivery, "deliver", deliver)

    asyncio.run(stars_delivery.retry_due_receipts(bot))
    to_player = [t for chat, t in bot.sent if chat == 555]
    to_admin = [t for chat, t in bot.sent if chat == 42]
    assert to_player and "/paysupport" in to_player[0]
    assert to_admin and "Автоповторы закончились" in to_admin[0]


def test_retry_loop_stays_quiet_on_an_intermediate_failure(monkeypatch):
    bot = FakeBot()
    _patch_admins(monkeypatch, [42])

    async def fetch_due(max_attempts, limit=20):
        return [_receipt(attempts=2)]

    async def deliver(*args):
        return stars_delivery.DeliveryOutcome(ok=False, status=500, error="boom")

    monkeypatch.setattr(db, "fetch_due_stars_receipts", fetch_due)
    monkeypatch.setattr(stars_delivery, "deliver", deliver)

    asyncio.run(stars_delivery.retry_due_receipts(bot))
    assert bot.sent == []


class FakeMessage:
    def __init__(self, bot):
        self.bot = bot
        self.answers: list[str] = []
        self.from_user = SimpleNamespace(id=555)
        self.successful_payment = SimpleNamespace(
            invoice_payload="tok", telegram_payment_charge_id="ch-1", total_amount=10,
        )

    async def answer(self, text, **kwargs):
        self.answers.append(text)


def test_payment_is_recorded_before_delivery_and_failure_is_announced(monkeypatch):
    bot = FakeBot()
    _patch_admins(monkeypatch, [42])
    calls = []

    async def record(charge_id, payload, telegram_user_id, amount, first_retry):
        calls.append(("record", charge_id, first_retry))

    async def deliver(*args):
        calls.append(("deliver",))
        return stars_delivery.DeliveryOutcome(ok=False, status=500, error="boom")

    monkeypatch.setattr(db, "record_stars_payment", record)
    monkeypatch.setattr(stars_delivery, "deliver", deliver)
    message = FakeMessage(bot)

    asyncio.run(payments.handle_successful_payment(message))
    assert calls == [("record", "ch-1", stars_delivery.FIRST_RETRY_DELAY_SECONDS), ("deliver",)]
    assert message.answers == [stars_delivery.DELAYED_TEXT]
    assert bot.sent and bot.sent[0][0] == 42 and "Не удалось начислить" in bot.sent[0][1]


def test_payment_is_delivered_even_if_recording_fails(monkeypatch):
    bot = FakeBot()

    async def record(*args):
        raise RuntimeError("db down")

    async def deliver(*args):
        return stars_delivery.DeliveryOutcome(ok=True, body={"coin_result": {}}, status=200)

    monkeypatch.setattr(db, "record_stars_payment", record)
    monkeypatch.setattr(stars_delivery, "deliver", deliver)
    message = FakeMessage(bot)

    asyncio.run(payments.handle_successful_payment(message))
    assert message.answers and "Монеты зачислены" in message.answers[0]


def test_paysupport_summary_lists_statuses():
    rows = [
        {"created_at": datetime(2026, 10, 16, 12, 30), "total_amount": 50, "status": "delivered"},
        {"created_at": datetime(2026, 10, 16, 13, 0), "total_amount": 10, "status": "refunded"},
    ]
    text = support.receipts_summary(rows)
    assert "16.10 12:30 — 50 ⭐ — ✅ начислено" in text
    assert "звёзды возвращены" in text
    assert "нет оплат" in support.receipts_summary([])


def test_terms_links_every_document():
    for url in (support.USER_AGREEMENT_URL, support.PACK_PURCHASE_TERMS_URL, support.PRIVACY_POLICY_URL):
        assert url in support.TERMS_TEXT
