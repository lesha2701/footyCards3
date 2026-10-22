"""«Мордобой», second wave: «Легенда ринга» (mordoboi_matches.mode, users'
legend day / wins, GameConfig reward and rating), «Выход на ринг» (cosmetic
kinds ring_gloves / ring_shorts / ring_entrance with equip slots on users,
a preset nickname), «Каска» (cosmetic kind helmet), «Клубный ринг»
(GameConfig points / cap) and the notification / transaction types.

Revision ID: 0194
Revises: 0193
Create Date: 2026-10-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0194"
down_revision: Union[str, None] = "0193"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KINDS_BEFORE = "'profile_frame', 'profile_background', 'card_skin', 'brutality'"
KINDS_AFTER = KINDS_BEFORE + ", 'ring_gloves', 'ring_shorts', 'ring_entrance', 'helmet'"

CONFIG_INT_COLUMNS = (
    ("mordoboi_legend_rating", "90"),
    ("mordoboi_legend_reward", "150"),
    ("club_ring_win_points", "30"),
    ("club_ring_member_cap", "300"),
)
SLOTS = ("equipped_ring_gloves_id", "equipped_ring_shorts_id", "equipped_ring_entrance_id")

# Frozen copy of mordoboi_look.SEED: (kind, style_key, name, description, coins, stars, sort).
SEED = (
    ("ring_gloves", "pink", "Розовые перчатки", "Нежно, но больно", 2000, 0, 1),
    ("ring_gloves", "steel", "Стальные перчатки", "Звенят при каждом ударе", 3000, 0, 2),
    ("ring_gloves", "toxic", "Токсичные перчатки", "Светятся ядовито-зелёным", 4000, 0, 3),
    ("ring_gloves", "fire", "Огненные перчатки", "Горят во время боя", 0, 60, 4),
    ("ring_gloves", "ice", "Ледяные перчатки", "Морозят соперника взглядом", 0, 60, 5),
    ("ring_gloves", "neon", "Неоновые перчатки", "Переливаются как вывеска", 0, 80, 6),
    ("ring_gloves", "gold", "Золотые перчатки", "Для чемпионов", 0, 120, 7),
    ("ring_shorts", "black", "Чёрные трусы", "Классика тяжеловесов", 1500, 0, 1),
    ("ring_shorts", "white", "Белые трусы", "Смело — на них видно всё", 1500, 0, 2),
    ("ring_shorts", "blue", "Синие трусы", "Синий угол ринга", 1500, 0, 3),
    ("ring_shorts", "green", "Зелёные трусы", "Цвет газона", 1500, 0, 4),
    ("ring_shorts", "gold", "Золотые трусы", "Блестят под прожекторами", 0, 80, 5),
    ("ring_shorts", "stars", "Трусы со звёздами", "Как у легенд прошлого", 0, 100, 6),
    ("ring_entrance", "confetti", "Конфетти", "Выход под дождь из конфетти", 3000, 0, 1),
    ("ring_entrance", "spotlight", "Луч прожектора", "Свет только на тебе", 5000, 0, 2),
    ("ring_entrance", "smoke", "Дым и прожектор", "Выход из клубов дыма", 0, 100, 3),
    ("ring_entrance", "fireworks", "Фейерверк", "Салют в твою честь", 0, 150, 4),
    ("ring_entrance", "lightning", "Молнии", "Разряды по канатам ринга", 0, 150, 5),
    ("helmet", "helmet", "Каска", "Один раз отражает чужое бруталити обратно в победителя", 2000, 30, 1),
)


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'mordoboi_helmet'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'mordoboi_legend_reward'")

    op.add_column("mordoboi_matches", sa.Column("mode", sa.String(16), nullable=False, server_default="normal"))
    op.add_column("users", sa.Column("mordoboi_legend_day", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("mordoboi_legend_wins", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("mordoboi_nickname", sa.String(32), nullable=True))
    for slot in SLOTS:
        op.add_column("users", sa.Column(slot, sa.Integer(), nullable=True))
        op.create_foreign_key(f"fk_users_{slot}", "users", "cosmetics", [slot], ["id"], ondelete="SET NULL")
    for name, default in CONFIG_INT_COLUMNS:
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=default))

    op.drop_constraint("ck_cosmetics_kind", "cosmetics", type_="check")
    op.create_check_constraint("ck_cosmetics_kind", "cosmetics", f"kind IN ({KINDS_AFTER})")
    cosmetics = sa.table(
        "cosmetics", sa.column("kind", sa.String), sa.column("name", sa.String), sa.column("description", sa.String),
        sa.column("style_key", sa.String), sa.column("coins_price", sa.Integer), sa.column("stars_price", sa.Integer),
        sa.column("is_exclusive", sa.Boolean), sa.column("is_active", sa.Boolean), sa.column("sort_order", sa.Integer),
        sa.column("status", sa.Integer), sa.column("win_bonus_coins", sa.Integer),
    )
    op.bulk_insert(cosmetics, [
        {
            "kind": kind, "name": name, "description": description, "style_key": key, "coins_price": coins,
            "stars_price": stars, "is_exclusive": False, "is_active": True, "sort_order": sort, "status": 0,
            "win_bonus_coins": 0,
        }
        for kind, key, name, description, coins, stars, sort in SEED
    ])


def downgrade() -> None:
    for slot in SLOTS:
        op.drop_constraint(f"fk_users_{slot}", "users", type_="foreignkey")
        op.drop_column("users", slot)
    op.execute("DELETE FROM cosmetics WHERE kind IN ('ring_gloves', 'ring_shorts', 'ring_entrance', 'helmet')")
    op.drop_constraint("ck_cosmetics_kind", "cosmetics", type_="check")
    op.create_check_constraint("ck_cosmetics_kind", "cosmetics", f"kind IN ({KINDS_BEFORE})")
    for name, _ in reversed(CONFIG_INT_COLUMNS):
        op.drop_column("game_config", name)
    for name in ("mordoboi_nickname", "mordoboi_legend_wins", "mordoboi_legend_day"):
        op.drop_column("users", name)
    op.drop_column("mordoboi_matches", "mode")
    # Postgres cannot drop enum values — the added types stay.
