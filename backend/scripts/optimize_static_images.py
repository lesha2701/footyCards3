"""Shrinks the images already stored under backend/static that the database
points at — every table with an `image_path` column. Uploads made before
image_service started optimising them were kept as-is, up to ~2.5 MB PNGs.

For every referenced file that isn't already WebP (GIFs are skipped — they
may be animated) it writes an optimised `<same name>.webp` next to the
original with image_service.optimize_image and repoints every row that
referenced the old path. Originals are left on disk, so the change is
reversible by pointing the rows back. Idempotent: re-running finds nothing
left to do. Migration 0334 runs it once on deploy (`optimise`).

Default is a dry run that only reports the savings.

Usage (from backend/, DATABASE_URL pointing at the DB to update):

    python -m scripts.optimize_static_images            # dry run
    python -m scripts.optimize_static_images --apply
"""

import argparse
import asyncio
import os
from pathlib import Path
from typing import Callable

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.services.image_service import MAX_SIDE, STATIC_DIR, optimize_image

DEFAULT_MAX_SIDE = 768


def _max_side(relative_path: str) -> int:
    return MAX_SIDE.get(relative_path.split("/", 1)[0], DEFAULT_MAX_SIDE)


def _resolve(static_dir: Path, relative_path: str) -> Path | None:
    full = (static_dir / relative_path).resolve()
    return full if static_dir.resolve() in full.parents and full.is_file() else None


def _tables(conn: Connection) -> list[str]:
    rows = conn.execute(text(
        "SELECT table_name FROM information_schema.columns "
        "WHERE column_name = 'image_path' AND table_schema = current_schema() ORDER BY table_name"
    ))
    return [name for (name,) in rows]


def optimise(conn: Connection, apply: bool, log: Callable[[str], None] = print,
             static_dir: Path = STATIC_DIR) -> dict:
    """Converts (or, with apply=False, only measures) every referenced
    non-WebP image. Postgres only (information_schema)."""
    paths: dict[str, list[str]] = {}
    for table in _tables(conn):
        rows = conn.execute(text(f'SELECT DISTINCT image_path FROM "{table}" WHERE image_path IS NOT NULL'))
        for (path,) in rows:
            paths.setdefault(path, []).append(table)

    before = after = changed = missing = 0
    for rel, tables in sorted(paths.items()):
        ext = rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
        if ext in ("webp", "gif") or rel.startswith(("http://", "https://", "/")):
            continue
        src = _resolve(static_dir, rel)
        if src is None:
            missing += 1
            continue
        original = src.read_bytes()
        try:
            optimised, new_ext = optimize_image(original, ext, _max_side(rel))
        except Exception as exc:  # noqa: BLE001 — one broken file must not stop the rest
            log(f"{rel}: skipped ({exc})")
            continue
        if new_ext != "webp":
            continue  # Pillow couldn't decode it — leave it alone
        new_rel = rel.rsplit(".", 1)[0] + ".webp"
        before += len(original)
        after += len(optimised)
        changed += 1
        log(f"{rel}: {len(original) // 1024} KB -> {len(optimised) // 1024} KB ({', '.join(tables)})")
        if apply:
            (static_dir / new_rel).write_bytes(optimised)
            for table in tables:
                conn.execute(
                    text(f'UPDATE "{table}" SET image_path = :new WHERE image_path = :old'),
                    {"new": new_rel, "old": rel},
                )
    log(
        f"{'Converted' if apply else 'Would convert'} {changed} file(s): "
        f"{before // 1024} KB -> {after // 1024} KB; {missing} referenced file(s) missing on disk."
    )
    return {"changed": changed, "before": before, "after": after, "missing": missing}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write .webp files and update the database")
    args = parser.parse_args()

    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: optimise(c, args.apply))
    if not args.apply:
        print("Dry run — nothing written. Re-run with --apply.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
