"""«Антифрод» in the admin panel: finds coin-farming networks built from
multi-accounts and bans them in bulk.

The pattern it looks for (seen in production): hundreds of accounts
registered in bursts farm coins in the games, then hand them over in
accepted trades to «hubs» — accounts that take coins from many distinct
senders — which pass them on or sell them.

* hubs: receivers of coins (accepted trades) from >= min_senders distinct
  senders;
* farm accounts: everyone who gave coins to a hub (a hub can be one of them
  too — farms are layered);
* bursts: hours with an unusual number of registrations, with how many of
  those accounts are farm accounts.

Accounts that paid Telegram Stars are flagged, never pre-selected: a payer
is far more likely to be a real player. Admins are never listed or banned.
Read-only except ban_users."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models.enums import TradeStatus
from app.models.pack import StarsInvoice
from app.models.trade import TradeOffer
from app.models.user import User

MAX_LIST = 2000
MAX_BAN_BATCH = 5000


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


async def _stars_paid(db: AsyncSession, user_ids: list[int]) -> dict[int, int]:
    if not user_ids:
        return {}
    rows = await db.execute(
        select(StarsInvoice.user_id, func.sum(StarsInvoice.stars_amount))
        .where(StarsInvoice.user_id.in_(user_ids), StarsInvoice.completed_at.is_not(None))
        .group_by(StarsInvoice.user_id)
    )
    return {uid: int(total or 0) for uid, total in rows.all()}


async def scan(db: AsyncSession, min_senders: int = 20, days: int = 120, burst_min: int = 30) -> dict:
    since = _since(days)
    coin_trade = and_(
        TradeOffer.status == TradeStatus.accepted, TradeOffer.sender_coins > 0, TradeOffer.created_at >= since,
    )

    hub_rows = (
        await db.execute(
            select(
                TradeOffer.receiver_id,
                func.count(func.distinct(TradeOffer.sender_id)).label("senders"),
                func.sum(TradeOffer.sender_coins).label("coins_in"),
            )
            .where(coin_trade)
            .group_by(TradeOffer.receiver_id)
            .having(func.count(func.distinct(TradeOffer.sender_id)) >= min_senders)
            .order_by(func.sum(TradeOffer.sender_coins).desc())
        )
    ).all()
    hub_ids = [r.receiver_id for r in hub_rows]

    coins_out: dict[int, int] = {}
    if hub_ids:
        coins_out = {
            uid: int(total or 0)
            for uid, total in (
                await db.execute(
                    select(TradeOffer.sender_id, func.sum(TradeOffer.sender_coins))
                    .where(coin_trade, TradeOffer.sender_id.in_(hub_ids))
                    .group_by(TradeOffer.sender_id)
                )
            ).all()
        }

    farm_rows = []
    if hub_ids:
        farm_rows = (
            await db.execute(
                select(
                    TradeOffer.sender_id,
                    func.sum(TradeOffer.sender_coins).label("sent"),
                    func.count(func.distinct(TradeOffer.receiver_id)).label("hubs"),
                )
                .where(coin_trade, TradeOffer.receiver_id.in_(hub_ids))
                .group_by(TradeOffer.sender_id)
                .order_by(func.sum(TradeOffer.sender_coins).desc())
            )
        ).all()

    all_ids = list({*hub_ids, *(r.sender_id for r in farm_rows)})
    users: dict[int, User] = {}
    if all_ids:
        users = {
            u.id: u for u in (await db.execute(select(User).where(User.id.in_(all_ids)))).scalars().all()
        }
    paid = await _stars_paid(db, all_ids)

    def _user(uid: int) -> Optional[dict]:
        u = users.get(uid)
        if u is None or u.is_admin:
            return None
        return {
            "id": u.id, "username": u.username, "telegram_id": u.telegram_id, "balance": u.balance,
            "registered": u.created_at, "last_seen": u.last_seen_at, "is_banned": u.is_banned,
            "stars_paid": paid.get(u.id, 0),
        }

    hubs = []
    for r in hub_rows:
        base = _user(r.receiver_id)
        if base:
            hubs.append({**base, "senders": int(r.senders), "coins_in": int(r.coins_in or 0),
                         "coins_out": coins_out.get(r.receiver_id, 0)})
    farms = []
    for r in farm_rows:
        base = _user(r.sender_id)
        if base:
            farms.append({**base, "coins_sent": int(r.sent or 0), "hubs": int(r.hubs),
                          "is_hub": r.sender_id in hub_ids})

    # Registration bursts: grouped by hour in Python (light id/created_at
    # rows only) so it works the same on Postgres and the SQLite test DB.
    farm_ids = {f["id"] for f in farms}
    per_hour: dict[datetime, list[int]] = {}
    for uid, created in (
        await db.execute(select(User.id, User.created_at).where(User.created_at >= since))
    ).all():
        per_hour.setdefault(created.replace(minute=0, second=0, microsecond=0), []).append(uid)
    bursts = sorted(
        (
            {"hour": hour, "registered": len(ids), "farm_accounts": sum(1 for i in ids if i in farm_ids)}
            for hour, ids in per_hour.items() if len(ids) >= burst_min
        ),
        key=lambda b: b["registered"], reverse=True,
    )[:50]

    def _summary(rows: list[dict]) -> dict:
        open_rows = [x for x in rows if not x["is_banned"]]
        return {
            "total": len(rows),
            "not_banned": len(open_rows),
            "not_banned_unpaid": sum(1 for x in open_rows if not x["stars_paid"]),
            "coins": sum(x.get("coins_in", x.get("coins_sent", 0)) for x in rows),
        }

    return {
        "min_senders": min_senders, "days": days, "burst_min": burst_min,
        "hubs": hubs[:MAX_LIST], "hubs_summary": _summary(hubs),
        "farms": farms[:MAX_LIST], "farms_summary": _summary(farms),
        "bursts": bursts,
    }


async def ban_users(db: AsyncSession, user_ids: list[int]) -> list[int]:
    """Bans (and trade-bans) the given accounts; admins and already banned
    ones are skipped. Returns the ids actually banned."""
    ids = list(dict.fromkeys(user_ids))
    if not ids:
        raise ConflictError("Нет аккаунтов для бана")
    if len(ids) > MAX_BAN_BATCH:
        raise ConflictError(f"За раз можно забанить не больше {MAX_BAN_BATCH}")
    banned = (
        await db.execute(
            update(User)
            .where(User.id.in_(ids), User.is_admin.is_(False), User.is_banned.is_(False))
            .values(is_banned=True, is_trade_banned=True)
            .returning(User.id)
        )
    ).scalars().all()
    return list(banned)
