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
    return {
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
