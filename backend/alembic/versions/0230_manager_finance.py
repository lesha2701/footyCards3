"""«Менеджер» → «Кабинет президента» (manager_finance): the club money ledger
(the report by seasons), season deals (sponsor, stadium naming rights, tour,
TV rights, deposit, venture fund, farm club), bank loans, supporters won on
tours, and GameConfig.manager_finance (overrides of manager_finance.DEFAULTS).
The ledger starts empty: the report covers the money from this release on.

Revision ID: 0230
Revises: 0229
Create Date: 2026-10-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0230"
down_revision: Union[str, None] = "0229"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_config", sa.Column("manager_finance", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("manager_clubs", sa.Column("fans_bonus", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "manager_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_key", sa.String(10), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("ref", sa.String(64), nullable=True),
        sa.Column("note", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("club_id", "ref", name="uq_manager_ledger_ref"),
    )
    op.create_index("ix_manager_ledger_club_season", "manager_ledger", ["club_id", "season_key"])
    op.create_table(
        "manager_deals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("season_key", sa.String(10), nullable=False),
        sa.Column("seasons", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("option", sa.String(32), nullable=True),
        sa.Column("amount", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("result", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("club_id", "kind", "season_key", name="uq_manager_deal_season"),
    )
    op.create_index("ix_manager_deals_club_id", "manager_deals", ["club_id"])
    op.create_table(
        "manager_loans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("principal", sa.BigInteger(), nullable=False),
        sa.Column("debt", sa.BigInteger(), nullable=False),
        sa.Column("rate_bp", sa.Integer(), nullable=False),
        sa.Column("seasons_total", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("seasons_left", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("last_season", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_manager_loans_club_id", "manager_loans", ["club_id"])
    op.create_index(
        "uq_manager_loan_open", "manager_loans", ["club_id"], unique=True, postgresql_where=sa.text("status <> 'repaid'"),
    )


def downgrade() -> None:
    op.drop_index("uq_manager_loan_open", table_name="manager_loans")
    op.drop_index("ix_manager_loans_club_id", table_name="manager_loans")
    op.drop_table("manager_loans")
    op.drop_index("ix_manager_deals_club_id", table_name="manager_deals")
    op.drop_table("manager_deals")
    op.drop_index("ix_manager_ledger_club_season", table_name="manager_ledger")
    op.drop_table("manager_ledger")
    op.drop_column("manager_clubs", "fans_bonus")
    op.drop_column("game_config", "manager_finance")
