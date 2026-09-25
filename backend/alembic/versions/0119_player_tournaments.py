"""Player tournaments: 16 players, 30 rounds, personal squads (5 templates),
configurable rewards and a per-user tournament rating.

Revision ID: 0119
Revises: 0118
Create Date: 2026-09-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0119"
down_revision: Union[str, None] = "0118"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PLACE_REWARDS = "[3000, 2000, 1500, 1000, 750, 500, 400, 300, 250, 200, 150, 100, 75, 50, 25, 0]"
_RATING_BY_PLACE = "[5, 4, 3, 2, 1, 0, 0, 0, 0, 0, 0, -1, -2, -3, -4, -5]"


def _status_enum():
    return postgresql.ENUM("active", "completed", name="tournament_status_enum", create_type=False)


def _queue_status_enum():
    return postgresql.ENUM("open", "formed", name="tournament_queue_status_enum", create_type=False)


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'player_tournament_match_reward'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'player_tournament_place_reward'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'player_tournament_match'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'player_tournament_results_ready'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'player_tournament_reminder'")

    op.add_column("users", sa.Column("tournament_rating", sa.Integer(), nullable=False, server_default="0"))

    op.add_column("game_config", sa.Column("ptour_match_reward_win", sa.Integer(), nullable=False, server_default="100"))
    op.add_column("game_config", sa.Column("ptour_match_reward_draw", sa.Integer(), nullable=False, server_default="40"))
    op.add_column("game_config", sa.Column("ptour_match_reward_loss", sa.Integer(), nullable=False, server_default="15"))
    op.add_column("game_config", sa.Column("ptour_place_rewards", sa.JSON(), nullable=False, server_default=sa.text(f"'{_PLACE_REWARDS}'::json")))
    op.add_column("game_config", sa.Column("ptour_rating_by_place", sa.JSON(), nullable=False, server_default=sa.text(f"'{_RATING_BY_PLACE}'::json")))

    op.create_table(
        "personal_squads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_index", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("formation", sa.String(16), nullable=False, server_default="4-3-3"),
        sa.Column("mentality", sa.String(16), nullable=False, server_default="BALANCED"),
        sa.Column("playstyle", sa.String(16), nullable=False, server_default="CENTRAL_PLAY"),
        sa.Column("user_coach_card_id", sa.Integer(), sa.ForeignKey("user_coach_cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "template_index", name="uq_personal_squad_user_template"),
    )
    op.create_index("ix_personal_squads_user_id", "personal_squads", ["user_id"])
    op.create_index(
        "uq_personal_squad_one_active_per_user", "personal_squads", ["user_id"], unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_table(
        "personal_squad_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("squad_id", sa.Integer(), sa.ForeignKey("personal_squads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot_code", sa.String(16), nullable=False),
        sa.UniqueConstraint("squad_id", "user_card_id", name="uq_personal_squad_card_once"),
        sa.UniqueConstraint("squad_id", "slot_code", name="uq_personal_squad_slot_once"),
    )
    op.create_index("ix_personal_squad_cards_squad_id", "personal_squad_cards", ["squad_id"])
    op.create_index("ix_personal_squad_cards_user_card_id", "personal_squad_cards", ["user_card_id"])

    op.create_table(
        "player_tournaments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", _status_enum(), nullable=False, server_default="active"),
        sa.Column("rounds_simulated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("rounds_simulated >= 0 AND rounds_simulated <= 30", name="ck_player_tournaments_rounds_range"),
    )
    op.create_table(
        "player_tournament_participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("player_tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("tournament_id", "user_id", name="uq_player_tournament_participant_once"),
    )
    op.create_index("ix_player_tournament_participants_tournament_id", "player_tournament_participants", ["tournament_id"])
    op.create_index("ix_player_tournament_participants_user_id", "player_tournament_participants", ["user_id"])
    op.create_table(
        "player_tournament_standings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("player_tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("goals_for", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("goals_against", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("tournament_id", "user_id", name="uq_player_tournament_standing_once"),
    )
    op.create_index("ix_player_tournament_standings_tournament_id", "player_tournament_standings", ["tournament_id"])
    op.create_index("ix_player_tournament_standings_user_id", "player_tournament_standings", ["user_id"])
    op.create_table(
        "player_tournament_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("player_tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("user_a_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_b_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score_a", sa.Integer(), nullable=False),
        sa.Column("score_b", sa.Integer(), nullable=False),
        sa.Column("event_log", sa.JSON(), nullable=False),
        sa.Column("simulated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("round_number >= 1 AND round_number <= 30", name="ck_player_tournament_matches_round_range"),
    )
    op.create_index("ix_player_tournament_matches_tournament_id", "player_tournament_matches", ["tournament_id"])
    op.create_index("ix_player_tournament_matches_user_a_id", "player_tournament_matches", ["user_a_id"])
    op.create_index("ix_player_tournament_matches_user_b_id", "player_tournament_matches", ["user_b_id"])
    op.create_table(
        "player_tournament_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("player_tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("final_rank", sa.Integer(), nullable=False),
        sa.Column("coins_awarded", sa.Integer(), nullable=False),
        sa.Column("rating_delta", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tournament_id", "user_id", name="uq_player_tournament_result_once"),
    )
    op.create_index("ix_player_tournament_results_tournament_id", "player_tournament_results", ["tournament_id"])
    op.create_index("ix_player_tournament_results_user_id", "player_tournament_results", ["user_id"])

    op.create_table(
        "player_tournament_queues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", _queue_status_enum(), nullable=False, server_default="open"),
    )
    op.create_table(
        "player_tournament_queue_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("current_queue_id", sa.Integer(), sa.ForeignKey("player_tournament_queues.id"), nullable=False),
    )
    op.create_table(
        "player_tournament_queue_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("queue_id", sa.Integer(), sa.ForeignKey("player_tournament_queues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("queue_id", "user_id", name="uq_player_tournament_queue_entry_once"),
    )
    op.create_index("ix_player_tournament_queue_entries_queue_id", "player_tournament_queue_entries", ["queue_id"])
    op.create_index("ix_player_tournament_queue_entries_user_id", "player_tournament_queue_entries", ["user_id"])

    # Seed the singleton queue state (real Postgres only; tests lazily create it,
    # see player_tournament_queue_service._lock_queue_state).
    op.execute("INSERT INTO player_tournament_queues (status) VALUES ('open')")
    op.execute(
        "INSERT INTO player_tournament_queue_state (id, current_queue_id) "
        "SELECT 1, id FROM player_tournament_queues ORDER BY id LIMIT 1"
    )


def downgrade() -> None:
    op.drop_table("player_tournament_queue_entries")
    op.drop_table("player_tournament_queue_state")
    op.drop_table("player_tournament_queues")
    op.drop_table("player_tournament_results")
    op.drop_table("player_tournament_matches")
    op.drop_table("player_tournament_standings")
    op.drop_table("player_tournament_participants")
    op.drop_table("player_tournaments")
    op.drop_table("personal_squad_cards")
    op.drop_table("personal_squads")
    for column in ("ptour_rating_by_place", "ptour_place_rewards", "ptour_match_reward_loss", "ptour_match_reward_draw", "ptour_match_reward_win"):
        op.drop_column("game_config", column)
    op.drop_column("users", "tournament_rating")
    # Postgres cannot drop enum values; the added transaction/notification
    # enum members are left in place (same note as 0109).
