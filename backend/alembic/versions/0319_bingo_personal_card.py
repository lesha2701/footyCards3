"""«Бинго недели»: the player's own 3×3 card (bingo_cards): 500 coins a
closed row, +500 and the legendary coin pack for all three; the server's
common goal (2000 coins) now pays only those with a closed row. The «обмены» common goal, out of reach since the trade
limits, is switched off — for the running week too.

Revision ID: 0319
Revises: 0318
Create Date: 2026-11-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0319"
down_revision: Union[str, None] = "0318"
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

    op.add_column("game_config", sa.Column("bingo_line_coins", sa.Integer(), nullable=False, server_default="500"))
    op.add_column("game_config", sa.Column("bingo_full_coins", sa.Integer(), nullable=False, server_default="500"))
    op.add_column("game_config", sa.Column("bingo_full_pack_id", sa.Integer(), nullable=True))
    op.add_column("game_config", sa.Column("bingo_pool", sa.JSON(), nullable=False, server_default="[]"))

    bind = op.get_bind()
    # The legendary coin pack — the one «Подарок за возвращение» resolved (0265).
    bind.execute(sa.text(
        "UPDATE game_config SET bingo_reward_coins = 2000, bingo_full_pack_id = "
        "(SELECT p.id FROM packs p WHERE p.slug = game_config.comeback_gift_pack_slug ORDER BY p.id LIMIT 1)"
    ))
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
