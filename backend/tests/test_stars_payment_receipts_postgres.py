"""Stars payment receipts on real Postgres (row locks, the receipt insert
race). SQLite ignores SELECT ... FOR UPDATE, so these use the `real_pg`
fixture (tests/conftest.py): a dedicated `*_test` database, migrated to
head on first use; every row a test creates is deleted on teardown."""
import asyncio
import secrets
import uuid

import pytest
from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.models.pack import StarsInvoice
from app.models.stars_payment_receipt import StarsPaymentReceipt
from app.models.transaction import CoinTransaction
from app.models.user import User
from app.schemas.stars import StarsPaymentDeliverIn
from app.services import stars_receipt_service


@pytest.fixture(autouse=True)
def _fresh_schema():
    # The PG database is migrated by alembic and must not be dropped.
    yield


async def _coin_order(pg, coins=300, stars=7):
    async with pg() as s:
        user = User(telegram_id=int(uuid.uuid4().int % 10**12), first_name="Pay", balance=0)
        s.add(user)
        await s.flush()
        token = secrets.token_urlsafe(16)
        s.add(StarsInvoice(user_id=user.id, coins_amount=coins, payload_token=token, stars_amount=stars))
        await s.commit()
        return user.id, StarsPaymentDeliverIn(
            payload_token=token, telegram_user_id=user.telegram_id,
            telegram_payment_charge_id=f"pg-{uuid.uuid4().hex}", total_amount=stars,
        )


async def _deliver(pg, payload):
    async with pg() as s:
        try:
            return await stars_receipt_service.deliver_with_receipt(s, payload)
        except AppError as exc:
            return exc


async def test_concurrent_deliveries_credit_once(real_pg):
    user_id, payload = await _coin_order(real_pg)

    results = await asyncio.gather(*(_deliver(real_pg, payload) for _ in range(4)))
    assert all(not isinstance(r, Exception) and r.status == "completed" for r in results)

    async with real_pg() as s:
        assert (await s.get(User, user_id)).balance == 300
        credits = (
            await s.execute(select(func.count(CoinTransaction.id)).where(CoinTransaction.user_id == user_id))
        ).scalar_one()
        assert credits == 1
        receipts = (
            await s.execute(
                select(StarsPaymentReceipt).where(
                    StarsPaymentReceipt.telegram_payment_charge_id == payload.telegram_payment_charge_id
                )
            )
        ).scalars().all()
        assert len(receipts) == 1 and receipts[0].status == "delivered"


async def test_failure_is_committed_and_refund_wins_over_later_delivery(real_pg, monkeypatch):
    user_id, payload = await _coin_order(real_pg)

    failed = await _deliver(real_pg, payload.model_copy(update={"total_amount": 1}))
    assert isinstance(failed, AppError)
    async with real_pg() as s:
        receipt = (
            await s.execute(
                select(StarsPaymentReceipt).where(
                    StarsPaymentReceipt.telegram_payment_charge_id == payload.telegram_payment_charge_id
                )
            )
        ).scalar_one()
        assert receipt.status == "failed" and receipt.attempts == 1 and receipt.next_attempt_at is not None
        receipt_id = receipt.id

    async def _fake_refund(*args):
        return None

    monkeypatch.setattr(stars_receipt_service, "_request_telegram_refund", _fake_refund)
    async with real_pg() as s:
        out = await stars_receipt_service.admin_refund(s, receipt_id)
        assert out.status == "refunded"

    late = await _deliver(real_pg, payload)
    assert isinstance(late, AppError) and late.status_code == 409
    async with real_pg() as s:
        assert (await s.get(User, user_id)).balance == 0
