"""«Мяч и Магия»: magic_runs, users' rating / hero XP / wins / army and the
hourly and daily counters, GameConfig settings (off by default) and the
transaction type.

Revision ID: 0298
Revises: 0297
Create Date: 2026-11-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0298"
down_revision: Union[str, None] = "0297"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONFIG_INT_COLUMNS = (
    ("magic_reward_win", "150"),
    ("magic_reward_loss", "30"),
    ("magic_daily_limit", "5"),
    ("magic_extra_run_coins", "300"),
    ("magic_extra_run_stars", "5"),
    ("magic_extra_runs_daily_limit", "5"),
    ("magic_creature_pack_coins", "1500"),
    ("magic_creature_pack_stars", "25"),
    ("magic_wounded_hours", "24"),
    ("magic_heal_essence_pct", "100"),
    ("magic_heal_stars", "10"),
    ("magic_essence_pack", "300"),
    ("magic_essence_leadership", "450"),
    ("magic_essence_leadership_max", "5"),
    ("magic_essence_mana", "360"),
    ("magic_essence_mana_max", "5"),
    ("magic_essence_per_star", "40"),
    ("magic_essence_per_100_coins", "10"),
    ("magic_progress_xp_pct", "100"),
    ("magic_captain_dup_xp", "150"),
    ("magic_captain_dup_daily", "1"),
    ("magic_progress_scaling_pct", "60"),
    ("magic_challenge_level_cap", "3"),
    ("magic_retry_coins", "250"),
    ("magic_retry_stars", "5"),
    ("magic_retries_daily_limit", "1"),
    ("magic_gold_coins_pct", "10"),
    ("magic_easy_reward_pct", "60"),
    ("magic_hard_reward_pct", "160"),
    ("magic_pack_chance_normal_pct", "5"),
    ("magic_pack_chance_hard_pct", "20"),
    ("magic_rating_win", "30"),
    ("magic_rating_loss", "10"),
    ("magic_days", "7"),
    ("magic_moves_per_day", "9"),
    ("magic_stack_cap", "300"),
)
USER_COLUMNS = (
    ("magic_rating", "0"),
    ("magic_hero_xp", "0"),
    ("magic_wins", "0"),
    ("magic_hourly_attempts", "0"),
    ("magic_rewarded_attempts_today", "0"),
    ("magic_extra_runs_today", "0"),
    ("magic_bonus_runs", "0"),
    ("magic_retries_today", "0"),
    ("magic_retry_credits", "0"),
)
SKIN_SLOTS = ("equipped_magic_hero_id", "equipped_magic_castle_id")
# Hero and castle skins sold in the hub (cosmetics; style_key = what the frontend draws).
SKINS = (
    ("magic_hero", "Золотой капитан", "Рыцарь: позолоченные доспехи и лавровый венок", "magic_hero_gold", 0, 50, 1),
    ("magic_hero", "Теневой маг", "Маг: капюшон, чёрный скакун, фиолетовое сияние", "magic_hero_shadow", 0, 25, 2),
    ("magic_hero", "Ледяной рыцарь", "Рыцарь: хрустальные доспехи и морозный плащ", "magic_hero_frost", 0, 50, 3),
    # Class skins: each dresses only its own class (engine.SKIN_CLASS).
    ("magic_hero", "Архимаг пламени", "Маг: алая мантия, посох с огненным кристаллом", "magic_hero_ember", 0, 40, 4),
    ("magic_hero", "Лесной страж", "Следопыт: плащ из листьев, лук из живого дерева", "magic_hero_grove", 3000, 0, 5),
    ("magic_hero", "Ночной охотник", "Следопыт: чёрный капюшон, серебряный лук, волк рядом", "magic_hero_night", 0, 50, 6),
    ("magic_castle", "Замок-стадион", "Крепость с трибунами и прожекторами", "magic_castle_stadium", 0, 50, 1),
    ("magic_castle", "Ледяной дворец", "Замок из сияющего льда", "magic_castle_ice", 0, 40, 2),
    ("magic_castle", "Вулканическая крепость", "Бастион на лавовой скале", "magic_castle_volcano", 0, 60, 3),
    ("magic_castle", "Замок-кубок", "Крепость в виде золотого кубка над полем", "magic_castle_cup", 3000, 0, 4),
)
USER_NULLABLE = (
    ("magic_army", sa.JSON()),
    ("magic_creatures", sa.JSON()),
    ("magic_hour_started_at", sa.DateTime(timezone=True)),
    ("magic_attempts_reset_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'magic_reward'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'magic_purchase'")

    op.create_table(
        "magic_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("faction", sa.String(16), nullable=False),
        sa.Column("difficulty", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="in_progress"),
        sa.Column("result", sa.String(16), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reward_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("xp_gained", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pack_opening_id", sa.Integer(), nullable=True),
        sa.Column("server_state", sa.JSON(), nullable=True),
        sa.Column("challenge_week", sa.String(10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    for col in ("user_id", "status", "created_at", "challenge_week"):
        op.create_index(f"ix_magic_runs_{col}", "magic_runs", [col])

    for name, default in USER_COLUMNS:
        op.add_column("users", sa.Column(name, sa.Integer(), nullable=False, server_default=default))
    for name, type_ in USER_NULLABLE:
        op.add_column("users", sa.Column(name, type_, nullable=True))
    for name in SKIN_SLOTS:
        op.add_column("users", sa.Column(name, sa.Integer(), sa.ForeignKey("cosmetics.id", ondelete="SET NULL"), nullable=True))
    cosmetics = sa.table(
        "cosmetics", sa.column("kind", sa.String), sa.column("name", sa.String), sa.column("description", sa.String),
        sa.column("style_key", sa.String), sa.column("coins_price", sa.Integer), sa.column("stars_price", sa.Integer),
        sa.column("sort_order", sa.Integer), sa.column("is_exclusive", sa.Boolean),
    )
    op.bulk_insert(cosmetics, [
        {"kind": k, "name": n, "description": d, "style_key": key, "coins_price": c, "stars_price": st, "sort_order": o,
         "is_exclusive": False}
        for k, n, d, key, c, st, o in SKINS
    ])

    op.add_column("game_config", sa.Column("magic_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("game_config", sa.Column("magic_pack_id", sa.Integer(), nullable=True))
    for name, default in CONFIG_INT_COLUMNS:
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=default))


def downgrade() -> None:
    for name, _ in reversed(CONFIG_INT_COLUMNS):
        op.drop_column("game_config", name)
    op.drop_column("game_config", "magic_pack_id")
    op.drop_column("game_config", "magic_enabled")
    for name in reversed(SKIN_SLOTS):
        op.drop_column("users", name)
    op.execute("DELETE FROM cosmetics WHERE kind IN ('magic_hero', 'magic_castle')")
    for name, _ in reversed(USER_NULLABLE):
        op.drop_column("users", name)
    for name, _ in reversed(USER_COLUMNS):
        op.drop_column("users", name)
    for col in ("user_id", "status", "created_at"):
        op.drop_index(f"ix_magic_runs_{col}", table_name="magic_runs")
    op.drop_table("magic_runs")
    # Postgres cannot drop enum values — the transaction type stays.
