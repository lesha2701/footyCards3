"""«Антифрод»: finds coin hubs and the accounts that fed them; bans in bulk."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.enums import TradeStatus
from app.models.pack import StarsInvoice
from app.models.trade import TradeOffer
from app.models.user import User
from tests.utils import telegram_headers

ADMIN_TELEGRAM_ID = 999000001  # in ADMIN_TELEGRAM_IDS (conftest)
API = "/api/v1/admin/antifraud"


async def _admin(client, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(ADMIN_TELEGRAM_ID, bot_token))
    return {"Authorization": f"Bearer {resp.json()['admin_token']}"}, resp.json()["user"]["id"]


async def _user(db_session, telegram_id, **fields) -> int:
    user = User(telegram_id=telegram_id, username=f"u{telegram_id}", first_name="F", balance=fields.pop("balance", 0), **fields)
    db_session.add(user)
    await db_session.commit()
    return user.id


async def _give(db_session, sender_id, receiver_id, coins, status=TradeStatus.accepted):
    db_session.add(TradeOffer(
        sender_id=sender_id, receiver_id=receiver_id, status=status, sender_coins=coins,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    ))
    await db_session.commit()


async def _network(db_session):
    hub = await _user(db_session, 880100, balance=500_000)
    farms = [await _user(db_session, 880101 + i) for i in range(3)]
    for f in farms:
        await _give(db_session, f, hub, 2_000)
    # A payer who also sent coins: listed, but flagged as paying.
    payer = await _user(db_session, 880110)
    await _give(db_session, payer, hub, 100)
    db_session.add(StarsInvoice(user_id=payer, coins_amount=10, payload_token="t-payer", stars_amount=50,
                                completed_at=datetime.now(timezone.utc)))
    # Noise: a rejected trade and a small private trade never count.
    other = await _user(db_session, 880120)
    await _give(db_session, other, hub, 9_999, status=TradeStatus.rejected)
    friend = await _user(db_session, 880121)
    await _give(db_session, other, friend, 50)
    await db_session.commit()
    return hub, farms, payer, other, friend


async def test_scan_finds_the_hub_and_its_farm(client, db_session, bot_token):
    auth, _admin_id = await _admin(client, bot_token)
    hub, farms, payer, other, friend = await _network(db_session)

    body = (await client.get(f"{API}/scan", headers=auth, params={"min_senders": 3, "burst_min": 5})).json()
    assert [h["id"] for h in body["hubs"]] == [hub]
    assert body["hubs"][0]["senders"] == 4 and body["hubs"][0]["coins_in"] == 6_100
    farm_ids = {f["id"] for f in body["farms"]}
    assert farm_ids == {*farms, payer}
    assert other not in farm_ids and friend not in farm_ids
    by_id = {f["id"]: f for f in body["farms"]}
    assert by_id[payer]["stars_paid"] == 50
    assert body["farms_summary"] == {"total": 4, "not_banned": 4, "not_banned_unpaid": 3, "coins": 6_100}
    # Every account above registered in the same hour → one burst.
    assert body["bursts"] and body["bursts"][0]["farm_accounts"] == 4


async def test_ban_skips_admins_and_already_banned(client, db_session, bot_token):
    auth, admin_id = await _admin(client, bot_token)
    hub, farms, *_ = await _network(db_session)
    already = await _user(db_session, 880130, is_banned=True)

    resp = await client.post(f"{API}/ban", headers=auth, json={"user_ids": [hub, *farms, admin_id, already]})
    assert resp.status_code == 200
    assert resp.json()["banned"] == 4 and set(resp.json()["user_ids"]) == {hub, *farms}

    db_session.expire_all()
    rows = (await db_session.execute(select(User).where(User.id.in_([hub, *farms, admin_id])))).scalars().all()
    by_id = {u.id: u for u in rows}
    assert all(by_id[i].is_banned and by_id[i].is_trade_banned for i in [hub, *farms])
    assert by_id[admin_id].is_banned is False


async def test_antifraud_requires_admin(client, db_session, bot_token):
    await client.post("/api/v1/auth/session", headers=telegram_headers(880140, bot_token))
    resp = await client.get(f"{API}/scan", headers=telegram_headers(880140, bot_token))
    assert resp.status_code == 401
