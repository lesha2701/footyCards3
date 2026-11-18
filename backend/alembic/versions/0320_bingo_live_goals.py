"""«Бинго недели»: more server goals, counted live from the games' own rows
over the week (bingo_service.LIVE_GOALS) — mini-games, Стратего, «21»,
«Табло удачи», «Мяч и Магия», «Контратака», «Мордобой», the wheel.

Each gets a definition whose target is 80% of what the whole server played
in the last 7 days (at least 10); it is active only when that week had at
least 20 such games, so a dead mode never blocks the reward. Active ones are
added to the week that is running now.

Revision ID: 0320
Revises: 0319
Create Date: 2026-11-18
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0320"
down_revision: Union[str, None] = "0319"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# goal type → (table, extra condition)
LIVE = {
    "mini_games_played": ("game_sessions", "status <> 'in_progress'"),
    "stratego_matches_played": ("stratego_matches", None),
    "blackjack_hands": ("blackjack_matches", None),
    "lucky_board_spins": ("lucky_board_spins", None),
    "magic_runs": ("magic_runs", None),
    "kontra_battles": ("kontra_battles", None),
    "mordoboi_matches": ("mordoboi_matches", None),
    "wheel_spins": ("wheel_spins", None),
}


def upgrade() -> None:
    # A new enum value can't be used in the transaction that adds it.
    with op.get_context().autocommit_block():
        for goal_type in LIVE:
            op.execute(f"ALTER TYPE bingo_goal_type_enum ADD VALUE IF NOT EXISTS '{goal_type}'")

    for goal_type, (table, cond) in LIVE.items():
        where = "created_at >= now() - interval '7 days'" + (f" AND {cond}" if cond else "")
        op.execute(
            f"""
            INSERT INTO bingo_goal_definitions (goal_type, target_value, is_active)
            SELECT '{goal_type}'::bingo_goal_type_enum, GREATEST(10, (c.n * 8) / 10), c.n >= 20
            FROM (SELECT count(*) AS n FROM {table} WHERE {where}) c
            WHERE NOT EXISTS (
                SELECT 1 FROM bingo_goal_definitions d WHERE d.goal_type = '{goal_type}'
            )
            """
        )

    op.execute(
        f"""
        INSERT INTO bingo_week_goals (week_id, goal_type, target_value, current_value)
        SELECT w.id, d.goal_type, d.target_value, 0
        FROM bingo_weeks w
        JOIN bingo_goal_definitions d ON d.is_active
        WHERE NOT w.reward_resolved AND w.ends_at > now()
          AND d.goal_type IN ({", ".join(f"'{t}'" for t in LIVE)})
          AND NOT EXISTS (
              SELECT 1 FROM bingo_week_goals g WHERE g.week_id = w.id AND g.goal_type = d.goal_type
          )
        """
    )


def downgrade() -> None:
    # Postgres can't drop enum values; the rows go, the values stay unused.
    types = ", ".join(f"'{t}'" for t in LIVE)
    op.execute(f"DELETE FROM bingo_week_goals WHERE goal_type::text IN ({types})")
    op.execute(f"DELETE FROM bingo_goal_definitions WHERE goal_type::text IN ({types})")
