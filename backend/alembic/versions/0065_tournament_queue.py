"""TournamentQueueState/TournamentQueue/TournamentQueueEntry

Revision ID: 0065
Revises: 0064
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tournament_queues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "status", sa.Enum("open", "formed", name="tournament_queue_status_enum"),
            nullable=False, server_default="open",
        ),
    )
    op.create_table(
        "tournament_queue_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("current_queue_id", sa.Integer(), sa.ForeignKey("tournament_queues.id"), nullable=False),
    )
    op.create_table(
        "tournament_queue_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("queue_id", sa.Integer(), sa.ForeignKey("tournament_queues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tournament_queue_entries_queue_id", "tournament_queue_entries", ["queue_id"])
    op.create_index("ix_tournament_queue_entries_club_id", "tournament_queue_entries", ["club_id"])

    # Seed row 1 of the singleton immediately — the app code always expects
    # it to exist (get-or-create is Task 9's job for the *queue*, not this
    # one-time bootstrap row).
    op.execute("INSERT INTO tournament_queues (status) VALUES ('open')")
    op.execute("INSERT INTO tournament_queue_state (id, current_queue_id) VALUES (1, (SELECT id FROM tournament_queues ORDER BY id DESC LIMIT 1))")


def downgrade() -> None:
    op.drop_index("ix_tournament_queue_entries_club_id", table_name="tournament_queue_entries")
    op.drop_index("ix_tournament_queue_entries_queue_id", table_name="tournament_queue_entries")
    op.drop_table("tournament_queue_entries")
    op.drop_table("tournament_queue_state")
    op.drop_table("tournament_queues")
    bind = op.get_bind()
    sa.Enum(name="tournament_queue_status_enum").drop(bind, checkfirst=True)
