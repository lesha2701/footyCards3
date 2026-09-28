from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.player_tournament import PlayerTournamentParticipant
from app.models.user import User
from app.schemas.player_tournament_ranking import (
    PlayerTournamentRankingEntry, PlayerTournamentRankingMetric, PlayerTournamentRankingOut,
)

# Mirrors club_ranking_service._DIRECT_COLUMNS exactly, one column per metric.
_DIRECT_COLUMNS = {
    PlayerTournamentRankingMetric.cups: User.tournament_cups_count,
    PlayerTournamentRankingMetric.stars: User.tournament_stars_count,
}


async def get_player_tournament_ranking(
    db: AsyncSession, metric: PlayerTournamentRankingMetric, current_user_id: int, limit: int = 10
) -> PlayerTournamentRankingOut:
    column = _DIRECT_COLUMNS[metric]
    played_user_ids = select(PlayerTournamentParticipant.user_id).distinct().subquery()
    stmt = (
        select(User, column)
        .where(User.id.in_(select(played_user_ids.c.user_id)), User.is_banned.is_(False), User.is_admin.is_(False))
        .order_by(column.desc(), User.id)
    )
    rows = (await db.execute(stmt)).all()

    def to_entry(rank: int, user: User, value) -> PlayerTournamentRankingEntry:
        return PlayerTournamentRankingEntry(
            rank=rank, user_id=user.id, display_name=user.full_display_name(), value=int(value or 0),
        )

    top = [to_entry(i + 1, user, value) for i, (user, value) in enumerate(rows[:limit])]

    me = None
    for i, (user, value) in enumerate(rows):
        if user.id == current_user_id:
            me = to_entry(i + 1, user, value)
            break

    return PlayerTournamentRankingOut(metric=metric, top=top, me=me)
