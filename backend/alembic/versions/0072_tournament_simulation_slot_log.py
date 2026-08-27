"""TournamentSimulationSlotLog — backend-side scheduler dedup

Revision ID: 0072
Revises: 0071
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tournament_simulation_slot_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("slot_key", sa.String(length=32), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("kind", "slot_key", name="uq_tournament_simulation_slot_log_once"),
    )


def downgrade() -> None:
    op.drop_table("tournament_simulation_slot_log")
