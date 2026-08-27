"""Club tournament columns: cups/stars/cooldown, GameConfig tournament fields, tournament_reward enum value

Revision ID: 0064
Revises: 0063
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clubs", sa.Column("cups_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("clubs", sa.Column("stars_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("clubs", sa.Column("last_tournament_applied_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("game_config", sa.Column("club_tournament_cooldown_hours", sa.Integer(), nullable=False, server_default="2"))
    op.add_column("game_config", sa.Column("club_form_window_matches", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("game_config", sa.Column("club_form_bonus_per_result", sa.Numeric(4, 2), nullable=False, server_default="0.02"))
    op.add_column("game_config", sa.Column("club_tournament_budget_place_1", sa.Integer(), nullable=False, server_default="1000"))
    op.add_column("game_config", sa.Column("club_tournament_budget_place_2", sa.Integer(), nullable=False, server_default="750"))
    op.add_column("game_config", sa.Column("club_tournament_budget_place_3", sa.Integer(), nullable=False, server_default="550"))
    op.add_column("game_config", sa.Column("club_tournament_budget_place_4", sa.Integer(), nullable=False, server_default="400"))
    op.add_column("game_config", sa.Column("club_tournament_budget_place_5", sa.Integer(), nullable=False, server_default="300"))
    op.add_column("game_config", sa.Column("club_tournament_budget_place_6", sa.Integer(), nullable=False, server_default="200"))
    op.add_column("game_config", sa.Column("club_tournament_budget_place_7", sa.Integer(), nullable=False, server_default="120"))
    op.add_column("game_config", sa.Column("club_tournament_budget_place_8", sa.Integer(), nullable=False, server_default="60"))

    op.execute("ALTER TYPE club_budget_transaction_type_enum ADD VALUE IF NOT EXISTS 'tournament_reward'")


def downgrade() -> None:
    # Postgres has no clean "ALTER TYPE ... DROP VALUE" — same accepted
    # asymmetric-downgrade limitation as every prior enum-value addition in
    # this codebase (see 0002_tasks_and_minigames.py's identical note).
    op.drop_column("game_config", "club_tournament_budget_place_8")
    op.drop_column("game_config", "club_tournament_budget_place_7")
    op.drop_column("game_config", "club_tournament_budget_place_6")
    op.drop_column("game_config", "club_tournament_budget_place_5")
    op.drop_column("game_config", "club_tournament_budget_place_4")
    op.drop_column("game_config", "club_tournament_budget_place_3")
    op.drop_column("game_config", "club_tournament_budget_place_2")
    op.drop_column("game_config", "club_tournament_budget_place_1")
    op.drop_column("game_config", "club_form_bonus_per_result")
    op.drop_column("game_config", "club_form_window_matches")
    op.drop_column("game_config", "club_tournament_cooldown_hours")

    op.drop_column("clubs", "last_tournament_applied_at")
    op.drop_column("clubs", "stars_count")
    op.drop_column("clubs", "cups_count")
