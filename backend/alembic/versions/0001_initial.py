"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

rarity_enum = postgresql.ENUM("common", "rare", "epic", "legendary", name="rarity_enum", create_type=False)
position_enum = postgresql.ENUM(
    "GK", "LB", "CB", "RB", "CDM", "CM", "CAM", "LM", "RM", "LW", "RW", "ST",
    name="position_enum", create_type=False,
)
card_source_enum = postgresql.ENUM(
    "pack", "daily_reward", "trade", "admin_grant", "achievement", "game_reward", "seed",
    name="card_source_enum", create_type=False,
)
transaction_type_enum = postgresql.ENUM(
    "starting_balance", "daily_reward", "pack_purchase", "card_sale", "game_reward", "match_reward",
    "achievement_reward", "trade_coins_sent", "trade_coins_received", "admin_adjustment",
    name="transaction_type_enum", create_type=False,
)
trade_status_enum = postgresql.ENUM(
    "pending", "accepted", "rejected", "cancelled", "expired", name="trade_status_enum", create_type=False
)
trade_card_side_enum = postgresql.ENUM("offered", "requested", name="trade_card_side_enum", create_type=False)
game_type_enum = postgresql.ENUM("memory_sequence", "card_arena", name="game_type_enum", create_type=False)
game_session_status_enum = postgresql.ENUM(
    "in_progress", "won", "lost", "rewarded", "expired", name="game_session_status_enum", create_type=False
)
match_difficulty_enum = postgresql.ENUM("easy", "medium", "hard", name="match_difficulty_enum", create_type=False)
match_result_enum = postgresql.ENUM("win", "draw", "loss", name="match_result_enum", create_type=False)
notification_type_enum = postgresql.ENUM(
    "trade_offer_received", "trade_offer_accepted", "trade_offer_rejected", "trade_offer_cancelled",
    "trade_offer_expired", "daily_reward_available", "special_pack", "admin_message",
    name="notification_type_enum", create_type=False,
)

