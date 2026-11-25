"""«Редкие версии»: now and then a card comes out of a pack as a special
print of the same player — a gold frame, his signature on the photo, or
the night edition. Purely a look (and a reason to show it off or price it
higher on the market): same player, same rating, same rules.

Rolled once, when the copy is created, only for cards that come out of a
pack (bought, free, for Stars, in chat, on the wheel, the daily reward);
never for an «Академия» design. Chances are per mille in GameConfig.
"""
import random
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import CardSource
from app.models.player import Player
from app.services.game_config_service import get_config

FINISHES = ("autograph", "night", "gold")  # rarest first
PACK_SOURCES = {
    CardSource.pack, CardSource.free_pack, CardSource.stars_purchase,
    CardSource.chat_pack, CardSource.wheel, CardSource.daily_reward,
}


def pick_finish(roll: float, gold: int, autograph: int, night: int) -> Optional[str]:
    """`roll` in [0, 1); the per-mille chances stack, rarest first."""
    edge = 0.0
    for name, per_mille in (("autograph", autograph), ("night", night), ("gold", gold)):
        edge += max(per_mille, 0) / 1000
        if roll < edge:
            return name
    return None


async def roll_finish(db: AsyncSession, source: CardSource, player_id: int) -> Optional[str]:
    if source not in PACK_SOURCES:
        return None
    player = await db.get(Player, player_id)
    if player is None or player.path_talent_code:
        return None
    config = await get_config(db)
    return pick_finish(
        random.random(),
        config.finish_gold_per_mille, config.finish_autograph_per_mille, config.finish_night_per_mille,
    )
