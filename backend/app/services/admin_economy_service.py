"""Admin analytics for tuning the economy: where coins come from and go,
pack/skill-token flow, and the expected quick-sell value of a pack — so
probability and price changes are measured instead of guessed."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.models.card_collection import CardCollection
from app.models.card_skill import CardSkillLedger
from app.models.enums import Rarity
from app.models.pack import Pack, PackOpening
from app.models.player import Player
from app.models.transaction import CoinTransaction


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
    """Expected quick-sell value of one pack = card_count × Σ P(rarity) ×
    average quick_sell_price of the players that rarity can drop (same pool
    as pack_service.pick_random_player). Ignores the guaranteed-minimum
    reroll and coach/stadium/token bonus drops, so it is a slight
    underestimate — good enough to compare price vs. value."""
    pack = (await db.execute(
        select(Pack).where(Pack.id == pack_id).options(selectinload(Pack.rarity_probabilities))
    )).scalar_one_or_none()
    if pack is None:
        raise NotFoundError("Пак не найден")

    avg_rows = (await db.execute(
        select(Player.rarity, func.avg(Player.quick_sell_price), func.count(Player.id))
        .outerjoin(CardCollection, Player.collection_id == CardCollection.id)
        .where(
            Player.is_active.is_(True), Player.is_pack_droppable.is_(True),
            (Player.collection_id.is_(None)) | (CardCollection.is_active.is_(True)),
        )
        .group_by(Player.rarity)
    )).all()
    avg_by_rarity = {r: (float(a or 0), int(n)) for r, a, n in avg_rows}

    total_p = sum(float(rp.probability) for rp in pack.rarity_probabilities) or 1.0
    rarities = []
    per_card = 0.0
    for rp in sorted(pack.rarity_probabilities, key=lambda x: list(Rarity).index(x.rarity)):
        p = float(rp.probability) / total_p
        avg, pool = avg_by_rarity.get(rp.rarity, (0.0, 0))
        per_card += p * avg
        rarities.append({"rarity": rp.rarity.value, "probability": round(p, 4), "avg_quick_sell": round(avg, 1), "pool_size": pool})
    expected = per_card * pack.card_count
    return {
        "pack_id": pack.id,
        "price": pack.price,
        "card_count": pack.card_count,
        "expected_quick_sell_value": round(expected, 1),
        "value_to_price": round(expected / pack.price, 3) if pack.price else None,
        "rarities": rarities,
    }
