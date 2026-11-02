"""«Менеджер»: the transfer log of a club (manager_moves) — who came, who
left, the fee and the reason, shown in the «Трансферы» tab.

Revision ID: 0229
Revises: 0228
Create Date: 2026-11-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0229"
down_revision: Union[str, None] = "0228"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "manager_moves",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_key", sa.String(10), nullable=False),
        sa.Column("direction", sa.String(4), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("who", sa.String(64), nullable=False),
        sa.Column("position", sa.String(8), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("fee", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("other_club", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_manager_moves_club", "manager_moves", ["club_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_manager_moves_club", table_name="manager_moves")
    op.drop_table("manager_moves")
