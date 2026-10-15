"""Card Arena divisions and four-style tactics: Elo-like arena points with a
promotion shield, the opponent found before kickoff, balance/division tuning
on GameConfig; old «Сбалансированная» lineups become «Владение».

Revision ID: 0148
Revises: 0147
Create Date: 2026-10-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0148"
down_revision: Union[str, None] = "0147"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_GC_INT = (
    ("arena_style_matchup_bonus_pct", "6"),
    ("arena_edge_rating_max", "12"),
    ("arena_points_k", "40"),
    ("arena_points_scale", "400"),
    ("arena_shield_matches", "3"),
    ("arena_matchmaking_window", "150"),
)
_GC_NUMERIC = (
    ("arena_share_exponent", "1.2"),
    ("arena_shot_exponent", "0.8"),
    ("arena_edge_rating_per_10pct", "2.0"),
)
_GC_JSON = (
    ("arena_division_min_points", "[0, 100, 200, 300, 400, 550, 700, 850, 1000, 1200]"),
    ("arena_division_reward_coins", "[0, 100, 150, 200, 300, 400, 500, 700, 1000, 1500]"),
    ("arena_division_coin_pct", "[100, 105, 110, 115, 120, 125, 130, 135, 140, 150]"),
)


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'arena_division_reward'")

    op.add_column("users", sa.Column("arena_points", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_users_arena_points", "users", ["arena_points"])
    op.add_column("users", sa.Column("arena_shield_matches", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("arena_best_division", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("users", sa.Column("arena_last_strength", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("arena_pending_opponent", sa.JSON(), nullable=True))

    for name, default in _GC_INT:
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=default))
    for name, default in _GC_NUMERIC:
        op.add_column("game_config", sa.Column(name, sa.Numeric(4, 2), nullable=False, server_default=default))
    for name, default in _GC_JSON:
        op.add_column(
            "game_config", sa.Column(name, sa.JSON(), nullable=False, server_default=sa.text(f"'{default}'::json")),
        )

    op.execute("UPDATE lineups SET tactic = 'possession' WHERE tactic = 'balanced'")


def downgrade() -> None:
    op.execute("UPDATE lineups SET tactic = 'balanced' WHERE tactic NOT IN ('attacking', 'defensive')")
    for name, _ in _GC_JSON + _GC_NUMERIC + _GC_INT:
        op.drop_column("game_config", name)
    op.drop_column("users", "arena_pending_opponent")
    op.drop_column("users", "arena_last_strength")
    op.drop_column("users", "arena_best_division")
    op.drop_column("users", "arena_shield_matches")
    op.drop_index("ix_users_arena_points", table_name="users")
    op.drop_column("users", "arena_points")
