"""Add club_join_request_received/accepted/rejected, club_role_changed,
club_kicked, club_captain_transferred to notification_type_enum

Revision ID: 0073
Revises: 0072
Create Date: 2026-08-28
"""
from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'club_join_request_received'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'club_join_request_accepted'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'club_join_request_rejected'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'club_role_changed'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'club_kicked'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'club_captain_transferred'")


def downgrade() -> None:
    # Postgres has no clean "ALTER TYPE ... DROP VALUE" — same accepted
    # asymmetric-downgrade limitation as every prior enum-value addition
    # in this codebase (see 0002_tasks_and_minigames.py's identical note).
    pass
