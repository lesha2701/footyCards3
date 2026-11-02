"""«🎃 Ночь тыкв»: pumpkins (halloween_wallets / halloween_ledger), the event
switch, dates and numbers on game_config, the collection frame
(card_collections.card_skin), and the event's badge «Тыква 2026», the
collection «Ночь живых Легенд» with its 20 footballers (art in
static/players/<rarity>/hw_*.webp) and its pack (drops only that collection).
The collection, its footballers and the pack start switched off and out of
the regular packs — an admin turns them on.

Revision ID: 0222
Revises: 0221
Create Date: 2026-10-31
"""
import json
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0222"
down_revision: Union[str, None] = "0221"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 31.10 00:00 – 05.11 00:00 Moscow (the event runs through 04.11). Real
# datetimes: asyncpg refuses a string for a timestamptz parameter.
_MSK = timezone(timedelta(hours=3))
STARTS_AT = datetime(2026, 10, 31, tzinfo=_MSK)
ENDS_AT = datetime(2026, 11, 5, tzinfo=_MSK)
PACK_SLUG = "halloween-legends-2026"
COLLECTION = "Ночь живых Легенд"
BADGE = "Тыква 2026"
PACK_ODDS = (("rare", Decimal("0.55")), ("epic", Decimal("0.35")), ("legendary", Decimal("0.10")))
SELL_PRICE = {"rare": 35, "epic": 120, "legendary": 400}
# display name, art slug, position, country, the most successful club of the career, rating, rarity
LEGENDS = (
    ("Коул Палмер", "palmer", "CAM", "Англия", "Челси", 87, "epic"),
    ("Кенан Йылдыз", "yildiz", "LW", "Турция", "Ювентус", 84, "epic"),
    ("Морган Роджерс", "rogers", "CAM", "Англия", "Астон Вилла", 81, "rare"),
    ("Франко Мастантуоно", "mastantuono", "RW", "Аргентина", "Реал Мадрид", 78, "rare"),
    ("Георгий Судаков", "sudakov", "CM", "Украина", "Шахтёр Донецк", 79, "rare"),
    ("Антонио Нуса", "nusa", "LW", "Норвегия", "РБ Лейпциг", 79, "rare"),
    ("Матеус Кунья", "cunha", "ST", "Бразилия", "Атлетико Мадрид", 85, "epic"),
    ("Юго Экитике", "ekitike", "ST", "Франция", "Ливерпуль", 85, "epic"),
    ("Барт Вербрюгген", "verbruggen", "GK", "Нидерланды", "Брайтон", 80, "rare"),
    ("Рикарду Куарежма", "quaresma", "RW", "Португалия", "Порту", 85, "epic"),
    ("Димитар Бербатов", "berbatov", "ST", "Болгария", "Манчестер Юнайтед", 90, "legendary"),
    ("Гути", "guti", "CAM", "Испания", "Реал Мадрид", 88, "epic"),
    ("Диего Форлан", "forlan", "ST", "Уругвай", "Атлетико Мадрид", 90, "legendary"),
    ("Клаудио Писарро", "pizarro", "ST", "Перу", "Бавария", 87, "epic"),
    ("Димитри Пайет", "payet", "CAM", "Франция", "Марсель", 86, "epic"),
    ("Маруан Феллайни", "fellaini", "CM", "Бельгия", "Манчестер Юнайтед", 83, "epic"),
    ("Виктор Дьёкереш", "gyokeres", "ST", "Швеция", "Спортинг", 88, "epic"),
    ("Марек Гамшик", "hamsik", "CAM", "Словакия", "Наполи", 88, "epic"),
    ("Деннис Бергкамп", "bergkamp", "ST", "Нидерланды", "Арсенал", 94, "legendary"),
    ("Пеле", "pele", "ST", "Бразилия", "Сантос", 98, "legendary"),
)
# Attack / defence around the rating by line.
LINE_SPLIT = {"GK": (-30, 2), "CM": (-1, -8), "CAM": (1, -25), "LW": (1, -28), "RW": (1, -28), "ST": (2, -35)}


