"""«Менеджер»: «Кубок менеджеров» (manager_cups) and friendlies (manager_friendlies).

Revision ID: 0238
Revises: 0237
Create Date: 2026-11-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0238"
down_revision: Union[str, None] = "0237"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "manager_cups",
        sa.Column("season_key", sa.String(10), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "manager_friendlies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("home_club_id", sa.Integer(), sa.ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("away_club_id", sa.Integer(), sa.ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("home_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("away_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_manager_friendlies_home_club_id", "manager_friendlies", ["home_club_id"])
    op.create_index("ix_manager_friendlies_away_club_id", "manager_friendlies", ["away_club_id"])


def downgrade() -> None:
    op.drop_index("ix_manager_friendlies_away_club_id", table_name="manager_friendlies")
    op.drop_index("ix_manager_friendlies_home_club_id", table_name="manager_friendlies")
    op.drop_table("manager_friendlies")
    op.drop_table("manager_cups")
