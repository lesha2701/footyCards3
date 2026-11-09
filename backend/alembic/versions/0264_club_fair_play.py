"""Club fair play: reward tenure and war minimum, rejoin pause, absent captains,
lost games worth less.

Revision ID: 0264
Revises: 0263
Create Date: 2026-11-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0264"
down_revision: Union[str, None] = "0263"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONFIG = (
    ("club_league_lost_game_pct", "50"), ("club_league_min_game_seconds", "20"), ("club_war_min_points", "10"),
    ("club_reward_min_tenure_hours", "24"), ("club_rejoin_cooldown_hours", "24"), ("club_captain_absent_days", "14"),
)


def upgrade() -> None:
    for name, default in _CONFIG:
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=default))
    op.add_column("users", sa.Column("club_left_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("club_reward_grants", sa.Column("eligible_user_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("club_reward_grants", "eligible_user_ids")
    op.drop_column("users", "club_left_at")
    for name, _default in reversed(_CONFIG):
        op.drop_column("game_config", name)
