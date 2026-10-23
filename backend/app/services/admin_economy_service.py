"""Admin analytics for tuning the economy: where coins come from and go,
pack/skill-token flow, and the expected quick-sell value of a pack — so
probability and price changes are measured instead of guessed."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.models.card_skill import CardSkillLedger
from app.models.pack import Pack, PackOpening
from app.models.transaction import CoinTransaction
from app.models.user import User
from app.services.pack_value_service import pack_rarity_breakdown, rarity_quick_sell_averages


async def economy_report(db: AsyncSession, days: int) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    inflow = func.coalesce(func.sum(case((CoinTransaction.amount > 0, CoinTransaction.amount), else_=0)), 0)
    outflow = func.coalesce(func.sum(case((CoinTransaction.amount < 0, -CoinTransaction.amount), else_=0)), 0)

    by_type_rows = (await db.execute(
        select(CoinTransaction.type, inflow, outflow, func.count(CoinTransaction.id))
        .where(CoinTransaction.created_at >= since)
        .group_by(CoinTransaction.type)
    )).all()
    by_type = sorted(
        ({"type": t.value, "inflow": int(i), "outflow": int(o), "count": int(c)} for t, i, o, c in by_type_rows),
        key=lambda r: -(r["inflow"] + r["outflow"]),
    )

    day = func.date(CoinTransaction.created_at)
    daily_rows = (await db.execute(
        select(day, inflow, outflow).where(CoinTransaction.created_at >= since).group_by(day).order_by(day)
    )).all()
    daily = [{"date": str(d), "inflow": int(i), "outflow": int(o)} for d, i, o in daily_rows]

    packs_opened = int((await db.execute(
        select(func.count(PackOpening.id)).where(PackOpening.created_at >= since)
    )).scalar_one())
    token_rows = (await db.execute(
        select(
            func.coalesce(func.sum(case((CardSkillLedger.token_delta > 0, CardSkillLedger.token_delta), else_=0)), 0),
            func.coalesce(func.sum(case((CardSkillLedger.token_delta < 0, -CardSkillLedger.token_delta), else_=0)), 0),
            func.coalesce(func.sum(CardSkillLedger.coins_spent), 0),
        ).where(CardSkillLedger.created_at >= since)
    )).one()

    total_in = sum(r["inflow"] for r in by_type)
    total_out = sum(r["outflow"] for r in by_type)
    coins_in_circulation = int((await db.execute(select(func.coalesce(func.sum(User.balance), 0)))).scalar_one())
    ratio = round(total_in / total_out, 2) if total_out else None
    positive_days = sum(1 for d in daily if d["inflow"] > d["outflow"])
    return {
        "coins_in_circulation": coins_in_circulation,
        "inflow_outflow_ratio": ratio,
        "positive_days": positive_days,
        "warning": _inflation_warning(total_in, total_out, ratio, positive_days, len(daily)),
        "days": days,
        "total_inflow": total_in,
        "total_outflow": total_out,
        "net": total_in - total_out,
        "by_type": by_type,
        "daily": daily,
        "packs_opened": packs_opened,
        "skill_tokens_granted": int(token_rows[0]),
        "skill_tokens_spent": int(token_rows[1]),
        "skill_coins_spent": int(token_rows[2]),
    }


# Report heuristics for the admin, not game balance: they only decide when
# the economy page shows an inflation warning.
INFLATION_RATIO = 1.5
INFLATION_POSITIVE_DAY_SHARE = 0.8
INFLATION_MIN_DAYS = 5


def _inflation_warning(total_in: int, total_out: int, ratio, positive_days: int, day_count: int):
    if total_in > 0 and total_out == 0:
        return "За период монеты только начислялись и ни разу не тратились."
    if ratio is not None and ratio >= INFLATION_RATIO:
        return f"Начисляется в {ratio}× больше монет, чем тратится: масса монет растёт, они дешевеют."
    if day_count >= INFLATION_MIN_DAYS and positive_days / day_count >= INFLATION_POSITIVE_DAY_SHARE:
        return f"В {positive_days} из {day_count} дней начислений было больше, чем трат."
    return None


async def pack_expected_value(db: AsyncSession, pack_id: int) -> dict:
    """Expected quick-sell value of one pack vs. its price (see
    pack_value_service for what the estimate does and does not include)."""
    pack = (await db.execute(
        select(Pack).where(Pack.id == pack_id).options(selectinload(Pack.rarity_probabilities))
    )).scalar_one_or_none()
    if pack is None:
        raise NotFoundError("Пак не найден")
    expected, rarities = pack_rarity_breakdown(pack, await rarity_quick_sell_averages(db))
    return {
        "pack_id": pack.id,
        "price": pack.price,
        "card_count": pack.card_count,
        "expected_quick_sell_value": expected,
        "value_to_price": round(expected / pack.price, 3) if pack.price else None,
        "rarities": rarities,
    }
