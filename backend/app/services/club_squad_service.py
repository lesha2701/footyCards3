import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.club_lineup import ClubLineup, ClubLineupCard
from app.models.enums import ClubCardSource, Position
from app.models.player import Player
from app.services.club_card_service import create_club_card
from app.services.lineup_service import CATEGORY_POSITIONS, FORMATION_SLOTS

# Bench categories seeded alongside the 11 starters — one extra card per
# category, giving every fresh club a small reserve pool from day one (per
# the design spec's "so a club is never caught with nobody to substitute").
BENCH_CATEGORIES = ["GK", "DEF", "MID", "FWD"]


async def _pick_weakest_active_player_id(db: AsyncSession, positions: list[Position], excluded_player_ids: set[int]) -> int:
    query = (
        select(Player.id, Player.rating)
        .where(Player.is_active.is_(True), Player.position.in_(positions))
        .order_by(Player.rating.asc())
        .limit(20)
    )
    if excluded_player_ids:
        query = query.where(Player.id.notin_(excluded_player_ids))
    rows = (await db.execute(query)).all()
    if not rows:
        # Fall back to allowing repeats if the active player pool for this
        # position is smaller than the number of slots needing it (e.g. a
        # freshly-seeded dev database) — a duplicate weak player beats no
        # player at all for a brand-new club's starting squad.
        rows = (
            await db.execute(
                select(Player.id, Player.rating)
                .where(Player.is_active.is_(True), Player.position.in_(positions))
                .order_by(Player.rating.asc())
                .limit(20)
            )
        ).all()
    lowest_rating = rows[0][1]
    lowest_rated_ids = [player_id for player_id, rating in rows if rating == lowest_rating]
    return random.choice(lowest_rated_ids)


async def seed_starting_squad(db: AsyncSession, club_id: int) -> None:
    """Mints the club's first 15 ClubCards (11 starters, placed directly
    into a fresh ClubLineup, plus 4 bench cards — one per category) using
    the lowest-rated active Player available per slot, random among ties.
    Deliberately weak by design — the club has to earn its way up via
    packs. Called once, synchronously, from club_service.create_club."""
    lineup = ClubLineup(club_id=club_id)
    db.add(lineup)
    await db.flush()

    used_player_ids: set[int] = set()

    for slot in FORMATION_SLOTS:
        positions = list(CATEGORY_POSITIONS[slot.category])
        # Position enum members compare by value against Player.position's
        # own enum column — no str() conversion needed, matches how
        # lineup_service itself queries by these same enum members.
        player_id = await _pick_weakest_active_player_id(db, positions, used_player_ids)
        used_player_ids.add(player_id)
        club_card = await create_club_card(db, club_id, player_id, ClubCardSource.starter_seed)
        db.add(ClubLineupCard(club_lineup_id=lineup.id, club_card_id=club_card.id, slot_code=slot.code))

    for category in BENCH_CATEGORIES:
        positions = list(CATEGORY_POSITIONS[category])
        player_id = await _pick_weakest_active_player_id(db, positions, used_player_ids)
        used_player_ids.add(player_id)
        await create_club_card(db, club_id, player_id, ClubCardSource.starter_seed)
        # No ClubLineupCard row for bench cards — per this plan's "bench =
        # any club card not currently in the lineup" simplification, these
        # are just extra ClubCard rows the squad editor's picker surfaces.

    await db.flush()
