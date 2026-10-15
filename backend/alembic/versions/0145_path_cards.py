"""«Начало пути»: path cards (diamond players that grow by playing) — talent
catalog, stages and their gate tasks, per-copy progress, experience journal,
bought attempts, GameConfig tuning, the «Начало пути» pack and collection.

Only adds tables/columns (existing cards get path_level = path_stage =
path_rating_bonus = 0 and no card_paths row, i.e. nothing changes for them)
plus seed rows inserted with ON CONFLICT DO NOTHING.

Revision ID: 0145
Revises: 0144
Create Date: 2026-10-15

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0145"
down_revision: Union[str, None] = "0144"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TALENTS = [
    ("big_matches", {"1": {"bonus": 3, "threshold_pct": 5}, "2": {"bonus": 5, "threshold_pct": 5}}),
    ("second_wind", {"1": {"bonus": 3, "from_minute": 60, "fatigue_cut_pct": 25},
                     "2": {"bonus": 5, "from_minute": 60, "fatigue_cut_pct": 40}}),
    ("universal", {"1": {"bonus": 0}, "2": {"bonus": 2}}),
    ("own_guy", {"1": {"link_floor": 1, "extra_points": 0}, "2": {"link_floor": 2, "extra_points": 1}}),
    ("academy", {"1": {"coach_bonus": 2, "stadium_bonus": 2}, "2": {"coach_bonus": 4, "stadium_bonus": 4}}),
    ("hunger", {"1": {"per_match": 1, "max": 3, "keep_on_miss_pct": 0}, "2": {"per_match": 1, "max": 6, "keep_on_miss_pct": 50}}),
    ("fighter", {"1": {"bonus": 3}, "2": {"bonus": 5}}),
    ("composure", {"1": {"bonus": 4}, "2": {"bonus": 7}}),
    ("hold_lead", {"1": {"bonus": 3, "from_minute": 75}, "2": {"bonus": 5, "from_minute": 75}}),
    ("captain", {"1": {"aura": 1, "aura_cap": 4}, "2": {"aura": 2, "aura_cap": 6}}),
]
# (index, name, upper rating bound, talent level unlocked)
_STAGES = [(0, "Новичок", 65, 0), (1, "Перспективный", 74, 0), (2, "Основной", 84, 1), (3, "Звезда", 89, 1), (4, "Легенда", 96, 2)]
_ATTACKING = ["ST", "LW", "RW", "CAM", "LM", "RM", "CM"]
# (stage, metric, target, positions)
_TASKS = [
    (0, "matches", 30, None), (0, "wins", 12, None),
    (1, "matches", 80, None), (1, "wins", 30, None), (1, "official_matches", 10, None),
    (2, "matches", 150, None), (2, "wins", 55, None), (2, "goal_contributions", 15, _ATTACKING),
    (2, "official_matches", 25, None),
    (3, "matches", 110, None), (3, "wins", 45, None), (3, "official_matches", 20, None),
]


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'path_attempt_purchase'")

    op.create_table(
        "path_talents",
        sa.Column("code", sa.String(32), primary_key=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("level_values", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "path_stages",
        sa.Column("stage_index", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("max_rating", sa.Integer(), nullable=False),
        sa.Column("talent_level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "path_stage_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stage_index", sa.Integer(), sa.ForeignKey("path_stages.stage_index", ondelete="CASCADE"), nullable=False),
        sa.Column("metric", sa.String(32), nullable=False),
        sa.Column("target", sa.Integer(), nullable=False),
        sa.Column("positions", sa.JSON(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_path_stage_tasks_stage_index", "path_stage_tasks", ["stage_index"])

    op.add_column("players", sa.Column(
        "path_talent_code", sa.String(32), sa.ForeignKey("path_talents.code", ondelete="RESTRICT"), nullable=True,
    ))
    op.create_index("ix_players_path_talent_code", "players", ["path_talent_code"])

    for name in ("path_level", "path_stage", "path_rating_bonus"):
        op.add_column("user_cards", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))
    op.create_check_constraint(
        "ck_user_cards_path_non_negative", "user_cards", "path_level >= 0 AND path_stage >= 0 AND path_rating_bonus >= 0",
    )

    op.create_table(
        "card_paths",
        sa.Column("user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("xp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage_counters", sa.JSON(), nullable=False),
        sa.Column("totals", sa.JSON(), nullable=False),
        sa.Column("day", sa.Date(), nullable=True),
        sa.Column("arena_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("career_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ptour_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coin_buys", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stars_buys", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bought_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hunger_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "path_xp_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("xp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_card_id", "source_type", "source_id", name="uq_path_xp_events_card_source"),
    )
    op.create_index("ix_path_xp_events_user_card_id", "path_xp_events", ["user_card_id"])
    op.create_index("ix_path_xp_events_user_id", "path_xp_events", ["user_id"])
    op.create_table(
        "path_attempt_purchases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("purchase_day", sa.Date(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_path_attempt_purchases_user_key"),
    )
    op.create_index("ix_path_attempt_purchases_user_id", "path_attempt_purchases", ["user_id"])
    op.create_index("ix_path_attempt_purchases_user_card_id", "path_attempt_purchases", ["user_card_id"])

    op.add_column("packs", sa.Column("player_pool", sa.String(16), nullable=False, server_default="default"))
    op.add_column("stars_invoices", sa.Column(
        "path_user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True,
    ))

    gc = [
        ("path_enabled", sa.Boolean(), sa.true()),
        ("path_title", sa.String(64), "Начало пути"),
        ("path_xp_base", sa.Integer(), "75"), ("path_xp_step", sa.Integer(), "10"),
        ("path_start_rating", sa.Integer(), "60"), ("path_rating_per_level", sa.Integer(), "1"),
        ("path_xp_match", sa.Integer(), "10"), ("path_xp_win", sa.Integer(), "10"), ("path_xp_draw", sa.Integer(), "3"),
        ("path_xp_goal", sa.Integer(), "5"), ("path_xp_assist", sa.Integer(), "3"),
        ("path_daily_free_arena", sa.Integer(), "10"), ("path_daily_career", sa.Integer(), "2"),
        ("path_daily_ptour", sa.Integer(), "3"),
        ("path_coin_attempt_prices", sa.JSON(), "[300, 400, 500, 600, 700]"),
        ("path_stars_attempt_prices", sa.JSON(), "[3, 4, 5, 6, 7]"),
        ("path_talent_cap", sa.Integer(), "8"),
        ("match_max_path_cards", sa.Integer(), "1"), ("tactico_max_path_cards", sa.Integer(), "1"),
        ("stratego_max_path_cards", sa.Integer(), "1"),
    ]
    for name, type_, default in gc:
        op.add_column("game_config", sa.Column(name, type_, nullable=False, server_default=default))

    bind = op.get_bind()
    for order, (code, values) in enumerate(_TALENTS):
        bind.execute(
            sa.text(
                "INSERT INTO path_talents (code, is_enabled, level_values, sort_order) "
                "VALUES (:code, true, :values, :order) ON CONFLICT (code) DO NOTHING"
            ),
            {"code": code, "values": json.dumps(values), "order": order},
        )
    for index, name, max_rating, talent_level in _STAGES:
        bind.execute(
            sa.text(
                "INSERT INTO path_stages (stage_index, name, max_rating, talent_level) "
                "VALUES (:i, :n, :m, :t) ON CONFLICT (stage_index) DO NOTHING"
            ),
            {"i": index, "n": name, "m": max_rating, "t": talent_level},
        )
    if not bind.execute(sa.text("SELECT 1 FROM path_stage_tasks LIMIT 1")).first():
        for order, (stage, metric, target, positions) in enumerate(_TASKS):
            bind.execute(
                sa.text(
                    "INSERT INTO path_stage_tasks (stage_index, metric, target, positions, sort_order, is_active) "
                    "VALUES (:s, :m, :t, :p, :o, true)"
                ),
                {"s": stage, "m": metric, "t": target, "p": json.dumps(positions) if positions else None, "o": order},
            )

    # The collection (completion reward) and the pack — inactive until the
    # admin has added «Начало пути» players (a path pack with no path players
    # would have nothing to drop in its diamond slots).
    bind.execute(sa.text(
        "INSERT INTO card_collections (name, description, is_active, sort_order, reward_coins, created_at, updated_at) "
        "VALUES ('Начало пути', 'Молодые игроки, которые растут, пока играют', true, 0, 5000, now(), now()) "
        "ON CONFLICT (name) DO NOTHING"
    ))
    exists = bind.execute(sa.text("SELECT id FROM packs WHERE slug = 'path-start'")).first()
    if not exists:
        pack_id = bind.execute(sa.text(
            "INSERT INTO packs (slug, name, description, price, card_count, guaranteed_min_rarity, is_active, sort_order, "
            "coach_drop_chance, stadium_drop_chance, skill_token_drop_chance, player_pool, created_at, updated_at) "
            "VALUES ('path-start', 'Начало пути', '5 карточек: шанс на молодого игрока «Начала пути» в каждом слоте', "
            "3000, 5, 'epic', false, 50, 0, 0, 0, 'path', now(), now()) RETURNING id"
        )).scalar_one()
        for rarity, probability in (("common", 0.20), ("rare", 0.35), ("epic", 0.30), ("legendary", 0.10), ("diamond", 0.05)):
            bind.execute(
                sa.text("INSERT INTO pack_rarity_probabilities (pack_id, rarity, probability) VALUES (:p, :r, :v)"),
                {"p": pack_id, "r": rarity, "v": probability},
            )


def downgrade() -> None:
    for name in (
        "stratego_max_path_cards", "tactico_max_path_cards", "match_max_path_cards", "path_talent_cap",
        "path_stars_attempt_prices", "path_coin_attempt_prices", "path_daily_ptour", "path_daily_career",
        "path_daily_free_arena", "path_xp_assist", "path_xp_goal", "path_xp_draw", "path_xp_win", "path_xp_match",
        "path_rating_per_level", "path_start_rating", "path_xp_step", "path_xp_base", "path_title", "path_enabled",
    ):
        op.drop_column("game_config", name)
    op.drop_column("stars_invoices", "path_user_card_id")
    op.drop_column("packs", "player_pool")
    op.drop_table("path_attempt_purchases")
    op.drop_table("path_xp_events")
    op.drop_table("card_paths")
    op.drop_constraint("ck_user_cards_path_non_negative", "user_cards", type_="check")
    for name in ("path_rating_bonus", "path_stage", "path_level"):
        op.drop_column("user_cards", name)
    op.drop_index("ix_players_path_talent_code", table_name="players")
    op.drop_column("players", "path_talent_code")
    op.drop_table("path_stage_tasks")
    op.drop_table("path_stages")
    op.drop_table("path_talents")
    # The seeded pack/collection rows stay (they are ordinary data by now);
    # transaction_type_enum keeps 'path_attempt_purchase' (Postgres cannot
    # drop an enum value).
