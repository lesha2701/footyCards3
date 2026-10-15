"""Shrinks the images already stored under backend/static that the database
points at (players, coaches, stadiums, packs, club packs, collections,
badges, trophies, gift sets, league tiers, lifestyle items) — uploads made
before image_service started optimising them were kept as-is, up to
~2.5 MB PNGs.

For every referenced file that isn't already WebP (GIFs are skipped — they
may be animated) it writes an optimised `<same name>.webp` next to the
original with image_service.optimize_image and repoints every row that
referenced the old path. Originals are left on disk (delete them yourself
once the app has been checked), so the change is reversible by pointing the
rows back. Idempotent: re-running finds nothing left to do.

Default is a dry run that only reports the savings.

Usage (from backend/, DATABASE_URL pointing at the DB to update):

    python -m scripts.optimize_static_images            # dry run
    python -m scripts.optimize_static_images --apply
"""
import argparse
import asyncio
import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.services.image_service import MAX_SIDE, STATIC_DIR, optimize_image

TABLES = (
    "players", "coaches", "stadiums", "packs", "club_packs", "card_collections",
    "badges", "trophy_definitions", "gift_sets", "league_tiers", "lifestyle_items",
)
DEFAULT_MAX_SIDE = 768


def _max_side(relative_path: str) -> int:
    return MAX_SIDE.get(relative_path.split("/", 1)[0], DEFAULT_MAX_SIDE)


def _resolve(relative_path: str) -> Path | None:
    full = (STATIC_DIR / relative_path).resolve()
    return full if STATIC_DIR.resolve() in full.parents and full.is_file() else None


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write .webp files and update the database")
    args = parser.parse_args()

    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        paths: dict[str, list[str]] = {}
        for table in TABLES:
            exists = (await conn.execute(text("SELECT to_regclass(:t)"), {"t": table})).scalar()
            if not exists:
                continue
            rows = await conn.execute(text(f"SELECT DISTINCT image_path FROM {table} WHERE image_path IS NOT NULL"))
            for (path,) in rows:
                paths.setdefault(path, []).append(table)

        total_before = total_after = changed = missing = 0
        for rel, tables in sorted(paths.items()):
            ext = rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
            if ext in ("webp", "gif"):
                continue
            src = _resolve(rel)
            if src is None:
                missing += 1
                continue
            original = src.read_bytes()
            optimised, new_ext = optimize_image(original, ext, _max_side(rel))
            if new_ext != "webp":
                continue  # Pillow couldn't decode it — leave it alone
            new_rel = rel.rsplit(".", 1)[0] + ".webp"
            total_before += len(original)
            total_after += len(optimised)
            changed += 1
            print(f"{rel}: {len(original) // 1024} KB -> {len(optimised) // 1024} KB ({', '.join(tables)})")
            if args.apply:
                (STATIC_DIR / new_rel).write_bytes(optimised)
                for table in tables:
                    await conn.execute(
                        text(f"UPDATE {table} SET image_path = :new WHERE image_path = :old"),
                        {"new": new_rel, "old": rel},
                    )

        print(
            f"\n{'Converted' if args.apply else 'Would convert'} {changed} file(s): "
            f"{total_before // 1024} KB -> {total_after // 1024} KB; {missing} referenced file(s) missing on disk."
        )
        if not args.apply:
            print("Dry run — nothing written. Re-run with --apply.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
