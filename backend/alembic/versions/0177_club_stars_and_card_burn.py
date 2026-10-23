"""«Звёзды клуба» (a Stars balance patrons top up and budget spenders spend
on the club's Stars goods) and the spare-card burn now giving a club pack.

Revision ID: 0177
Revises: 0176
Create Date: 2026-10-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0177"
down_revision: Union[str, None] = "0176"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clubs", sa.Column("star_balance", sa.Integer(), nullable=False, server_default="0"))
    op.create_check_constraint("ck_clubs_star_balance_non_negative", "clubs", "star_balance >= 0")
    op.create_table(
        "club_star_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("description", sa.String(256), nullable=False, server_default=""),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_club_star_transactions_club_id", "club_star_transactions", ["club_id"])
    op.add_column("game_config", sa.Column("club_card_exchange_pack_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("game_config", "club_card_exchange_pack_id")
    op.drop_index("ix_club_star_transactions_club_id", table_name="club_star_transactions")
    op.drop_table("club_star_transactions")
    op.drop_constraint("ck_clubs_star_balance_non_negative", "clubs", type_="check")
    op.drop_column("clubs", "star_balance")