ALL_ENUMS = [
    rarity_enum, position_enum, card_source_enum, transaction_type_enum, trade_status_enum,
    trade_card_side_enum, game_type_enum, game_session_status_enum, match_difficulty_enum,
    match_result_enum, notification_type_enum,
]


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in ALL_ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("first_name", sa.String(128), nullable=True),
        sa.Column("last_name", sa.String(128), nullable=True),
        sa.Column("avatar_url", sa.String(512), nullable=True),
        sa.Column("balance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_banned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("game_rewards_blocked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("experience", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received_starting_bonus", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("match_energy", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("match_energy_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("matches_won", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matches_drawn", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matches_lost", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("arena_rating", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("memory_best_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("memory_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("memory_attempts_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("telegram_id", name="uq_users_telegram_id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("first_name", sa.String(64), nullable=False),
        sa.Column("last_name", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("rarity", rarity_enum, nullable=False),
        sa.Column("country", sa.String(64), nullable=False),
        sa.Column("club", sa.String(64), nullable=False),
        sa.Column("position", position_enum, nullable=False),
        sa.Column("image_path", sa.String(255), nullable=True),
        sa.Column("quick_sell_price", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rating >= 1 AND rating <= 99", name="ck_players_rating_range"),
    )
    op.create_index("ix_players_display_name", "players", ["display_name"])
    op.create_index("ix_players_rarity", "players", ["rarity"])
    op.create_index("ix_players_country", "players", ["country"])
    op.create_index("ix_players_club", "players", ["club"])
    op.create_index("ix_players_position", "players", ["position"])

    op.create_table(
        "user_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("serial_number", sa.BigInteger(), nullable=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", card_source_enum, nullable=False),
        sa.Column("source_ref_id", sa.Integer(), nullable=True),
        sa.Column("is_locked_by_admin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_locked_in_trade", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_in_lineup", sa.Boolean(), nullable=False, server_default="false"),
        sa.UniqueConstraint("serial_number", name="uq_user_cards_serial"),
    )
    op.create_index("ix_user_cards_serial_number", "user_cards", ["serial_number"])
    op.create_index("ix_user_cards_owner_id", "user_cards", ["owner_id"])
    op.create_index("ix_user_cards_player_id", "user_cards", ["player_id"])

    op.create_table(
        "packs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(512), nullable=False, server_default=""),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("image_path", sa.String(255), nullable=True),
        sa.Column("card_count", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("guaranteed_min_rarity", rarity_enum, nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("purchase_limit_per_user", sa.Integer(), nullable=True),
        sa.Column("available_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slug", name="uq_packs_slug"),
    )

    op.create_table(
        "pack_rarity_probabilities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pack_id", sa.Integer(), sa.ForeignKey("packs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rarity", rarity_enum, nullable=False),
        sa.Column("probability", sa.Numeric(6, 4), nullable=False),
        sa.UniqueConstraint("pack_id", "rarity", name="uq_pack_rarity"),
    )
    op.create_index("ix_pack_rarity_probabilities_pack_id", "pack_rarity_probabilities", ["pack_id"])

    op.create_table(
        "pack_openings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pack_id", sa.Integer(), sa.ForeignKey("packs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("price_paid", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_pack_opening_idem"),
    )
    op.create_index("ix_pack_openings_user_id", "pack_openings", ["user_id"])
    op.create_index("ix_pack_openings_pack_id", "pack_openings", ["pack_id"])
    op.create_index("ix_pack_openings_idempotency_key", "pack_openings", ["idempotency_key"])

    op.create_table(
        "pack_opening_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("opening_id", sa.Integer(), sa.ForeignKey("pack_openings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_new_player", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_pack_opening_cards_opening_id", "pack_opening_cards", ["opening_id"])
    op.create_index("ix_pack_opening_cards_user_card_id", "pack_opening_cards", ["user_card_id"])

    op.create_table(
        "coin_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_before", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("type", transaction_type_enum, nullable=False),
        sa.Column("description", sa.String(255), nullable=False, server_default=""),
        sa.Column("related_object_type", sa.String(64), nullable=True),
        sa.Column("related_object_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("balance_after >= 0", name="ck_coin_tx_balance_non_negative"),
    )
    op.create_index("ix_coin_transactions_user_id", "coin_transactions", ["user_id"])
    op.create_index("ix_coin_transactions_created_at", "coin_transactions", ["created_at"])

    op.create_table(
        "daily_rewards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reward_date", sa.Date(), nullable=False),
        sa.Column("streak_day", sa.Integer(), nullable=False),
        sa.Column("coins_awarded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("free_pack_id", sa.Integer(), sa.ForeignKey("packs.id"), nullable=True),
        sa.Column("random_card_id", sa.Integer(), sa.ForeignKey("user_cards.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "reward_date", name="uq_daily_reward_user_date"),
    )
    op.create_index("ix_daily_rewards_user_id", "daily_rewards", ["user_id"])

    op.create_table(
        "game_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("game_type", game_type_enum, nullable=False),
        sa.Column("status", game_session_status_enum, nullable=False, server_default="in_progress"),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reward_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_rewarded", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("server_state", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_game_sessions_user_id", "game_sessions", ["user_id"])

    op.create_table(
        "memory_game_rounds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.String(256), nullable=False),
        sa.Column("was_correct", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_memory_game_rounds_session_id", "memory_game_rounds", ["session_id"])

    op.create_table(
        "lineups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False, server_default="Основной состав"),
        sa.Column("formation", sa.String(16), nullable=False, server_default="4-3-3"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_lineups_user_id", "lineups", ["user_id"])

    op.create_table(
        "lineup_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lineup_id", sa.Integer(), sa.ForeignKey("lineups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot_code", sa.String(16), nullable=False),
        sa.UniqueConstraint("lineup_id", "user_card_id", name="uq_lineup_card_once"),
        sa.UniqueConstraint("lineup_id", "slot_code", name="uq_lineup_slot_once"),
    )
    op.create_index("ix_lineup_cards_lineup_id", "lineup_cards", ["lineup_id"])
    op.create_index("ix_lineup_cards_user_card_id", "lineup_cards", ["user_card_id"])

    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opponent_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("opponent_name", sa.String(128), nullable=False),
        sa.Column("difficulty", match_difficulty_enum, nullable=False),
        sa.Column("user_team_strength", sa.Integer(), nullable=False),
        sa.Column("opponent_team_strength", sa.Integer(), nullable=False),
        sa.Column("user_score", sa.Integer(), nullable=False),
        sa.Column("opponent_score", sa.Integer(), nullable=False),
        sa.Column("result", match_result_enum, nullable=False),
        sa.Column("reward_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lineup_id", sa.Integer(), sa.ForeignKey("lineups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_matches_user_id", "matches", ["user_id"])
    op.create_index("ix_matches_created_at", "matches", ["created_at"])

    op.create_table(
        "match_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("minute", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("team", sa.String(16), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("payload", postgresql.JSON(), nullable=True),
    )
    op.create_index("ix_match_events_match_id", "match_events", ["match_id"])

    op.create_table(
        "trade_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("receiver_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", trade_status_enum, nullable=False, server_default="pending"),
        sa.Column("sender_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("receiver_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.String(255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trade_offers_sender_id", "trade_offers", ["sender_id"])
    op.create_index("ix_trade_offers_receiver_id", "trade_offers", ["receiver_id"])
    op.create_index("ix_trade_offers_status", "trade_offers", ["status"])

    op.create_table(
        "trade_offer_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trade_offer_id", sa.Integer(), sa.ForeignKey("trade_offers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("side", trade_card_side_enum, nullable=False),
    )
    op.create_index("ix_trade_offer_cards_trade_offer_id", "trade_offer_cards", ["trade_offer_id"])
    op.create_index("ix_trade_offer_cards_user_card_id", "trade_offer_cards", ["user_card_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", notification_type_enum, nullable=False),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("body", sa.String(512), nullable=False),
        sa.Column("related_object_type", sa.String(64), nullable=True),
        sa.Column("related_object_id", sa.Integer(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("telegram_sent", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])

    op.create_table(
        "admin_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("admin_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("old_value", postgresql.JSON(), nullable=True),
        sa.Column("new_value", postgresql.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("extra", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_actions_admin_id", "admin_actions", ["admin_id"])
    op.create_index("ix_admin_actions_created_at", "admin_actions", ["created_at"])

    op.create_table(
        "achievements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(512), nullable=False, server_default=""),
        sa.Column("reward_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("target_value", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_achievements_code"),
    )

    op.create_table(
        "user_achievements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("achievement_id", sa.Integer(), sa.ForeignKey("achievements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reward_claimed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),
    )
    op.create_index("ix_user_achievements_user_id", "user_achievements", ["user_id"])
    op.create_index("ix_user_achievements_achievement_id", "user_achievements", ["achievement_id"])

    op.create_table(
        "game_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("memory_daily_reward_limit", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("memory_reward_cap", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("suspicious_memory_score_threshold", sa.Integer(), nullable=False, server_default="400"),
        sa.Column("match_daily_energy", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("match_reward_win", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("match_reward_draw", sa.Integer(), nullable=False, server_default="40"),
        sa.Column("match_reward_loss", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("difficulty_easy_multiplier", sa.Numeric(4, 2), nullable=False, server_default="0.85"),
        sa.Column("difficulty_medium_multiplier", sa.Numeric(4, 2), nullable=False, server_default="1.0"),
        sa.Column("difficulty_hard_multiplier", sa.Numeric(4, 2), nullable=False, server_default="1.2"),
        sa.Column("suspicious_score_margin", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        "INSERT INTO game_config (id, created_at, updated_at) VALUES (1, now(), now())"
    )


def downgrade() -> None:
    op.drop_table("game_config")
    op.drop_table("user_achievements")
    op.drop_table("achievements")
    op.drop_table("admin_actions")
    op.drop_table("notifications")
    op.drop_table("trade_offer_cards")
    op.drop_table("trade_offers")
    op.drop_table("match_events")
    op.drop_table("matches")
    op.drop_table("lineup_cards")
    op.drop_table("lineups")
    op.drop_table("memory_game_rounds")
    op.drop_table("game_sessions")
    op.drop_table("daily_rewards")
    op.drop_table("coin_transactions")
    op.drop_table("pack_opening_cards")
    op.drop_table("pack_openings")
    op.drop_table("pack_rarity_probabilities")
    op.drop_table("packs")
    op.drop_table("user_cards")
    op.drop_table("players")
    op.drop_table("users")

    bind = op.get_bind()
    for enum_type in reversed(ALL_ENUMS):
        enum_type.drop(bind, checkfirst=True)
