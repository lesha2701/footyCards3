from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.club import Club, ClubMember
from app.schemas.club_ranking import ClubRankingEntry, ClubRankingMetric, ClubRankingOut

# Mirrors ranking_service.get_ranking's exact shape (one unfiltered query, Python top-N slice,
# linear scan of the full row set for "my position") — confirmed by direct read of that file
# before writing this one. Entry serialization doesn't transfer (personal entries carry
# avatar/badge; club entries carry name/logo), so ClubRankingEntry is its own schema.
_DIRECT_COLUMNS = {
    ClubRankingMetric.cups: Club.cups_count,
    ClubRankingMetric.stars: Club.stars_count,
}


async def get_club_ranking(
    db: AsyncSession, metric: ClubRankingMetric, current_user_id: int, limit: int = 10
) -> ClubRankingOut:
    column = _DIRECT_COLUMNS[metric]
    stmt = select(Club, column).where(Club.is_disbanded.is_(False)).order_by(column.desc())
    rows = (await db.execute(stmt)).all()

    def to_entry(rank: int, club: Club, value) -> ClubRankingEntry:
        return ClubRankingEntry(
            rank=rank, club_id=club.id, name=club.name,
            logo_shape=club.logo_shape, logo_color=club.logo_color, value=int(value or 0),
        )

    top = [to_entry(i + 1, club, value) for i, (club, value) in enumerate(rows[:limit])]

    my_club_id = (
        await db.execute(select(ClubMember.club_id).where(ClubMember.user_id == current_user_id))
    ).scalar_one_or_none()

    me = None
    if my_club_id is not None:
        for i, (club, value) in enumerate(rows):
            if club.id == my_club_id:
                me = to_entry(i + 1, club, value)
                break

    return ClubRankingOut(metric=metric, top=top, me=me)
