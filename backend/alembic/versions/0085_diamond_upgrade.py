"""Diamond card leveling: per-card rating bonus + admin-tunable feed-cost tiers

Revision ID: 0085
Revises: 0084
Create Date: 2026-09-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0085"
down_revision: Union[str, None] = "0084"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_cards", sa.Column("diamond_rating_bonus", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "diamond_upgrade_tiers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("min_rating", sa.Integer(), nullable=False),
        sa.Column("max_rating", sa.Integer(), nullable=False),
        sa.Column("common_cost", sa.Integer(), nullable=False),
        sa.Column("rare_cost", sa.Integer(), nullable=False),
        sa.Column("epic_cost", sa.Integer(), nullable=False),
        sa.Column("legendary_cost", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Seeds exactly the one band product gave us (60-70: 10 common / 5 rare /
    # 3 epic / 1 legendary per +1 rating) — higher bands are added by an
    # admin via the admin panel, not guessed here.
    op.execute(
        """
        INSERT INTO diamond_upgrade_tiers
            (min_rating, max_rating, common_cost, rare_cost, epic_cost, legendary_cost, is_active)
        VALUES (60, 70, 10, 5, 3, 1, true)
        """
    )


def downgrade() -> None:
    op.drop_table("diamond_upgrade_tiers")
    op.drop_column("user_cards", "diamond_rating_bonus")
