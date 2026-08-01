"""card arena rework: interactive shots + flat rating system

Resets every user's arena_rating to 0 (the old 1000-start, strength-difference
formula is being replaced by a flat +3/+1/-1 win/draw/loss system, so the old
values are on an incompatible scale). This reset is NOT reversible — downgrade()
can only put everyone back to the 1000 default, not restore original per-user
values.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    match_status_enum = sa.Enum("in_progress", "finished", name="match_status_enum")
    match_status_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "matches", sa.Column("status", match_status_enum, nullable=False, server_default="finished")
    )
    op.add_column("matches", sa.Column("server_state", sa.JSON(), nullable=True))
    op.alter_column("matches", "result", nullable=True)

    op.add_column(
        "game_config",
        sa.Column("match_shot_miss_chance_min", sa.Numeric(4, 2), nullable=False, server_default="0.08"),
    )
    op.add_column(
        "game_config",
        sa.Column("match_shot_miss_chance_max", sa.Numeric(4, 2), nullable=False, server_default="0.30"),
    )
    op.add_column(
        "game_config",
        sa.Column("match_defender_block_chance_min", sa.Numeric(4, 2), nullable=False, server_default="0.10"),
    )
    op.add_column(
        "game_config",
        sa.Column("match_defender_block_chance_max", sa.Numeric(4, 2), nullable=False, server_default="0.35"),
    )
    op.add_column(
        "game_config", sa.Column("match_shot_type_in_box_weight", sa.Integer(), nullable=False, server_default="55")
    )
    op.add_column(
        "game_config",
        sa.Column("match_shot_type_long_range_weight", sa.Integer(), nullable=False, server_default="35"),
    )
    op.add_column(
        "game_config",
        sa.Column("match_shot_type_empty_net_weight", sa.Integer(), nullable=False, server_default="10"),
    )

    op.alter_column("users", "arena_rating", server_default="0")
    op.execute("UPDATE users SET arena_rating = 0")


def downgrade() -> None:
    # Best-effort only: original per-user arena_rating values are not recoverable
    # once upgrade() has run.
    op.execute("UPDATE users SET arena_rating = 1000")
    op.alter_column("users", "arena_rating", server_default="1000")

    op.drop_column("game_config", "match_shot_type_empty_net_weight")
    op.drop_column("game_config", "match_shot_type_long_range_weight")
    op.drop_column("game_config", "match_shot_type_in_box_weight")
    op.drop_column("game_config", "match_defender_block_chance_max")
    op.drop_column("game_config", "match_defender_block_chance_min")
    op.drop_column("game_config", "match_shot_miss_chance_max")
    op.drop_column("game_config", "match_shot_miss_chance_min")

    op.alter_column("matches", "result", nullable=False)
    op.drop_column("matches", "server_state")
    op.drop_column("matches", "status")
    sa.Enum(name="match_status_enum").drop(op.get_bind(), checkfirst=True)
