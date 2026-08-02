"""player attack/defense stats

Adds `attack_rating`/`defense_rating` to players — nullable, schema-only.
No data backfill here on purpose: `backend/app/backfill_player_stats.py` is
a standalone, re-runnable script (same convention as `app/seed.py`) that
fills these in from a position+rating formula, meant to be run once after
this migration against every environment (dev and the production stand
alike, since the production player catalog is larger than the dev seed and
this needs to be repeatable there too):

    python -m app.backfill_player_stats

New players created after this migration get a value automatically at
creation time (see `app/routers/admin_players.py::create_player`), so NULL
should only ever be seen on rows that predate this migration, until the
backfill script runs.

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("players", sa.Column("attack_rating", sa.Integer(), nullable=True))
    op.add_column("players", sa.Column("defense_rating", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("players", "defense_rating")
    op.drop_column("players", "attack_rating")