def _split(display_name: str) -> tuple[str, str]:
    parts = display_name.split(maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else parts[0]


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'halloween_reward'")

    op.add_column("game_config", sa.Column("halloween_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("game_config", sa.Column("halloween_starts_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("game_config", sa.Column("halloween_ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("game_config", sa.Column("halloween_settings", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("card_collections", sa.Column("card_skin", sa.String(16), nullable=True))

    op.create_table(
        "halloween_wallets",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("event_key", sa.String(32), primary_key=True),
        sa.Column("pumpkins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("earned_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("games_day", sa.String(10), nullable=True),
        sa.Column("games_pumpkins_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("zombie_player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="SET NULL"), nullable=True),
        sa.Column("zombie_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "halloween_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_key", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("ref_key", sa.String(96), nullable=True),
        sa.Column("item_code", sa.String(32), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "ref_key", name="uq_halloween_ledger_user_ref"),
    )
    op.create_index("ix_halloween_ledger_user_id", "halloween_ledger", ["user_id"])

    conn = op.get_bind()
    badge_id = conn.execute(sa.text(
        "INSERT INTO badges (name, icon, is_active, sort_order) VALUES (:name, '🎃', true, 900) RETURNING id"
    ), {"name": BADGE}).scalar_one()
    collection_id = conn.execute(sa.text(
        "SELECT id FROM card_collections WHERE name = :name"
    ), {"name": COLLECTION}).scalar()
    if collection_id is None:
        collection_id = conn.execute(sa.text(
            "INSERT INTO card_collections (name, description, is_active, sort_order, reward_coins, card_skin, "
            "created_at, updated_at) VALUES (:name, :descr, false, 900, 5000, 'zombie', now(), now()) RETURNING id"
        ), {"name": COLLECTION, "descr": "Легенды восстали из мёртвых на одну ночь. Собери всех — получи награду."}
        ).scalar_one()
    else:
        conn.execute(sa.text("UPDATE card_collections SET card_skin = 'zombie' WHERE id = :id"), {"id": collection_id})
    for name, slug, position, country, club, rating, rarity in LEGENDS:
        if conn.execute(sa.text(
            "SELECT 1 FROM players WHERE display_name = :n AND collection_id = :c"
        ), {"n": name, "c": collection_id}).first():
            continue
        first, last = _split(name)
        atk, dfn = LINE_SPLIT[position]
        conn.execute(sa.text(
            "INSERT INTO players (first_name, last_name, display_name, rating, attack_rating, defense_rating, rarity, "
            "country, club, position, image_path, quick_sell_price, is_active, is_pack_droppable, collection_id, "
            "next_serial_number, next_club_serial_number, created_at, updated_at) "
            "VALUES (:first, :last, :name, :rating, :atk, :dfn, CAST(:rarity AS rarity_enum), :country, :club, "
            "CAST(:position AS position_enum), :image, :sell, false, false, :collection, 1, 1, now(), now())"
        ), {
            "first": first, "last": last, "name": name, "rating": rating,
            "atk": max(1, min(99, rating + atk)), "dfn": max(1, min(99, rating + dfn)), "rarity": rarity,
            "country": country, "club": club, "position": position,
            "image": f"players/{rarity}/hw_{slug}.webp", "sell": SELL_PRICE[rarity], "collection": collection_id,
        })

    pack_id = conn.execute(sa.text(
        "INSERT INTO packs (slug, name, description, price, card_count, guaranteed_min_rarity, is_active, sort_order, "
        "available_from, available_until, pity_enabled, coach_drop_chance, stadium_drop_chance, "
        "skill_token_drop_chance, player_pool, muse_drop_chance, created_at, updated_at) "
        "VALUES (:slug, :name, :descr, 2500, 3, 'rare', false, -10, :start, :end, false, 0, 0, 0, :pool, 0, now(), now()) "
        "ON CONFLICT (slug) DO NOTHING RETURNING id"
    ), {
        "slug": PACK_SLUG, "name": "Ночь живых Легенд",
        "descr": "Только на Хеллоуин: 3 карточки коллекции «Ночь живых Легенд» в зомби-рамке.",
        "start": STARTS_AT, "end": ENDS_AT, "pool": f"collection:{collection_id}",
    }).scalar()
    if pack_id is not None:
        for rarity, p in PACK_ODDS:
            conn.execute(sa.text(
                "INSERT INTO pack_rarity_probabilities (pack_id, rarity, probability) VALUES (:p, CAST(:r AS rarity_enum), :prob)"
            ), {"p": pack_id, "r": rarity, "prob": p})
    else:
        pack_id = conn.execute(sa.text("SELECT id FROM packs WHERE slug = :s"), {"s": PACK_SLUG}).scalar_one()
    conn.execute(sa.text(
        "UPDATE game_config SET halloween_starts_at = :start, halloween_ends_at = :end, "
        "halloween_settings = CAST(:settings AS JSON) WHERE id = 1"
    ), {"start": STARTS_AT, "end": ENDS_AT, "settings": json.dumps(
        {"pack_id": pack_id, "badge_id": badge_id, "collection_id": collection_id})})


def downgrade() -> None:
    op.drop_index("ix_halloween_ledger_user_id", table_name="halloween_ledger")
    op.drop_table("halloween_ledger")
    op.drop_table("halloween_wallets")
    op.drop_column("card_collections", "card_skin")
    op.drop_column("game_config", "halloween_settings")
    op.drop_column("game_config", "halloween_ends_at")
    op.drop_column("game_config", "halloween_starts_at")
    op.drop_column("game_config", "halloween_enabled")
