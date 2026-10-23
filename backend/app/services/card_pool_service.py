"""The cards a game mode picks from, without loading whole collections.

Some players own tens of thousands of cards — mostly plain duplicates.
Loading every copy as an ORM object (with its Player) on each screen made
the API workers swell by hundreds of megabytes. Modes that only need the
strongest copies call load_top_copies instead: the ranking runs in SQL and
only the kept rows are loaded.
"""
from typing import Iterable, Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.card import UserCard
from app.models.player import Player

# Copies kept per player template: enough for modes that may field a
# duplicate (and for skilled copies to compete), far below what big
# collections hold.
COPIES_PER_PLAYER = 3


def _score():
    """Rating with everything the copy adds — mirrors
    player_stats_service.card_rating_bonus."""
    artifact = case(
        (UserCard.artifact_bonus_owner_id == UserCard.owner_id, func.coalesce(UserCard.artifact_rating_bonus, 0)), else_=0,
    )
    return (
        Player.rating + func.coalesce(UserCard.diamond_rating_bonus, 0) + func.coalesce(UserCard.star_rating_bonus, 0)
        + func.coalesce(UserCard.path_rating_bonus, 0) + func.coalesce(UserCard.equipment_rating_bonus, 0) + artifact
    )


def top_copy_ids(user_id: int, per_player: int = COPIES_PER_PLAYER, unlocked_only: bool = False):
    """Select of the ids of the `per_player` strongest copies of each player
    template the user owns (skilled copies first among equals)."""
    conditions = [UserCard.owner_id == user_id]
    if unlocked_only:
        conditions.append(UserCard.is_locked_by_admin.is_(False))
    ranked = (
        select(
            UserCard.id.label("id"),
            func.row_number().over(
                partition_by=UserCard.player_id,
                order_by=(_score().desc(), func.coalesce(UserCard.skill_level, 0).desc(), UserCard.id),
            ).label("n"),
        )
        .join(Player, Player.id == UserCard.player_id)
        .where(*conditions)
        .subquery()
    )
    return select(ranked.c.id).where(ranked.c.n <= per_player)


async def load_top_copies(
    db: AsyncSession, user_id: int, *, per_player: int = COPIES_PER_PLAYER,
    include: Optional[Iterable[int]] = None, unlocked_only: bool = False,
) -> list[UserCard]:
    """The strongest copies of each player (see top_copy_ids) plus the cards
    in `include` (saved squads, submitted picks) when the user owns them,
    with their players loaded."""
    wanted = UserCard.id.in_(top_copy_ids(user_id, per_player, unlocked_only))
    extra = [i for i in (include or ()) if isinstance(i, int)]
    if extra:
        wanted = wanted | UserCard.id.in_(extra)
    conditions = [UserCard.owner_id == user_id, wanted]
    if unlocked_only:
        conditions.append(UserCard.is_locked_by_admin.is_(False))
    rows = (await db.execute(
        select(UserCard).where(*conditions).options(joinedload(UserCard.player))
    )).unique().scalars().all()
    return list(rows)
