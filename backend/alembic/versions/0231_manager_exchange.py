"""«Кабинет президента», phase 2: the club exchange (manager_stocks,
manager_shares, manager_trades) and bonds (manager_bonds,
manager_bond_holdings).

Revision ID: 0231
Revises: 0230
Create Date: 2026-11-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0231"
down_revision: Union[str, None] = "0230"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLUB = "manager_clubs.id"


def upgrade() -> None:
    op.create_table(
        "manager_stocks",
        sa.Column("club_id", sa.Integer(), sa.ForeignKey(CLUB, ondelete="CASCADE"), primary_key=True),
        sa.Column("shares_total", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("floated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unsold", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pool", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("base", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("price", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("history", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("raised_season", sa.String(10), nullable=True),
        sa.Column("raised_eur", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("dividends_paid", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "manager_shares",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey(CLUB, ondelete="CASCADE"), nullable=False),
        sa.Column("holder_club_id", sa.Integer(), sa.ForeignKey(CLUB, ondelete="CASCADE"), nullable=False),
        sa.Column("shares", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("dividends", sa.BigInteger(), nullable=False, server_default="0"),
        sa.UniqueConstraint("club_id", "holder_club_id", name="uq_manager_share_holder"),
    )
    op.create_index("ix_manager_shares_club_id", "manager_shares", ["club_id"])
    op.create_index("ix_manager_shares_holder_club_id", "manager_shares", ["holder_club_id"])
    op.create_table(
        "manager_trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey(CLUB, ondelete="CASCADE"), nullable=False),
        sa.Column("holder_club_id", sa.Integer(), sa.ForeignKey(CLUB, ondelete="CASCADE"), nullable=True),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("shares", sa.Integer(), nullable=False),
        sa.Column("price", sa.BigInteger(), nullable=False),
        sa.Column("fee", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_manager_trades_club", "manager_trades", ["club_id", "id"])
    op.create_index("ix_manager_trades_holder_club_id", "manager_trades", ["holder_club_id"])
    op.create_table(
        "manager_bonds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey(CLUB, ondelete="CASCADE"), nullable=False),
        sa.Column("season_key", sa.String(10), nullable=False),
        sa.Column("seasons_total", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("seasons_left", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("rate_bp", sa.Integer(), nullable=False),
        sa.Column("unit_eur", sa.BigInteger(), nullable=False),
        sa.Column("units_total", sa.Integer(), nullable=False),
        sa.Column("units_sold", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="selling"),
        sa.Column("last_season", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_manager_bonds_club_id", "manager_bonds", ["club_id"])
    op.create_table(
        "manager_bond_holdings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bond_id", sa.Integer(), sa.ForeignKey("manager_bonds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("holder_club_id", sa.Integer(), sa.ForeignKey(CLUB, ondelete="CASCADE"), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received", sa.BigInteger(), nullable=False, server_default="0"),
        sa.UniqueConstraint("bond_id", "holder_club_id", name="uq_manager_bond_holder"),
    )
    op.create_index("ix_manager_bond_holdings_bond_id", "manager_bond_holdings", ["bond_id"])
    op.create_index("ix_manager_bond_holdings_holder_club_id", "manager_bond_holdings", ["holder_club_id"])


def downgrade() -> None:
    op.drop_table("manager_bond_holdings")
    op.drop_table("manager_bonds")
    op.drop_table("manager_trades")
    op.drop_table("manager_shares")
    op.drop_table("manager_stocks")
