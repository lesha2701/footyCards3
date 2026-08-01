"""card arena rework: situation + action mechanics

Adds GameConfig knobs for the new attack (shoot/pass) and defense
(tackle/block/keeper) probability rolls, replacing the old direction-guess
mechanic. `Match.server_state` needs no schema change (JSON column) — new
keys (`cards`, `red_card_applied`, `ratings.user_gk`/`opponent_gk`, and the
per-moment `actors`/`description`/`actions`) are written by application code
going forward.

In-progress matches created before this migration have the old moment shape
(no `actors`/`description`/`actions`) and cannot be resolved by the new
resolver, so they are voided with zero economy impact (no reward/rating was
ever granted for them — that only happens in `_finalize_match`).

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "game_config",
        sa.Column("match_attack_shoot_miss_chance_min", sa.Numeric(4, 2), nullable=False, server_default="0.08"),
    )
    op.add_column(
        "game_config",
        sa.Column("match_attack_shoot_miss_chance_max", sa.Numeric(4, 2), nullable=False, server_default="0.32"),
    )
    op.add_column(
        "game_config",
        sa.Column("match_pass_fail_chance_min", sa.Numeric(4, 2), nullable=False, server_default="0.05"),
    )
    op.add_column(
        "game_config",
        sa.Column("match_pass_fail_chance_max", sa.Numeric(4, 2), nullable=False, server_default="0.28"),
    )
    op.add_column(
        "game_config",
        sa.Column("match_receiver_shot_miss_chance_min", sa.Numeric(4, 2), nullable=False, server_default="0.05"),
    )
    op.add_column(
        "game_config",
        sa.Column("match_receiver_shot_miss_chance_max", sa.Numeric(4, 2), nullable=False, server_default="0.22"),
    )
    op.add_column(
        "game_config",
        sa.Column("match_tackle_foul_chance_min", sa.Numeric(4, 2), nullable=False, server_default="0.06"),
    )
    op.add_column(
        "game_config",
        sa.Column("match_tackle_foul_chance_max", sa.Numeric(4, 2), nullable=False, server_default="0.30"),
    )
    op.add_column(
        "game_config",
        sa.Column("match_tackle_red_chance_min", sa.Numeric(4, 2), nullable=False, server_default="0.05"),
    )
    op.add_column(
        "game_config",
        sa.Column("match_tackle_red_chance_max", sa.Numeric(4, 2), nullable=False, server_default="0.22"),
    )
    op.add_column(
        "game_config",
        sa.Column("match_block_fail_chance_min", sa.Numeric(4, 2), nullable=False, server_default="0.10"),
    )
    op.add_column(
        "game_config",
        sa.Column("match_block_fail_chance_max", sa.Numeric(4, 2), nullable=False, server_default="0.32"),
    )
    op.add_column(
        "game_config",
        sa.Column("match_keeper_save_chance_min", sa.Numeric(4, 2), nullable=False, server_default="0.35"),
    )
    op.add_column(
        "game_config",
        sa.Column("match_keeper_save_chance_max", sa.Numeric(4, 2), nullable=False, server_default="0.75"),
    )
    op.add_column(
        "game_config",
        sa.Column("match_red_card_strength_penalty_pct", sa.Numeric(4, 2), nullable=False, server_default="0.12"),
    )
    op.add_column(
        "game_config",
        sa.Column("match_penalty_gk_rating_penalty", sa.Integer(), nullable=False, server_default="6"),
    )

    op.execute(
        "UPDATE matches SET status = 'finished', reward_coins = 0, rating_delta = 0 "
        "WHERE status = 'in_progress'"
    )


def downgrade() -> None:
    op.drop_column("game_config", "match_penalty_gk_rating_penalty")
    op.drop_column("game_config", "match_red_card_strength_penalty_pct")
    op.drop_column("game_config", "match_keeper_save_chance_max")
    op.drop_column("game_config", "match_keeper_save_chance_min")
    op.drop_column("game_config", "match_block_fail_chance_max")
    op.drop_column("game_config", "match_block_fail_chance_min")
    op.drop_column("game_config", "match_tackle_red_chance_max")
    op.drop_column("game_config", "match_tackle_red_chance_min")
    op.drop_column("game_config", "match_tackle_foul_chance_max")
    op.drop_column("game_config", "match_tackle_foul_chance_min")
    op.drop_column("game_config", "match_receiver_shot_miss_chance_max")
    op.drop_column("game_config", "match_receiver_shot_miss_chance_min")
    op.drop_column("game_config", "match_pass_fail_chance_max")
    op.drop_column("game_config", "match_pass_fail_chance_min")
    op.drop_column("game_config", "match_attack_shoot_miss_chance_max")
    op.drop_column("game_config", "match_attack_shoot_miss_chance_min")
