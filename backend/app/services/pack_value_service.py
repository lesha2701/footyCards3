"""Expected quick-sell value of a pack: card_count × Σ P(rarity) × average
quick_sell_price of the players that rarity can drop (the same pool as
pack_service.pick_random_player). Ignores the guaranteed-minimum reroll and
coach/stadium/token bonus drops, so it slightly underestimates. Shown to
admins (economy) and to players on pack cards ("в среднем ~N монет")."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.card_collection import CardCollection
from app.models.enums import Rarity
from app.models.pack import Pack
from app.models.player import Player


async def rarity_quick_sell_averages(db: AsyncSession) -> dict[Rarity, tuple[float, int]]:
    rows = (await db.execute(
        select(Player.rarity, func.avg(Player.quick_sell_price), func.count(Player.id))
        .outerjoin(CardCollection, Player.collection_id == CardCollection.id)
        .where(
            Player.is_active.is_(True), Player.is_pack_droppable.is_(True),
            (Player.collection_id.is_(None)) | (CardCollection.is_active.is_(True)),
        )
        .group_by(Player.rarity)
    )).all()
    return {r: (float(a or 0), int(n)) for r, a, n in rows}


def pack_rarity_breakdown(pack: Pack, averages: dict[Rarity, tuple[float, int]]) -> tuple[float, list[dict]]:
    """(expected value of the whole pack, per-rarity rows)."""
    total_p = sum(float(rp.probability) for rp in pack.rarity_probabilities) or 1.0
    per_card = 0.0
    rows = []
    for rp in sorted(pack.rarity_probabilities, key=lambda x: list(Rarity).index(x.rarity)):
        p = float(rp.probability) / total_p
        avg, pool = averages.get(rp.rarity, (0.0, 0))
        per_card += p * avg
        rows.append({"rarity": rp.rarity.value, "probability": round(p, 4), "avg_quick_sell": round(avg, 1), "pool_size": pool})
    return round(per_card * pack.card_count, 1), rows
