"""«Где проводят время»: seconds per player, section and local day.

The app (`lib/sectionTime.ts`) counts active time per section — the page is
visible and the player did something in the last 90 s — and sends what it
counted about once a minute. Nothing here pays or unlocks anything, but the
numbers still come from the client, so a batch is capped: at most
MAX_SECTIONS sections and MAX_BATCH_SECONDS seconds in all (a minute of
counting plus some slack), and the router lets a player send only a few
batches a minute. A forged client can add at most a few minutes an hour.
"""
import re
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import local_today
from app.models.user_activity import SectionTimeDaily

MAX_SECTIONS = 12
MAX_BATCH_SECONDS = 75
# "home", "packs", "play/penalty", "clubs", … — see sectionOf in lib/sectionTime.ts.
SECTION_RE = re.compile(r"^[a-z0-9-]{1,19}(/[a-z0-9-]{1,19})?$")


def clean(sections: dict[str, int]) -> dict[str, int]:
    """The batch as it will be stored: known-shaped keys, whole positive
    seconds, the biggest sections first until the batch cap is spent."""
    valid = [(k, int(v)) for k, v in sections.items() if SECTION_RE.match(k) and int(v) > 0]
    valid.sort(key=lambda kv: (-kv[1], kv[0]))
    out: dict[str, int] = {}
    left = MAX_BATCH_SECONDS
    for key, seconds in valid[:MAX_SECTIONS]:
        if left <= 0:
            break
        take = min(seconds, left)
        out[key] = take
        left -= take
    return out


async def record(db: AsyncSession, user_id: int, sections: dict[str, int], day: date | None = None) -> dict[str, int]:
    batch = clean(sections)
    if not batch:
        return batch
    day = day or local_today()
    if db.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    # Sorted: two batches of one player lock their rows in the same order.
    for section, seconds in sorted(batch.items()):
        stmt = insert(SectionTimeDaily).values(day=day, section=section, user_id=user_id, seconds=seconds)
        await db.execute(stmt.on_conflict_do_update(
            index_elements=["day", "section", "user_id"],
            set_={"seconds": SectionTimeDaily.seconds + seconds},
        ))
    await db.commit()
    return batch


async def report(db: AsyncSession, first_day: date) -> list[dict]:
    """Per section since `first_day`: players, total seconds and the average
    minutes a player spent there on a day he came to it."""
    rows = (await db.execute(
        select(
            SectionTimeDaily.section,
            func.count(func.distinct(SectionTimeDaily.user_id)),
            func.sum(SectionTimeDaily.seconds),
            func.count(),
        )
        .where(SectionTimeDaily.day >= first_day)
        .group_by(SectionTimeDaily.section)
    )).all()
    out = [
        {
            "section": section,
            "players": players,
            "seconds": int(seconds or 0),
            "minutes_per_player_day": round(int(seconds or 0) / player_days / 60, 1) if player_days else 0.0,
        }
        for section, players, seconds, player_days in rows
    ]
    return sorted(out, key=lambda r: (-r["seconds"], r["section"]))
