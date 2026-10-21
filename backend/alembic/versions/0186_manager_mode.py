"""«Менеджер»: own clubs (the owner's «Мой игрок» and an «Академия» card
always start, other users' «Мои игроки» on contracts for seasons, catalog
footballers bought or loaned), money in club euros, a 10-division pyramid
with weekly seasons (preseason window + 15 rounds), the transfer value
history, the club style shop, fans' merchandise and «Менеджер Pro».

Revision ID: 0186
Revises: 0185
Create Date: 2026-10-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0186"
down_revision: Union[str, None] = "0185"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INT_FIELDS = (
    ("manager_found_cost", "3000"),
    ("manager_min_level", "3"),
    ("manager_max_live", "5"),
    ("manager_squad_max", "22"),
    ("manager_league_size", "16"),
    ("manager_divisions", "10"),
    ("manager_promote", "2"),
    ("manager_preseason_hours", "72"),
    ("manager_style_edge_pct", "4"),
    ("manager_formation_effect_pct", "100"),
    ("manager_wage_pct", "10"),
    ("manager_loan_fee_pct", "20"),
    ("manager_sell_back_pct", "50"),
    ("manager_live_wage_max", "3000"),
    ("manager_wage_eur_per_coin", "1000"),
    ("manager_form_bonus_pct", "5"),
    ("manager_form_bonus_cap", "50"),
    ("manager_income_win", "300000"),
    ("manager_income_draw", "150000"),
    ("manager_income_loss", "60000"),
    ("manager_ticket_eur_per_level", "20000"),
    ("manager_sponsor_eur_per_level", "100000"),
    ("manager_merch_eur_per_level", "60000"),
    ("manager_budget_per_base_level", "20000"),
    ("manager_base_bonus_cap_pct", "60"),
    ("manager_promotion_bonus_pct", "50"),
    ("manager_parachute_pct", "33"),
    ("manager_match_xp", "30"),
    ("manager_freshness_cost", "0"),
    ("manager_merch_cap_eur", "15000000"),
    ("manager_pro_stars", "299"),
    ("manager_pro_days", "30"),
)
JSON_FIELDS = (
    ("manager_value_ratings", "[45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95]"),
    ("manager_value_eur", "[50000, 80000, 150000, 400000, 1000000, 3500000, 12000000, 35000000, 80000000, 160000000, 220000000]"),
    ("manager_division_budget", "[120000000, 70000000, 40000000, 22000000, 12000000, 7000000, 4500000, 3000000, 2500000, 2000000]"),
    ("manager_division_income_pct", "[300, 250, 200, 170, 140, 120, 110, 100, 100, 100]"),
    ("manager_division_wage_pct", "[180, 160, 140, 125, 115, 105, 100, 100, 100, 100]"),
    ("manager_division_rating", "[80, 77, 74, 71, 68, 65, 63, 61, 59, 57]"),
    ("manager_place_rewards", "[1000, 600, 300]"),
    ("manager_place_budget", "[3000000, 2000000, 1000000]"),
    ("manager_slots", "[\"13:00\", \"17:00\", \"21:00\"]"),
    ("manager_cosmetics", "[{\"code\": \"shape_shield\", \"kind\": \"shape\", \"name\": \"Щит\", \"value\": \"shield\", \"coins\": 0, \"stars\": 0}, {\"code\": \"shape_circle\", \"kind\": \"shape\", \"name\": \"Круг\", \"value\": \"circle\", \"coins\": 0, \"stars\": 0}, {\"code\": \"shape_hexagon\", \"kind\": \"shape\", \"name\": \"Шестигранник\", \"value\": \"hexagon\", \"coins\": 5000, \"stars\": 49}, {\"code\": \"shape_crest\", \"kind\": \"shape\", \"name\": \"Герб\", \"value\": \"crest\", \"coins\": 6000, \"stars\": 59}, {\"code\": \"shape_crown\", \"kind\": \"shape\", \"name\": \"Корона\", \"value\": \"crown\", \"coins\": 8000, \"stars\": 79}, {\"code\": \"shape_diamond\", \"kind\": \"shape\", \"name\": \"Ромб\", \"value\": \"diamond\", \"coins\": 0, \"stars\": 99}, {\"code\": \"shape_star\", \"kind\": \"shape\", \"name\": \"Звезда\", \"value\": \"star\", \"coins\": 0, \"stars\": 129}, {\"code\": \"shape_castle\", \"kind\": \"shape\", \"name\": \"Замок\", \"value\": \"castle\", \"coins\": 0, \"stars\": 149}, {\"code\": \"symbol_ball\", \"kind\": \"symbol\", \"name\": \"Мяч\", \"value\": \"⚽\", \"coins\": 0, \"stars\": 0}, {\"code\": \"symbol_star\", \"kind\": \"symbol\", \"name\": \"Звезда\", \"value\": \"⭐\", \"coins\": 0, \"stars\": 0}, {\"code\": \"symbol_lion\", \"kind\": \"symbol\", \"name\": \"Лев\", \"value\": \"🦁\", \"coins\": 4000, \"stars\": 39}, {\"code\": \"symbol_eagle\", \"kind\": \"symbol\", \"name\": \"Орёл\", \"value\": \"🦅\", \"coins\": 4000, \"stars\": 39}, {\"code\": \"symbol_wolf\", \"kind\": \"symbol\", \"name\": \"Волк\", \"value\": \"🐺\", \"coins\": 4000, \"stars\": 39}, {\"code\": \"symbol_bear\", \"kind\": \"symbol\", \"name\": \"Медведь\", \"value\": \"🐻\", \"coins\": 4000, \"stars\": 39}, {\"code\": \"symbol_tiger\", \"kind\": \"symbol\", \"name\": \"Тигр\", \"value\": \"🐯\", \"coins\": 5000, \"stars\": 49}, {\"code\": \"symbol_bull\", \"kind\": \"symbol\", \"name\": \"Бык\", \"value\": \"🐂\", \"coins\": 5000, \"stars\": 49}, {\"code\": \"symbol_shark\", \"kind\": \"symbol\", \"name\": \"Акула\", \"value\": \"🦈\", \"coins\": 5000, \"stars\": 49}, {\"code\": \"symbol_horse\", \"kind\": \"symbol\", \"name\": \"Конь\", \"value\": \"🐎\", \"coins\": 5000, \"stars\": 49}, {\"code\": \"symbol_anchor\", \"kind\": \"symbol\", \"name\": \"Якорь\", \"value\": \"⚓\", \"coins\": 6000, \"stars\": 59}, {\"code\": \"symbol_bolt\", \"kind\": \"symbol\", \"name\": \"Молния\", \"value\": \"⚡\", \"coins\": 0, \"stars\": 69}, {\"code\": \"symbol_fire\", \"kind\": \"symbol\", \"name\": \"Пламя\", \"value\": \"🔥\", \"coins\": 0, \"stars\": 79}, {\"code\": \"symbol_rocket\", \"kind\": \"symbol\", \"name\": \"Ракета\", \"value\": \"🚀\", \"coins\": 0, \"stars\": 89}, {\"code\": \"symbol_dragon\", \"kind\": \"symbol\", \"name\": \"Дракон\", \"value\": \"🐉\", \"coins\": 0, \"stars\": 129}, {\"code\": \"symbol_crown\", \"kind\": \"symbol\", \"name\": \"Корона\", \"value\": \"👑\", \"coins\": 0, \"stars\": 149}, {\"code\": \"kit_plain\", \"kind\": \"kit\", \"name\": \"Однотонная\", \"value\": \"plain\", \"coins\": 0, \"stars\": 0}, {\"code\": \"kit_stripes\", \"kind\": \"kit\", \"name\": \"Полосы\", \"value\": \"stripes\", \"coins\": 3000, \"stars\": 29}, {\"code\": \"kit_hoops\", \"kind\": \"kit\", \"name\": \"Обручи\", \"value\": \"hoops\", \"coins\": 3000, \"stars\": 29}, {\"code\": \"kit_pinstripes\", \"kind\": \"kit\", \"name\": \"Тонкая полоса\", \"value\": \"pinstripes\", \"coins\": 4000, \"stars\": 39}, {\"code\": \"kit_halves\", \"kind\": \"kit\", \"name\": \"Половинки\", \"value\": \"halves\", \"coins\": 5000, \"stars\": 49}, {\"code\": \"kit_quarters\", \"kind\": \"kit\", \"name\": \"Четверти\", \"value\": \"quarters\", \"coins\": 6000, \"stars\": 59}, {\"code\": \"kit_sash\", \"kind\": \"kit\", \"name\": \"Диагональ\", \"value\": \"sash\", \"coins\": 0, \"stars\": 69}, {\"code\": \"kit_chevron\", \"kind\": \"kit\", \"name\": \"Шеврон\", \"value\": \"chevron\", \"coins\": 0, \"stars\": 79}, {\"code\": \"kit_checks\", \"kind\": \"kit\", \"name\": \"Клетка\", \"value\": \"checks\", \"coins\": 0, \"stars\": 89}, {\"code\": \"kit_gradient\", \"kind\": \"kit\", \"name\": \"Градиент\", \"value\": \"gradient\", \"coins\": 0, \"stars\": 99}, {\"code\": \"frame_classic\", \"kind\": \"frame\", \"name\": \"Классика\", \"value\": \"classic\", \"coins\": 0, \"stars\": 0}, {\"code\": \"frame_retro\", \"kind\": \"frame\", \"name\": \"Ретро\", \"value\": \"retro\", \"coins\": 8000, \"stars\": 69}, {\"code\": \"frame_ruby\", \"kind\": \"frame\", \"name\": \"Рубин\", \"value\": \"ruby\", \"coins\": 0, \"stars\": 89}, {\"code\": \"frame_ice\", \"kind\": \"frame\", \"name\": \"Лёд\", \"value\": \"ice\", \"coins\": 0, \"stars\": 89}, {\"code\": \"frame_neon\", \"kind\": \"frame\", \"name\": \"Неон\", \"value\": \"neon\", \"coins\": 0, \"stars\": 99}, {\"code\": \"frame_fire\", \"kind\": \"frame\", \"name\": \"Огонь\", \"value\": \"fire\", \"coins\": 0, \"stars\": 119}, {\"code\": \"frame_galaxy\", \"kind\": \"frame\", \"name\": \"Галактика\", \"value\": \"galaxy\", \"coins\": 0, \"stars\": 149}, {\"code\": \"frame_gold\", \"kind\": \"frame\", \"name\": \"Золото\", \"value\": \"gold\", \"coins\": 0, \"stars\": 199}, {\"code\": \"theme_night\", \"kind\": \"theme\", \"name\": \"Ночь\", \"value\": \"night\", \"coins\": 0, \"stars\": 0}, {\"code\": \"theme_ocean\", \"kind\": \"theme\", \"name\": \"Океан\", \"value\": \"ocean\", \"coins\": 6000, \"stars\": 49}, {\"code\": \"theme_forest\", \"kind\": \"theme\", \"name\": \"Лес\", \"value\": \"forest\", \"coins\": 6000, \"stars\": 49}, {\"code\": \"theme_sunset\", \"kind\": \"theme\", \"name\": \"Закат\", \"value\": \"sunset\", \"coins\": 0, \"stars\": 79}, {\"code\": \"theme_royal\", \"kind\": \"theme\", \"name\": \"Королевский\", \"value\": \"royal\", \"coins\": 0, \"stars\": 99}, {\"code\": \"theme_gold\", \"kind\": \"theme\", \"name\": \"Золотой\", \"value\": \"gold\", \"coins\": 0, \"stars\": 149}, {\"code\": \"stadium_name\", \"kind\": \"stadium_name\", \"name\": \"Имя стадиона\", \"value\": \"\", \"coins\": 0, \"stars\": 199}]"),
    ("manager_merch", "[{\"code\": \"scarf\", \"name\": \"Шарф\", \"emoji\": \"🧣\", \"coins\": 500, \"eur\": 300000}, {\"code\": \"cap\", \"name\": \"Кепка\", \"emoji\": \"🧢\", \"coins\": 800, \"eur\": 500000}, {\"code\": \"shirt\", \"name\": \"Футболка\", \"emoji\": \"👕\", \"coins\": 1500, \"eur\": 900000}, {\"code\": \"ball\", \"name\": \"Мяч с автографами\", \"emoji\": \"⚽\", \"coins\": 2500, \"eur\": 1500000}, {\"code\": \"flag\", \"name\": \"Флаг на трибуну\", \"emoji\": \"🚩\", \"coins\": 4000, \"eur\": 2500000}, {\"code\": \"season_ticket\", \"name\": \"Абонемент\", \"emoji\": \"🎟️\", \"coins\": 8000, \"eur\": 5000000}]"),
)
TRANSACTION_TYPES = ("manager_club_found", "manager_salary", "manager_reward", "manager_cosmetic", "manager_merch")


def _json(value: str):
    return sa.text("'" + value.replace("'", "''") + "'::json")


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'manager_event'")
    for value in TRANSACTION_TYPES:
        op.execute(f"ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS '{value}'")
    op.create_table(
        "manager_seasons",
        sa.Column("key", sa.String(10), primary_key=True),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "manager_leagues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("season_key", sa.String(10), nullable=False),
        sa.Column("division", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("rounds_played", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", sa.JSON(), nullable=False, server_default=_json("{}")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_manager_leagues_season_key", "manager_leagues", ["season_key"])
    op.create_index("ix_manager_leagues_status", "manager_leagues", ["status"])
    op.create_table(
        "manager_clubs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column("formation", sa.String(8), nullable=False, server_default="4-3-3"),
        sa.Column("style", sa.String(16), nullable=False, server_default="possession"),
        sa.Column("budget", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("division", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("academy_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("budget_season", sa.String(10), nullable=True),
        sa.Column("league_id", sa.Integer(), sa.ForeignKey("manager_leagues.id", ondelete="SET NULL"), nullable=True),
        sa.Column("seasons_played", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("titles", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("best_division", sa.Integer(), nullable=True),
        sa.Column("look", sa.JSON(), nullable=False, server_default=_json("{}")),
        sa.Column("stadium_name", sa.String(32), nullable=True),
        sa.Column("pro_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("merch_season", sa.String(10), nullable=True),
        sa.Column("merch_eur", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_manager_clubs_division", "manager_clubs", ["division"])
    op.create_table(
        "manager_contracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="sign"),
        sa.Column("status", sa.String(16), nullable=False, server_default="offered"),
        sa.Column("from_contract_id", sa.Integer(), sa.ForeignKey("manager_contracts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fee", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("wage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("seasons_total", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("seasons_left", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("club_agreed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("player_agreed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("matches_played", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("goals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assists", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("earned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_manager_contracts_club_id", "manager_contracts", ["club_id"])
    op.create_index("ix_manager_contracts_user_status", "manager_contracts", ["user_id", "status"])
    op.create_table(
        "manager_npc",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False, server_default="buy"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("fee", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("wage", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("seasons_left", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("auto", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("goals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_manager_npc_club_id", "manager_npc", ["club_id"])
    # A footballer plays for one manager club at a time.
    op.create_index(
        "uq_manager_npc_active_player", "manager_npc", ["player_id"], unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "manager_value_history",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("season_key", sa.String(10), primary_key=True),
        sa.Column("value", sa.BigInteger(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
    )
    op.create_table(
        "manager_cosmetics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("club_id", "code", name="uq_manager_cosmetic"),
    )
    op.create_index("ix_manager_cosmetics_club_id", "manager_cosmetics", ["club_id"])
    op.create_table(
        "manager_merch",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("eur", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "club_id", "code", name="uq_manager_merch"),
    )
    op.create_index("ix_manager_merch_user_id", "manager_merch", ["user_id"])
    op.create_index("ix_manager_merch_club_id", "manager_merch", ["club_id"])
    op.add_column("my_players", sa.Column("market_open", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("game_config", sa.Column("manager_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    for column, default in INT_FIELDS:
        op.add_column("game_config", sa.Column(column, sa.Integer(), nullable=False, server_default=default))
    for column, default in JSON_FIELDS:
        # A plain string literal: sa.text() would read "13:00" as a bind parameter.
        op.add_column("game_config", sa.Column(column, sa.JSON(), nullable=False, server_default=default))


def downgrade() -> None:
    for column, _ in (*JSON_FIELDS, *INT_FIELDS):
        op.drop_column("game_config", column)
    op.drop_column("game_config", "manager_enabled")
    op.drop_column("my_players", "market_open")
    op.drop_index("ix_manager_merch_club_id", table_name="manager_merch")
    op.drop_index("ix_manager_merch_user_id", table_name="manager_merch")
    op.drop_table("manager_merch")
    op.drop_index("ix_manager_cosmetics_club_id", table_name="manager_cosmetics")
    op.drop_table("manager_cosmetics")
    op.drop_table("manager_value_history")
    op.drop_index("uq_manager_npc_active_player", table_name="manager_npc")
    op.drop_index("ix_manager_npc_club_id", table_name="manager_npc")
    op.drop_table("manager_npc")
    op.drop_index("ix_manager_contracts_user_status", table_name="manager_contracts")
    op.drop_index("ix_manager_contracts_club_id", table_name="manager_contracts")
    op.drop_table("manager_contracts")
    op.drop_index("ix_manager_clubs_division", table_name="manager_clubs")
    op.drop_table("manager_clubs")
    op.drop_index("ix_manager_leagues_status", table_name="manager_leagues")
    op.drop_index("ix_manager_leagues_season_key", table_name="manager_leagues")
    op.drop_table("manager_leagues")
    op.drop_table("manager_seasons")
    # Enum values stay: Postgres cannot drop a value from an enum type.
