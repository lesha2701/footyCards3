"""«Менеджер» — «Штаб президента»: club staff hired from the owner's
«Жители города» (`manager_staff`), and the president's office state
(`manager_clubs.office`: the VIP staff names and skins, the assistant's
rules and log, the board of directors, the car and the office worn).

Revision ID: 0292
Revises: 0291
Create Date: 2026-11-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0292"
down_revision: Union[str, None] = "0291"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("manager_clubs", sa.Column("office", sa.JSON(), nullable=True))
    op.create_table(
        "manager_staff",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("resident_id", sa.Integer(), sa.ForeignKey("town_residents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rarity", sa.String(16), nullable=False),
        sa.Column("wage", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("hired_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("club_id", "role", name="uq_manager_staff_role"),
        sa.UniqueConstraint("club_id", "resident_id", name="uq_manager_staff_resident"),
    )
    op.create_index("ix_manager_staff_club", "manager_staff", ["club_id"])


def downgrade() -> None:
    op.drop_index("ix_manager_staff_club", table_name="manager_staff")
    op.drop_table("manager_staff")
    op.drop_column("manager_clubs", "office")
