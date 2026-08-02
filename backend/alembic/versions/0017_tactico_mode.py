"""Тактико: 11-card tactical duel mode

Adds the squad (`tactico_squads`/`tactico_squad_cards`) and match
(`tactico_matches`) tables for the new Tactico game mode, a `tactics_rating`
column on `users` for its leaderboard, new `GameConfig` tunables, and the
new `NotificationType`/`TransactionType` enum values used by its
challenge/reward lifecycle.

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

tactico_opponent_type_enum = postgresql.ENUM("bot", "friend", name="tactico_opponent_type_enum", create_type=False)
tactico_match_status_enum = postgresql.ENUM(
    "pending_accept", "in_progress", "finished", "declined", "cancelled", "expired",
    name="tactico_match_status_enum", create_type=False,
)
match_difficulty_enum = postgresql.ENUM("easy", "medium", "hard", name="match_difficulty_enum", create_type=False)
match_result_enum = postgresql.ENUM("win", "draw", "loss", name="match_result_enum", create_type=False)

NEW_ENUMS = [tactico_opponent_type_enum, tactico_match_status_enum]


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in NEW_ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'tactico_challenge_received'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'tactico_challenge_accepted'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'tactico_challenge_declined'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'tactico_challenge_cancelled'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'tactico_challenge_expired'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'tactico_your_turn'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'tactico_match_finished'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'tactico_reward'")

    op.add_column("users", sa.Column("tactics_rating", sa.Integer(), nullable=False, server_default="0"))

    op.add_column(
        "game_config", sa.Column("tactico_challenge_expiry_hours", sa.Integer(), nullable=False, server_default="24")
    )
    op.add_column(
        "game_config", sa.Column("tactico_round_timeout_hours", sa.Integer(), nullable=False, server_default="24")
    )
    op.add_column(
        "game_config", sa.Column("tactico_phase_bonus_pct", sa.Numeric(4, 2), nullable=False, server_default="0.15")
    )
    op.add_column("game_config", sa.Column("tactico_reward_win", sa.Integer(), nullable=False, server_default="40"))
    op.add_column("game_config", sa.Column("tactico_reward_draw", sa.Integer(), nullable=False, server_default="15"))
    op.add_column("game_config", sa.Column("tactico_reward_loss", sa.Integer(), nullable=False, server_default="5"))
    op.add_column(
        "game_config",
        sa.Column("tactico_bot_optimal_pick_chance_easy", sa.Numeric(4, 2), nullable=False, server_default="0.40"),
    )
    op.add_column(
        "game_config",
        sa.Column("tactico_bot_optimal_pick_chance_medium", sa.Numeric(4, 2), nullable=False, server_default="0.65"),
    )
    op.add_column(
        "game_config",
        sa.Column("tactico_bot_optimal_pick_chance_hard", sa.Numeric(4, 2), nullable=False, server_default="0.90"),
    )

    op.create_table(
        "tactico_squads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_tactico_squads_user_id"),
    )
    op.create_index("ix_tactico_squads_user_id", "tactico_squads", ["user_id"])

    op.create_table(
        "tactico_squad_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("squad_id", sa.Integer(), sa.ForeignKey("tactico_squads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("squad_id", "user_card_id", name="uq_tactico_squad_card"),
    )
    op.create_index("ix_tactico_squad_cards_squad_id", "tactico_squad_cards", ["squad_id"])
    op.create_index("ix_tactico_squad_cards_user_card_id", "tactico_squad_cards", ["user_card_id"])

    op.create_table(
        "tactico_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opponent_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("opponent_name", sa.String(128), nullable=False),
        sa.Column("opponent_type", tactico_opponent_type_enum, nullable=False),
        sa.Column("difficulty", match_difficulty_enum, nullable=True),
        sa.Column("status", tactico_match_status_enum, nullable=False, server_default="pending_accept"),
        sa.Column("user_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opponent_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result", match_result_enum, nullable=True),
        sa.Column("reward_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("server_state", postgresql.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tactico_matches_user_id", "tactico_matches", ["user_id"])
    op.create_index("ix_tactico_matches_status", "tactico_matches", ["status"])
    op.create_index("ix_tactico_matches_created_at", "tactico_matches", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_tactico_matches_created_at", table_name="tactico_matches")
    op.drop_index("ix_tactico_matches_status", table_name="tactico_matches")
    op.drop_index("ix_tactico_matches_user_id", table_name="tactico_matches")
    op.drop_table("tactico_matches")

    op.drop_index("ix_tactico_squad_cards_user_card_id", table_name="tactico_squad_cards")
    op.drop_index("ix_tactico_squad_cards_squad_id", table_name="tactico_squad_cards")
    op.drop_table("tactico_squad_cards")

    op.drop_index("ix_tactico_squads_user_id", table_name="tactico_squads")
    op.drop_table("tactico_squads")

    op.drop_column("game_config", "tactico_bot_optimal_pick_chance_hard")
    op.drop_column("game_config", "tactico_bot_optimal_pick_chance_medium")
    op.drop_column("game_config", "tactico_bot_optimal_pick_chance_easy")
    op.drop_column("game_config", "tactico_reward_loss")
    op.drop_column("game_config", "tactico_reward_draw")
    op.drop_column("game_config", "tactico_reward_win")
    op.drop_column("game_config", "tactico_phase_bonus_pct")
    op.drop_column("game_config", "tactico_round_timeout_hours")
    op.drop_column("game_config", "tactico_challenge_expiry_hours")

    op.drop_column("users", "tactics_rating")

    bind = op.get_bind()
    for enum_type in reversed(NEW_ENUMS):
        enum_type.drop(bind, checkfirst=True)
    # notification_type_enum / transaction_type_enum ADD VALUEs above are not reversible.
