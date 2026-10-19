"""«Экипировка»: catalog of things (collections + items), the inventory of
owned copies, what each card wears summed on user_cards, GameConfig switch
and ceilings, transaction type. Seeds two collections and a few single
things (all editable in the admin panel).

Revision ID: 0182
Revises: 0181
Create Date: 2026-10-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0182"
down_revision: Union[str, None] = "0181"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (name, description, set_size, set_bonus_rating, sort)
COLLECTIONS = [
    ("Ретро-70", "Классика тотального футбола: кожаные бутсы, шерстяная форма, высокие гетры.", 3, 1, 1),
    ("Неон", "Ночной матч под прожекторами: светящиеся бутсы, гетры и браслет.", 3, 1, 2),
]
# (collection index or None, name, description, icon, slot, rarity, effect, value, coins, stars, sort)
ITEMS = [
    (0, "Бутсы «Ретро-70»", "Кожаные бутсы с длинными шипами.", "👞", "boots", "rare", "shot_pp", 3, 300, 0, 1),
    (0, "Форма «Ретро-70»", "Шерстяная футболка с воротником-поло.", "👕", "kit", "rare", "rating", 1, 400, 0, 2),
    (0, "Гетры «Ретро-70»", "Высокие гетры в полоску.", "🧦", "socks", "rare", "dribble_pp", 2, 300, 0, 3),
    (1, "Бутсы «Неон»", "Светятся в темноте — удар точнее.", "👟", "boots", "epic", "shot_pp", 5, 900, 40, 4),
    (1, "Гетры «Неон»", "Лёгкие компрессионные гетры.", "🧦", "socks", "epic", "dribble_pp", 4, 900, 40, 5),
    (1, "Браслет «Неон»", "Фитнес-браслет: держит игрока в тонусе.", "⌚", "accessory", "epic", "rating", 1, 1200, 50, 6),
    (None, "Перчатки «Стена»", "Вратарские перчатки с цепким латексом.", "🧤", "gloves", "rare", "rating", 1, 500, 0, 7),
    (None, "Капитанская повязка", "Игрок с повязкой тянет за собой партнёров.", "🎗️", "accessory", "legendary", "chemistry", 1, 2000, 100, 8),
    (None, "Счастливая монета", "Талисман из первого жребия сезона.", "🪙", "artifact", "epic", "shot_pp", 4, 2500, 0, 9),
    (None, "Мяч финала", "Мяч, которым забили победный гол финала.", "⚽", "artifact", "legendary", "rating", 2, 0, 150, 10),
]


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'equipment_purchase'")

    collections = op.create_table(
        "equipment_collections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("image_path", sa.String(255), nullable=True),
        sa.Column("set_size", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("set_bonus_rating", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    items = op.create_table(
        "equipment_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("image_path", sa.String(255), nullable=True),
        sa.Column("icon", sa.String(16), nullable=False, server_default="👕"),
        sa.Column("slot", sa.String(16), nullable=False),
        sa.Column("rarity", sa.String(16), nullable=False, server_default="common"),
        sa.Column("collection_id", sa.Integer(), sa.ForeignKey("equipment_collections.id", ondelete="SET NULL"), nullable=True),
        sa.Column("effect", sa.String(16), nullable=False, server_default="rating"),
        sa.Column("effect_value", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cond_club", sa.String(64), nullable=True),
        sa.Column("cond_country", sa.String(64), nullable=True),
        sa.Column("coins_price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stars_price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_equipment_items_collection_id", "equipment_items", ["collection_id"])
    op.create_table(
        "user_equipment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("equipment_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("slot", sa.String(16), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("purchase_key", sa.String(128), nullable=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_card_id", "slot", name="uq_user_equipment_card_slot"),
        sa.UniqueConstraint("user_id", "purchase_key", name="uq_user_equipment_purchase_key"),
    )
    for column in ("user_id", "item_id", "user_card_id"):
        op.create_index(f"ix_user_equipment_{column}", "user_equipment", [column])

    op.add_column("user_cards", sa.Column("equipment_rating_bonus", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user_cards", sa.Column("equipment_chemistry", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user_cards", sa.Column("equipment_boosts", sa.JSON(), nullable=True))

    op.add_column("game_config", sa.Column("equipment_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("game_config", sa.Column("equipment_max_rating", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("game_config", sa.Column("equipment_max_pp", sa.Integer(), nullable=False, server_default="8"))
    op.add_column("game_config", sa.Column("equipment_max_chemistry", sa.Integer(), nullable=False, server_default="1"))

    op.bulk_insert(collections, [
        {"id": i + 1, "name": n, "description": d, "set_size": size, "set_bonus_rating": bonus, "is_active": True, "sort_order": s}
        for i, (n, d, size, bonus, s) in enumerate(COLLECTIONS)
    ])
    op.bulk_insert(items, [
        {
            "name": name, "description": desc, "icon": icon, "slot": slot, "rarity": rarity,
            "collection_id": (col + 1) if col is not None else None, "effect": effect, "effect_value": value,
            "coins_price": coins, "stars_price": stars, "is_active": True, "sort_order": sort,
        }
        for col, name, desc, icon, slot, rarity, effect, value, coins, stars, sort in ITEMS
    ])
    if op.get_bind().dialect.name == "postgresql":
        # Explicit ids above: move the sequence past them.
        op.execute("SELECT setval('equipment_collections_id_seq', (SELECT MAX(id) FROM equipment_collections))")


def downgrade() -> None:
    for name in ("equipment_max_chemistry", "equipment_max_pp", "equipment_max_rating", "equipment_enabled"):
        op.drop_column("game_config", name)
    for name in ("equipment_boosts", "equipment_chemistry", "equipment_rating_bonus"):
        op.drop_column("user_cards", name)
    op.drop_table("user_equipment")
    op.drop_index("ix_equipment_items_collection_id", table_name="equipment_items")
    op.drop_table("equipment_items")
    op.drop_table("equipment_collections")
    # transaction_type_enum keeps 'equipment_purchase' (Postgres cannot drop an enum value).
