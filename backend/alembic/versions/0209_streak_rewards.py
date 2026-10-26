"""«N дней подряд»: streak_rewards (one keepsake per player per milestone,
shown as a popup) and GameConfig.streak_rewards — 100 days in a row: badge
«Ветеран» + a legendary card + 25 000 coins.

Revision ID: 0209
Revises: 0208
Create Date: 2026-10-26
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0209"
down_revision: Union[str, None] = "0208"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    op.create_table(
        "streak_rewards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("rewards", sa.JSON(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "days", name="uq_streak_rewards_user_days"),
    )
    op.create_index("ix_streak_rewards_user_id", "streak_rewards", ["user_id"])
    op.add_column("game_config", sa.Column("streak_rewards", sa.JSON(), nullable=True))
    badge = conn.execute(sa.text(
        "INSERT INTO badges (name, icon, is_active, sort_order, created_at, updated_at) "
        "VALUES ('Ветеран', '🎖️', true, 953, now(), now()) RETURNING id"
    )).scalar_one()
    rewards = [{"days": 100, "coins": 25000, "pack_id": None, "card_rarity": "legendary", "badge_id": badge,
                "cosmetic_id": None}]
    conn.execute(sa.text("UPDATE game_config SET streak_rewards = CAST(:r AS json)"), {"r": json.dumps(rewards)})
    op.alter_column("game_config", "streak_rewards", nullable=False)


def downgrade() -> None:
    op.drop_column("game_config", "streak_rewards")
    op.drop_index("ix_streak_rewards_user_id", table_name="streak_rewards")
    op.drop_table("streak_rewards")
    op.execute("DELETE FROM badges WHERE name = 'Ветеран' AND NOT EXISTS "
               "(SELECT 1 FROM user_badges ub WHERE ub.badge_id = badges.id)")
