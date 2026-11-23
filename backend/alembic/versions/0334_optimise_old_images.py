"""Old admin uploads (PNG/JPEG up to ~2.5 MB) → optimised WebP, once

image_service shrinks new uploads, but files uploaded before that were
kept as-is and players still download them. This runs
scripts/optimize_static_images.optimise on deploy: for every row with an
`image_path` that isn't WebP it writes `<name>.webp` next to the file and
repoints the row. Originals stay on disk, so downgrade can point back.

Revision ID: 0334
Revises: 0333
Create Date: 2026-11-24
"""
import logging
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0334"
down_revision: Union[str, None] = "0333"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    from scripts.optimize_static_images import optimise

    try:
        optimise(conn, apply=True, log=logger.info)
    except OSError as exc:
        # No static directory or a read-only one: the images simply stay as
        # they are — never block a deploy over a speed-up.
        logger.warning("image optimisation skipped: %s", exc)


def downgrade() -> None:
    # The originals were kept next to the .webp copies: point the rows back
    # where such an original exists.
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return
    from app.services.image_service import STATIC_DIR
    from scripts.optimize_static_images import _tables

    for table in _tables(conn):
        rows = conn.execute(text(f'SELECT DISTINCT image_path FROM "{table}" WHERE image_path LIKE \'%.webp\''))
        for (path,) in rows:
            stem = path[: -len(".webp")]
            for ext in ("png", "jpg", "jpeg"):
                if (STATIC_DIR / f"{stem}.{ext}").is_file():
                    conn.execute(
                        text(f'UPDATE "{table}" SET image_path = :old WHERE image_path = :new'),
                        {"old": f"{stem}.{ext}", "new": path},
                    )
                    break
