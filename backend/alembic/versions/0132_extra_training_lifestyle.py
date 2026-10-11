""""Мой игрок": extra trainings for coins/Stars, «Имущество» (lifestyle
items: cars, real estate, stocks...) managed from the admin panel, and the
skill level bought with skill tokens.

Revision ID: 0132
Revises: 0131
Create Date: 2026-10-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0132"
down_revision: Union[str, None] = "0131"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'my_player_extra_training'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'lifestyle_purchase'")
    op.add_column("my_players", sa.Column("skill_level", sa.Integer(), nullable=True))
    # Dev databases that ran an early draft of 0131 have this column; the
    # skill now follows card-skill rules with no player-level gate.
    op.execute("ALTER TABLE game_config DROP COLUMN IF EXISTS my_player_skill_levels")
    op.add_column("my_players", sa.Column("extra_training_credits", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("my_players", sa.Column("extra_trainings_bought", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("my_players", sa.Column("extra_training_day", sa.Date(), nullable=True))
    gc = "game_config"
    op.add_column(gc, sa.Column("my_player_extra_trainings_max", sa.Integer(), nullable=False, server_default="3"))
    op.add_column(gc, sa.Column("my_player_extra_training_coins", sa.Integer(), nullable=False, server_default="300"))
    op.add_column(gc, sa.Column("my_player_extra_training_stars", sa.Integer(), nullable=False, server_default="15"))
    op.add_column("stars_invoices", sa.Column("my_player_purchase", sa.String(64), nullable=True))

    op.create_table(
        "lifestyle_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=False, server_default=""),
        sa.Column("category", sa.String(16), nullable=False, server_default="other"),
        sa.Column("emoji", sa.String(16), nullable=False, server_default="⭐"),
        sa.Column("image_path", sa.String(255), nullable=True),
        sa.Column("coins_price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stars_price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prestige", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("max_supply", sa.Integer(), nullable=True),
        sa.Column("sold_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_lifestyle_items_category", "lifestyle_items", ["category"])
    op.create_table(
        "user_lifestyle_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("lifestyle_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(16), nullable=False, server_default="coins"),
        sa.Column("serial_number", sa.Integer(), nullable=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "item_id", name="uq_user_lifestyle_item"),
    )
    op.create_index("ix_user_lifestyle_items_user_id", "user_lifestyle_items", ["user_id"])

    # A starter catalog the admin can edit or switch off.
    items = sa.table(
        "lifestyle_items",
        sa.column("name", sa.String), sa.column("description", sa.String), sa.column("category", sa.String),
        sa.column("emoji", sa.String), sa.column("coins_price", sa.Integer), sa.column("stars_price", sa.Integer),
        sa.column("prestige", sa.Integer), sa.column("max_supply", sa.Integer), sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(items, [
        {"name": "Хэтчбек", "description": "Первая машина молодого игрока", "category": "car", "emoji": "🚗",
         "coins_price": 1500, "stars_price": 0, "prestige": 10, "max_supply": None, "sort_order": 1},
        {"name": "Спорткар", "description": "Красный, быстрый, на парковке у базы", "category": "car", "emoji": "🏎️",
         "coins_price": 8000, "stars_price": 100, "prestige": 50, "max_supply": None, "sort_order": 2},
        {"name": "Квартира у стадиона", "description": "Пешком до тренировки", "category": "estate", "emoji": "🏢",
         "coins_price": 5000, "stars_price": 0, "prestige": 30, "max_supply": None, "sort_order": 3},
        {"name": "Вилла у моря", "description": "Для отпуска между сезонами", "category": "estate", "emoji": "🏝️",
         "coins_price": 0, "stars_price": 250, "prestige": 120, "max_supply": 100, "sort_order": 4},
        {"name": "Пакет акций клуба", "description": "Совладелец любимой команды", "category": "stocks", "emoji": "📈",
         "coins_price": 3000, "stars_price": 0, "prestige": 20, "max_supply": None, "sort_order": 5},
        {"name": "Личный самолёт", "description": "Лимитированная серия", "category": "other", "emoji": "🛩️",
         "coins_price": 0, "stars_price": 500, "prestige": 250, "max_supply": 25, "sort_order": 6},
    ])


def downgrade() -> None:
    op.drop_index("ix_user_lifestyle_items_user_id", table_name="user_lifestyle_items")
    op.drop_table("user_lifestyle_items")
    op.drop_index("ix_lifestyle_items_category", table_name="lifestyle_items")
    op.drop_table("lifestyle_items")
    op.drop_column("stars_invoices", "my_player_purchase")
    gc = "game_config"
    for column in ("my_player_extra_training_stars", "my_player_extra_training_coins", "my_player_extra_trainings_max"):
        op.drop_column(gc, column)
    for column in ("extra_training_day", "extra_trainings_bought", "extra_training_credits", "skill_level"):
        op.drop_column("my_players", column)
    # The enum values stay: Postgres can't drop enum values.
