"""«Академия» building: slower and more modest — builds take 24 h for the
first level up to 7 days for the last, smaller wing effects, higher costs,
1 Star per hour of speed-up, a rarer scouting report.

Only rows still on the 0147 defaults are updated (an admin's own tuning is
kept); the column server defaults follow the new values.

Revision ID: 0149
Revises: 0148
Create Date: 2026-10-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0149"
down_revision: Union[str, None] = "0148"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_BUILDINGS = '{"scout": {"costs": [2000, 5000, 10000, 20000, 40000], "hours": [1, 4, 8, 16, 24], "effect": [1, 2, 3, 4, 5]}, "training": {"costs": [2000, 5000, 10000, 20000, 40000], "hours": [1, 4, 8, 16, 24], "effect": [4, 8, 12, 16, 20]}, "dorm": {"costs": [3000, 6000, 12000, 24000, 48000], "hours": [2, 6, 12, 18, 24], "effect": [1, 1, 2, 2, 3]}, "staff": {"costs": [2500, 6000, 12000, 24000, 45000], "hours": [2, 6, 10, 16, 24], "effect": [5, 10, 15, 20, 25]}, "hall": {"costs": [1000, 3000, 6000, 12000, 25000], "hours": [1, 2, 4, 8, 12], "effect": [1, 2, 3, 4, 5]}}'
NEW_BUILDINGS = '{"scout": {"costs": [3000, 8000, 16000, 32000, 60000], "hours": [24, 48, 72, 120, 168], "effect": [1, 1, 2, 2, 3]}, "training": {"costs": [3000, 8000, 16000, 32000, 60000], "hours": [24, 48, 72, 120, 168], "effect": [2, 4, 6, 8, 10]}, "dorm": {"costs": [4000, 10000, 20000, 40000, 75000], "hours": [24, 48, 72, 120, 168], "effect": [1, 1, 1, 1, 2]}, "staff": {"costs": [3500, 9000, 18000, 36000, 65000], "hours": [24, 48, 72, 120, 168], "effect": [3, 5, 7, 9, 12]}, "hall": {"costs": [1500, 4000, 8000, 16000, 30000], "hours": [24, 48, 72, 120, 168], "effect": [1, 1, 2, 2, 3]}}'
OLD_SCOUT = '{"chance_pct": [15, 20, 25, 30, 40], "cooldown_days": [7, 6, 5, 4, 3], "consolation_coins": [200, 300, 400, 500, 700]}'
NEW_SCOUT = '{"chance_pct": [10, 12, 14, 16, 20], "cooldown_days": [10, 9, 8, 8, 7], "consolation_coins": [100, 150, 200, 250, 300]}'


def _swap(column: str, old: str, new: str) -> None:
    op.get_bind().execute(
        sa.text(f"UPDATE game_config SET {column} = CAST(:new AS json) "
                f"WHERE CAST({column} AS jsonb) = CAST(:old AS jsonb)"),
        {"new": new, "old": old},
    )
    op.alter_column("game_config", column, server_default=new)


def upgrade() -> None:
    _swap("academy_buildings", OLD_BUILDINGS, NEW_BUILDINGS)
    _swap("academy_scout_report", OLD_SCOUT, NEW_SCOUT)
    op.execute("UPDATE game_config SET academy_stars_per_hour = 1 WHERE academy_stars_per_hour = 2")
    op.alter_column("game_config", "academy_stars_per_hour", server_default="1")


def downgrade() -> None:
    _swap("academy_buildings", NEW_BUILDINGS, OLD_BUILDINGS)
    _swap("academy_scout_report", NEW_SCOUT, OLD_SCOUT)
    op.execute("UPDATE game_config SET academy_stars_per_hour = 2 WHERE academy_stars_per_hour = 1")
    op.alter_column("game_config", "academy_stars_per_hour", server_default="2")
