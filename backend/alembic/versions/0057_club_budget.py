"""Club budget: Club.budget, ClubBudgetTransaction, club_daily_reward_coins

Revision ID: 0057
Revises: 0056
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0057"
down_revision: Union[str, None] = "0056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clubs", sa.Column("budget", sa.Integer(), nullable=False, server_default="0"))
    op.create_check_constraint("ck_clubs_budget_non_negative", "clubs", "budget >= 0")

    op.add_column("game_config", sa.Column("club_daily_reward_coins", sa.Integer(), nullable=False, server_default="200"))

    op.create_table(
        "club_budget_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_before", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column(
            "type", sa.Enum("daily_claim", "pack_purchase", name="club_budget_transaction_type_enum"), nullable=False
        ),
        sa.Column("description", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("related_object_type", sa.String(length=64), nullable=True),
        sa.Column("related_object_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_club_budget_transactions_club_id", "club_budget_transactions", ["club_id"])
    op.create_index("ix_club_budget_transactions_created_at", "club_budget_transactions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_club_budget_transactions_created_at", table_name="club_budget_transactions")
    op.drop_index("ix_club_budget_transactions_club_id", table_name="club_budget_transactions")
    op.drop_table("club_budget_transactions")
    op.drop_column("game_config", "club_daily_reward_coins")
    op.drop_constraint("ck_clubs_budget_non_negative", "clubs", type_="check")
    op.drop_column("clubs", "budget")
    bind = op.get_bind()
    sa.Enum(name="club_budget_transaction_type_enum").drop(bind, checkfirst=True)
