"""«Мордобой» chat challenges (opponent type `chat`, stake column, stake
transaction types), «Бруталити» (cosmetic kind "brutality" + the starter
set of finishers, cosmetics.image_path / win_bonus_coins, notification and
transaction types) and «Стартовое предложение» for everyone who hasn't
bought it: starter_offer_for_all / starter_offer_all_since, switched on
together with the offer for the launch (50 ⭐: 10 000 coins, «Академия»
pack, «Рамка новичка») (the window of existing players
starts now; admins can switch either off in «Монетизация»).

Revision ID: 0193
Revises: 0192
Create Date: 2026-10-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0193"
down_revision: Union[str, None] = "0192"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copy of mordoboi_brutality.SEED: (style_key, name, description, coins, stars, sort).
BRUTALITY_SEED = (
    ("flick", "Щелбан", "Звонкий щелбан поверженному сопернику", 1000, 0, 1),
    ("fart", "Газовая атака", "Пёрнуть сопернику прямо под нос", 0, 100, 2),
    ("underpants", "Труханы на голову", "Надеть сопернику трусы на голову", 0, 100, 3),
    ("clown", "Клоунский нос", "Красный нос — теперь он клоун", 0, 100, 4),
    ("tickle", "Щекотка", "Защекотать пёрышком до икоты", 0, 100, 5),
    ("wet_willy", "Мокрый палец", "Мокрый палец в ухо — классика жанра", 0, 120, 6),
    ("lipstick", "Помада", "Накрасить губы и сделать фото на память", 0, 120, 7),
    ("sock", "Носок в рот", "Грязный носок прямо в рот", 0, 150, 8),
    ("armpit", "Подмышка", "Ткнуть носом в потную подмышку", 0, 150, 9),
    ("bucket", "Ведро воды", "Ледяной душ для проигравшего", 0, 150, 10),
    ("baby_song", "Колыбельная", "Спеть колыбельную нокаутированному", 0, 150, 11),
    ("cake", "Торт в лицо", "Кремовый торт в лицо проигравшему", 0, 200, 12),
    ("diaper", "Памперс", "Памперс и соска для проигравшего", 0, 200, 13),
    ("chicken", "Курица", "Проигравший кудахчет на весь стадион", 0, 250, 14),
)


def upgrade() -> None:
    op.execute("ALTER TYPE mordoboi_opponent_type_enum ADD VALUE IF NOT EXISTS 'chat'")
    for value in ("mordoboi_stake_lock", "mordoboi_stake_win", "mordoboi_stake_refund"):
        op.execute(f"ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS '{value}'")
    op.add_column("mordoboi_matches", sa.Column("stake_coins", sa.Integer(), nullable=False, server_default="0"))

    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'mordoboi_brutality'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'mordoboi_brutality_bonus'")
    op.add_column("cosmetics", sa.Column("image_path", sa.String(255), nullable=True))
    op.add_column("cosmetics", sa.Column("win_bonus_coins", sa.Integer(), nullable=False, server_default="0"))
    op.drop_constraint("ck_cosmetics_kind", "cosmetics", type_="check")
    op.create_check_constraint(
        "ck_cosmetics_kind", "cosmetics", "kind IN ('profile_frame', 'profile_background', 'card_skin', 'brutality')",
    )
    cosmetics = sa.table(
        "cosmetics", sa.column("kind", sa.String), sa.column("name", sa.String), sa.column("description", sa.String),
        sa.column("style_key", sa.String), sa.column("coins_price", sa.Integer), sa.column("stars_price", sa.Integer),
        sa.column("is_exclusive", sa.Boolean), sa.column("is_active", sa.Boolean), sa.column("sort_order", sa.Integer),
        sa.column("status", sa.Integer), sa.column("win_bonus_coins", sa.Integer),
    )
    op.bulk_insert(cosmetics, [
        {
            "kind": "brutality", "name": name, "description": description, "style_key": key,
            "coins_price": coins, "stars_price": stars, "is_exclusive": False, "is_active": True,
            "sort_order": sort, "status": 0, "win_bonus_coins": 10,
        }
        for key, name, description, coins, stars, sort in BRUTALITY_SEED
    ])

    op.add_column("game_config", sa.Column("starter_offer_for_all", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("game_config", sa.Column("starter_offer_all_since", sa.DateTime(timezone=True), nullable=True))
    # Launch contents: 50 ⭐ → 10 000 coins + the «Академия» pack + «Рамка
    # новичка» (one purchase per player — starter_offer_purchases.user_id).
    op.execute(
        "UPDATE game_config SET starter_offer_enabled = true, starter_offer_for_all = true, "
        "starter_offer_all_since = now(), starter_offer_stars = 50, starter_offer_coins = 10000, "
        "starter_offer_pack_id = COALESCE((SELECT id FROM packs WHERE slug = 'path-start' LIMIT 1), starter_offer_pack_id), "
        "starter_offer_cosmetic_id = COALESCE("
        "(SELECT id FROM cosmetics WHERE style_key = 'starter' AND kind = 'profile_frame' LIMIT 1), starter_offer_cosmetic_id)"
    )


def downgrade() -> None:
    op.execute("DELETE FROM cosmetics WHERE kind = 'brutality'")
    op.drop_constraint("ck_cosmetics_kind", "cosmetics", type_="check")
    op.create_check_constraint(
        "ck_cosmetics_kind", "cosmetics", "kind IN ('profile_frame', 'profile_background', 'card_skin')",
    )
    op.drop_column("cosmetics", "win_bonus_coins")
    op.drop_column("cosmetics", "image_path")
    op.drop_column("game_config", "starter_offer_all_since")
    op.drop_column("game_config", "starter_offer_for_all")
    op.drop_column("mordoboi_matches", "stake_coins")
    # Postgres cannot drop enum values — 'chat' and the stake types stay.
