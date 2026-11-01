"""«Менеджер»: «Установка на матч» and the club's form from events
(manager_clubs.match_plan / buffs), «События клуба» (manager_events).

Revision ID: 0235
Revises: 0234
Create Date: 2026-11-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0235"
down_revision: Union[str, None] = "0234"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("manager_clubs", sa.Column("match_plan", sa.JSON(), nullable=True))
    op.add_column("manager_clubs", sa.Column("buffs", sa.JSON(), nullable=True))
    op.create_table(
        "manager_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_key", sa.String(10), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="offered"),
        sa.Column("choice", sa.String(32), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("club_id", "season_key", "slot", name="uq_manager_event_slot"),
    )
    op.create_index("ix_manager_events_club_id", "manager_events", ["club_id"])


def downgrade() -> None:
    op.drop_index("ix_manager_events_club_id", table_name="manager_events")
    op.drop_table("manager_events")
    op.drop_column("manager_clubs", "buffs")
    op.drop_column("manager_clubs", "match_plan")
