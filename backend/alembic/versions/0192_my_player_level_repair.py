"""«Мой игрок»: give back the levels lost when the admin made the XP curve
steeper. Levels are derived from XP, so the steeper curve dropped players
below the level they had already reached and spent points for — new levels
then gave no points until they caught up. Every player gets at least the
higher of the level last shown to the player (level_seen) and the level their spent
points need. From now on the admin rebases XP when the curve changes
(my_player_service.rebase_xp_curve).

Revision ID: 0192
Revises: 0191
Create Date: 2026-10-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0192"
down_revision: Union[str, None] = "0191"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    config = bind.execute(sa.text(
        "SELECT my_player_xp_level_base, my_player_xp_level_step, my_player_points_per_level FROM game_config WHERE id = 1"
    )).first()
    if config is None:
        return
    base, step, per_level = config

    def need(level: int) -> int:
        return max(1, base + step * (level - 1))

    def level_of(xp: int) -> int:
        level = 1
        while xp >= need(level) and level < 500:
            xp -= need(level)
            level += 1
        return level

    rows = bind.execute(sa.text(
        "SELECT u.id, u.my_player_xp, p.level_seen, p.points_spent "
        "FROM users u JOIN my_players p ON p.user_id = u.id"
    )).all()
    changes = []
    for user_id, xp, level_seen, points_spent in rows:
        floor = max(level_seen or 0, (-(-(points_spent or 0) // per_level) + 1) if per_level > 0 else 0)
        if floor > level_of(xp or 0):
            changes.append({"id": user_id, "xp": sum(need(lvl) for lvl in range(1, min(floor, 500)))})
    if changes:
        bind.execute(sa.text("UPDATE users SET my_player_xp = :xp WHERE id = :id"), changes)


def downgrade() -> None:
    pass  # data repair: nothing to undo
