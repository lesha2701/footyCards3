"""Backfills Player.attack_rating / defense_rating for any row where either
is still NULL, using the position+rating default formula
(app/services/player_stats_service.py). Safe to re-run — only touches rows
where a stat is still NULL, never overwrites an admin's manual edit.

Run (from backend/, with DATABASE_URL pointing at a migrated DB):
    python -m app.backfill_player_stats
"""
import asyncio

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.player import Player
from app.services.player_stats_service import compute_default_attack_defense


async def backfill(db: AsyncSession) -> int:
    result = await db.execute(
        select(Player).where(or_(Player.attack_rating.is_(None), Player.defense_rating.is_(None)))
    )
    players = result.scalars().all()
    for player in players:
        default_attack, default_defense = compute_default_attack_defense(player.rating, player.position)
        if player.attack_rating is None:
            player.attack_rating = default_attack
        if player.defense_rating is None:
            player.defense_rating = default_defense
        db.add(player)
    await db.commit()
    return len(players)


async def main() -> None:
    async with AsyncSessionLocal() as db:
        count = await backfill(db)
        print(f"Backfilled attack/defense stats for {count} player(s).")


if __name__ == "__main__":
    asyncio.run(main())
