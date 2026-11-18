"""«Бинго недели»: the player's own 3×3 card (bingo_cards) with coins for a
line and for the whole card; the server's common goal now pays only those
with a closed line. The «обмены» common goal, out of reach since the trade
limits, is switched off — for the running week too.

Revision ID: 0316
Revises: 0315
Create Date: 2026-11-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0316"
down_revision: Union[str, None] = "0315"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bingo_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("week_id", sa.Integer(), sa.ForeignKey("bingo_weeks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cells", sa.JSON(), nullable=False),
        sa.Column("lines_claimed", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("full_claimed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("coins_granted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("week_id", "user_id", name="uq_bingo_card_week_user"),
    )
    op.create_index("ix_bingo_cards_week_id", "bingo_cards", ["week_id"])
    op.create_index("ix_bingo_cards_user_id", "bingo_cards", ["user_id"])

    op.add_column("game_config", sa.Column("bingo_line_coins", sa.Integer(), nullable=False, server_default="150"))
    op.add_column("game_config", sa.Column("bingo_full_coins", sa.Integer(), nullable=False, server_default="800"))
    op.add_column("game_config", sa.Column("bingo_full_pack_id", sa.Integer(), nullable=True))
    op.add_column("game_config", sa.Column("bingo_pool", sa.JSON(), nullable=False, server_default="[]"))

    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE bingo_goal_definitions SET is_active = false WHERE goal_type = 'trades_completed'"
    ))
    bind.execute(sa.text(
        "DELETE FROM bingo_week_goals WHERE goal_type = 'trades_completed' AND week_id IN "
        "(SELECT id FROM bingo_weeks WHERE reward_resolved = false)"
    ))


def downgrade() -> None:
    op.drop_column("game_config", "bingo_pool")
    op.drop_column("game_config", "bingo_full_pack_id")
    op.drop_column("game_config", "bingo_full_coins")
    op.drop_column("game_config", "bingo_line_coins")
    op.drop_index("ix_bingo_cards_user_id", table_name="bingo_cards")
    op.drop_index("ix_bingo_cards_week_id", table_name="bingo_cards")
    op.drop_table("bingo_cards")
