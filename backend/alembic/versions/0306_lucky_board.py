"""«Табло удачи»: a three-window football scoreboard mini-game — daily free
spins, then fixed-price spins for Telegram Stars (shop product «lucky_board»);
lucky_board_spins, users.lucky_board_*, game_config.lucky_board_*.

Revision ID: 0306
Revises: 0305
Create Date: 2026-11-17
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Same as app.models.game_config.LUCKY_BOARD_DEFAULT_OUTCOMES on the day of
# this migration (copied, so later edits there don't rewrite history).
def _side(coins=0, tokens=0, shards=0, cosmetic=False):
    return {"coins": coins, "tokens": tokens, "shards": shards, "cosmetic": cosmetic}


LUCKY_BOARD_DEFAULT_OUTCOMES = [
    {"code": "cup", "label": "Кубок", "free_weight": 10, "paid_weight": 10,
     "free": _side(coins=1000, tokens=1), "paid": _side(tokens=3)},
    {"code": "ball", "label": "Хет-трик", "free_weight": 30, "paid_weight": 30,
     "free": _side(tokens=1), "paid": _side(tokens=2)},
    {"code": "glove", "label": "Сухарь", "free_weight": 80, "paid_weight": 80,
     "free": _side(coins=300), "paid": _side(tokens=1)},
    {"code": "boot", "label": "Бутса", "free_weight": 80, "paid_weight": 30,
     "free": _side(coins=150), "paid": _side(shards=3, cosmetic=True)},
    {"code": "pair", "label": "Дубль", "free_weight": 300, "paid_weight": 350,
     "free": _side(shards=1), "paid": _side(shards=2)},
    {"code": "miss", "label": "Мимо ворот", "free_weight": 500, "paid_weight": 500,
     "free": _side(coins=25), "paid": _side(shards=1)},
]

# (name, icon, image, sort) / (name, description, style_key, sort)
BADGE = ("Кубок табло", "🏆", "badges/lucky_board.webp", 960)
FRAME = ("Табло удачи", "Приз «Табло удачи» — горит огнями стадиона", "lucky_board", 961)

revision: str = "0306"
down_revision: Union[str, None] = "0305"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONFIG_INT_COLUMNS = (
    ("lucky_board_free_per_day", "3"),
    ("lucky_board_stars_cost", "1"),
    ("lucky_board_paid_daily_limit", "20"),
    ("lucky_board_hourly_limit", "10"),
    ("lucky_board_shards_per_token", "5"),
)
USER_INT_COLUMNS = (
    "lucky_board_free_used_today",
    "lucky_board_paid_bought_today",
    "lucky_board_paid_spins",
    "lucky_board_shards",
    "lucky_board_hourly_attempts",
)


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'lucky_board_reward'")

    op.create_table(
        "lucky_board_spins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("reels", sa.JSON(), nullable=False),
        sa.Column("prize", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_lucky_board_spins_user_key"),
    )
    op.create_index("ix_lucky_board_spins_user_id", "lucky_board_spins", ["user_id"])
    op.create_index("ix_lucky_board_spins_created_at", "lucky_board_spins", ["created_at"])

    for name in USER_INT_COLUMNS:
        op.add_column("users", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("lucky_board_day_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("lucky_board_hour_started_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("game_config", sa.Column("lucky_board_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    for name, default in CONFIG_INT_COLUMNS:
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=default))
    op.add_column("game_config", sa.Column(
        "lucky_board_outcomes", sa.JSON(), nullable=False,
        server_default=sa.text("'" + json.dumps(LUCKY_BOARD_DEFAULT_OUTCOMES, ensure_ascii=False).replace("'", "''") + "'"),
    ))
    op.add_column("game_config", sa.Column("lucky_board_cosmetic_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("game_config", sa.Column("lucky_board_badge_id", sa.Integer(), nullable=True))

    # The paid «Бутса» prizes: the board's badge and profile frame (exclusive,
    # never sold), linked to the config. Reused if a row already exists.
    conn = op.get_bind()
    badge_id = conn.execute(sa.text("SELECT id FROM badges WHERE name = :n"), {"n": BADGE[0]}).scalar()
    if badge_id is None:
        badge_id = conn.execute(sa.text(
            "INSERT INTO badges (name, icon, image_path, is_active, sort_order, created_at, updated_at) "
            "VALUES (:n, :icon, :img, true, :sort, now(), now()) RETURNING id"
        ), {"n": BADGE[0], "icon": BADGE[1], "img": BADGE[2], "sort": BADGE[3]}).scalar_one()
    frame_id = conn.execute(sa.text(
        "SELECT id FROM cosmetics WHERE kind = 'profile_frame' AND style_key = :s"
    ), {"s": FRAME[2]}).scalar()
    if frame_id is None:
        frame_id = conn.execute(sa.text(
            "INSERT INTO cosmetics (kind, name, description, style_key, coins_price, stars_price, is_exclusive, "
            "is_active, sort_order, status, win_bonus_coins, created_at, updated_at) "
            "VALUES ('profile_frame', :name, :description, :style, 0, 0, true, true, :sort, 0, 0, now(), now()) "
            "RETURNING id"
        ), {"name": FRAME[0], "description": FRAME[1], "style": FRAME[2], "sort": FRAME[3]}).scalar_one()
    conn.execute(sa.text(
        "UPDATE game_config SET lucky_board_badge_id = :b, lucky_board_cosmetic_ids = CAST(:c AS JSON) WHERE id = 1"
    ), {"b": badge_id, "c": json.dumps([frame_id])})


def downgrade() -> None:
    for name in ("lucky_board_badge_id", "lucky_board_cosmetic_ids", "lucky_board_outcomes"):
        op.drop_column("game_config", name)
    for name, _ in reversed(CONFIG_INT_COLUMNS):
        op.drop_column("game_config", name)
    op.drop_column("game_config", "lucky_board_enabled")
    op.drop_column("users", "lucky_board_hour_started_at")
    op.drop_column("users", "lucky_board_day_reset_at")
    for name in reversed(USER_INT_COLUMNS):
        op.drop_column("users", name)
    op.drop_index("ix_lucky_board_spins_created_at", table_name="lucky_board_spins")
    op.drop_index("ix_lucky_board_spins_user_id", table_name="lucky_board_spins")
    op.drop_table("lucky_board_spins")
    # PostgreSQL can't drop an enum value; 'lucky_board_reward' stays harmless.
