"""«Менеджер»: «Филиал академии» — the filial, its alumni and the alumni trades.

Revision ID: 0322
Revises: 0321
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0322"
down_revision: Union[str, None] = "0321"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'manager_filial'")
    op.create_table(
        "manager_filials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("region", sa.String(24), nullable=False),
        sa.Column("country", sa.String(32), nullable=False, server_default=""),
        sa.Column("levels", sa.JSON(), nullable=False),
        sa.Column("last_release_key", sa.String(10), nullable=True),
        sa.Column("pending", sa.JSON(), nullable=True),
        sa.Column("sold_key", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "manager_alumni",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filial_id", sa.Integer(), sa.ForeignKey("manager_filials.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("manager_clubs.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("name", sa.String(48), nullable=False),
        sa.Column("country", sa.String(32), nullable=False),
        sa.Column("position", sa.String(4), nullable=False),
        sa.Column("potential", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("peak", sa.Integer(), nullable=False),
        sa.Column("peak_age", sa.Integer(), nullable=False),
        sa.Column("decline_age", sa.Integer(), nullable=False),
        sa.Column("retire_age", sa.Integer(), nullable=False),
        sa.Column("start_age", sa.Integer(), nullable=False, server_default="17"),
        sa.Column("joined_key", sa.String(10), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="club"),
        sa.Column("price", sa.BigInteger(), nullable=True),
        sa.Column("goals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "manager_alumni_trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alumnus_id", sa.Integer(), sa.ForeignKey("manager_alumni.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("seller_club_id", sa.Integer(), sa.ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("buyer_club_id", sa.Integer(), sa.ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("price", sa.BigInteger(), nullable=False),
        sa.Column("season_key", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("manager_alumni_trades")
    op.drop_table("manager_alumni")
    op.drop_table("manager_filials")
