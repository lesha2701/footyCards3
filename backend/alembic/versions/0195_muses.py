"""«Музы»: companions of «Мой футболист» — collections, Muses, the player's
album (copies, one active), gifts that raise a Muse's bonus, the daily coin
claim, the daily «Свидание» (a random mini-game on an extra attempt that
keeps her inspired), a per-slot Muse chance on packs and the «Музы» pack, GameConfig
switch and ceilings, transaction types. Seeds one collection of 20 fictional
Muses (emoji placeholders, photos are uploaded in the admin panel), a gift
catalog and the pack (inactive until the admin switches Muses on).

Revision ID: 0195
Revises: 0194
Create Date: 2026-10-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0195"
down_revision: Union[str, None] = "0194"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_KIND_CHECK = (
    "(CASE WHEN user_card_id IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN user_coach_card_id IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN user_stadium_card_id IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN skill_code IS NOT NULL THEN 1 ELSE 0 END) = 1"
)
NEW_KIND_CHECK = (
    "(CASE WHEN user_card_id IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN user_coach_card_id IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN user_stadium_card_id IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN skill_code IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN user_muse_id IS NOT NULL THEN 1 ELSE 0 END) = 1"
)

COLLECTION = ("Звёздные музы", "Двадцать муз «Моего футболиста»: каждая вдохновляет по-своему.")
# Fictional characters. (name, title, description, icon, rarity, effect, value, sort)
MUSES = [
    ("Изабелла Марино", "модель из Милана", "Лицо осенних показов. Приходит на каждый домашний матч.", "👸", "legendary", "daily_coins", 300, 1),
    ("Камила Сантос", "певица из Рио", "Её песню поёт весь стадион — и игрок выходит на поле другим.", "🎤", "legendary", "match_rating", 3, 2),
    ("Виктория Лейн", "дизайнер из Лондона", "Учит видеть игру целиком: опыт копится быстрее.", "💎", "legendary", "xp_bonus_pct", 15, 3),
    ("Луиза Ферран", "актриса из Парижа", "Верит в него больше всех — и он идёт вперёд.", "🎬", "epic", "attack", 3, 4),
    ("София Белл", "ведущая спортивного канала", "Разбирает его удары в эфире — точность растёт.", "📺", "epic", "shot_pp", 6, 5),
    ("Алина Орлова", "фигуристка", "Показала, как держать равновесие на скорости.", "⛸️", "epic", "dribble_pp", 6, 6),
    ("Марта Кляйн", "фотограф из Мюнхена", "Её снимки продаются лучше любой рекламы.", "📸", "epic", "daily_coins", 200, 7),
    ("Каролина Вега", "танцовщица из Мадрида", "Научила читать ритм соперника.", "💃", "epic", "defense", 3, 8),
    ("Эмма Розен", "модный блогер", "Каждый пост о нём — новые спонсоры.", "📱", "rare", "daily_coins", 150, 9),
    ("Нина Каро", "теннисистка", "Знает всё о восстановлении между матчами.", "🎾", "rare", "freshness_regen", 2, 10),
    ("Лаура Бьянки", "шеф-повар", "Правильный ужин — и тренировка идёт впрок.", "🍝", "rare", "xp_bonus_pct", 8, 11),
    ("Дарья Светлова", "фитнес-тренер", "Утренние пробежки вдвоём — и сил хватает до конца.", "🏋️", "rare", "freshness_regen", 3, 12),
    ("Ханна Мур", "диджей", "Плейлист перед матчем, после которого хочется забивать.", "🎧", "rare", "attack", 2, 13),
    ("Ольга Мирон", "спортивная журналистка", "Задаёт неудобные вопросы — он отвечает на поле.", "📝", "rare", "match_rating", 2, 14),
    ("Мия Коста", "студентка-архитектор", "Чертит схемы его передач на салфетках.", "📐", "common", "daily_coins", 80, 15),
    ("Ана Пейра", "бариста", "Лучший кофе в городе — и чаевые от фанатов.", "☕", "common", "daily_coins", 100, 16),
    ("Лина Хофф", "инструктор по йоге", "Растяжка после игры — и мышцы благодарны.", "🧘", "common", "freshness_regen", 1, 17),
    ("Ева Лоран", "художница", "Рисует его портреты — и он учится видеть поле.", "🎨", "common", "xp_bonus_pct", 5, 18),
    ("Кира Вольская", "болельщица с трибуны", "Самый громкий голос на секторе.", "📣", "common", "attack", 1, 19),
    ("Полина Рей", "флористка", "Цветы после каждой победы — и спокойствие в защите.", "💐", "common", "defense", 1, 20),
]
# (name, description, icon, kind, rarity, boost_pct, coins, stars, sort)
ACCESSORIES = [
    ("Букет роз", "Простой знак внимания.", "🌹", "other", "common", 5, 500, 0, 1),
    ("Сумочка-клатч", "Аккуратная сумочка на вечер.", "👛", "bag", "common", 10, 1500, 0, 2),
    ("Набор косметики", "Всё нужное в одной косметичке.", "💄", "cosmetics", "common", 10, 2000, 0, 3),
    ("Туфли на шпильке", "Для выхода на красную дорожку.", "👠", "shoes", "rare", 12, 3000, 0, 4),
    ("Флакон духов", "Аромат, который запоминается.", "🧴", "perfume", "rare", 12, 3000, 0, 5),
    ("Пляжный купальник", "Для отпуска между сезонами.", "👙", "swimsuit", "rare", 15, 3500, 0, 6),
    ("Вечернее платье", "Платье для церемонии наград.", "👗", "dress", "rare", 15, 4000, 0, 7),
    ("Люксовая косметика", "Набор из бутика.", "💅", "cosmetics", "epic", 20, 6000, 120, 8),
    ("Дизайнерская сумка", "Сумка из новой коллекции.", "👜", "bag", "epic", 25, 8000, 150, 9),
    ("Бриллиантовое колье", "Подарок на годовщину.", "💍", "jewelry", "legendary", 35, 25000, 350, 10),
    ("Платье от кутюр", "Единственное в своём роде.", "👘", "dress", "legendary", 40, 0, 400, 11),
]
DEFAULT_PROBABILITIES = (("common", 0.20), ("rare", 0.35), ("epic", 0.35), ("legendary", 0.10))


def _seed_pack(bind) -> None:
    if bind.execute(sa.text("SELECT id FROM packs WHERE slug = 'muses'")).first():
        return
    # «остальные шансы как у легендарного пака»: copy the coin pack that
    # names itself legendary (else the seed's top coin pack, «elite»).
    source = bind.execute(sa.text(
        "SELECT id, price, card_count, guaranteed_min_rarity, image_path FROM packs "
        "WHERE stars_price IS NULL AND (lower(slug) LIKE '%legend%' OR lower(name) LIKE '%legend%' "
        "OR lower(name) LIKE '%легенд%' OR name LIKE '%Легенд%') ORDER BY id LIMIT 1"
    )).first() or bind.execute(sa.text(
        "SELECT id, price, card_count, guaranteed_min_rarity, image_path FROM packs WHERE slug = 'elite'"
    )).first()
    price, count, guaranteed, image = (
        (source.price, source.card_count, source.guaranteed_min_rarity, source.image_path) if source else (2000, 5, "epic", None)
    )
    probabilities = [
        (r.rarity, float(r.probability)) for r in bind.execute(sa.text(
            "SELECT rarity, probability FROM pack_rarity_probabilities WHERE pack_id = :p"
        ), {"p": source.id})
    ] if source else []
    pack_id = bind.execute(sa.text(
        "INSERT INTO packs (slug, name, description, price, card_count, guaranteed_min_rarity, is_active, sort_order, "
        "coach_drop_chance, stadium_drop_chance, skill_token_drop_chance, muse_drop_chance, player_pool, image_path, "
        "created_at, updated_at) VALUES ('muses', 'Музы', :d, :price, :count, :g, false, 60, 0, 0, 0, 0.1, "
        "'default', :img, now(), now()) RETURNING id"
    ), {
        "d": "Каждая карточка — 10% шанс на музу «Моего футболиста», остальные шансы как у легендарного пака",
        "price": price, "count": count, "g": guaranteed, "img": image,  # its picture until the admin uploads one
    }).scalar_one()
    for rarity, probability in probabilities or DEFAULT_PROBABILITIES:
        bind.execute(
            sa.text("INSERT INTO pack_rarity_probabilities (pack_id, rarity, probability) VALUES (:p, :r, :v)"),
            {"p": pack_id, "r": rarity, "v": probability},
        )


def upgrade() -> None:
    for value in ("muse_daily_coins", "muse_accessory_purchase", "muse_spare_sale", "muse_date_reward"):
        op.execute(f"ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS '{value}'")

    timestamps = (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    collections = op.create_table(
        "muse_collections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("image_path", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        *[c.copy() for c in timestamps],
    )
    muses = op.create_table(
        "muses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("collection_id", sa.Integer(), sa.ForeignKey("muse_collections.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("title", sa.String(64), nullable=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("icon", sa.String(16), nullable=False, server_default="💃"),
        sa.Column("image_path", sa.String(255), nullable=True),
        sa.Column("rarity", sa.String(16), nullable=False, server_default="common"),
        sa.Column("effect", sa.String(24), nullable=False, server_default="daily_coins"),
        sa.Column("effect_value", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("drop_weight", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        *[c.copy() for c in timestamps],
    )
    op.create_index("ix_muses_collection_id", "muses", ["collection_id"])
    op.create_table(
        "user_muses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("muse_id", sa.Integer(), sa.ForeignKey("muses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("copies", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "muse_id", name="uq_user_muses_user_muse"),
    )
    op.create_index("ix_user_muses_user_id", "user_muses", ["user_id"])
    op.create_index("ix_user_muses_muse_id", "user_muses", ["muse_id"])
    op.create_index("uq_user_muses_one_active", "user_muses", ["user_id"], unique=True, postgresql_where=sa.text("is_active"))
    accessories = op.create_table(
        "muse_accessories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("icon", sa.String(16), nullable=False, server_default="👜"),
        sa.Column("image_path", sa.String(255), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False, server_default="other"),
        sa.Column("rarity", sa.String(16), nullable=False, server_default="common"),
        sa.Column("boost_pct", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("coins_price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stars_price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        *[c.copy() for c in timestamps],
    )
    op.create_table(
        "user_muse_accessories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_muse_id", sa.Integer(), sa.ForeignKey("user_muses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("accessory_id", sa.Integer(), sa.ForeignKey("muse_accessories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("purchase_key", sa.String(128), nullable=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_muse_id", "accessory_id", name="uq_user_muse_accessories_once"),
        sa.UniqueConstraint("user_id", "purchase_key", name="uq_user_muse_accessories_purchase_key"),
    )
    op.create_index("ix_user_muse_accessories_user_id", "user_muse_accessories", ["user_id"])
    op.create_index("ix_user_muse_accessories_user_muse_id", "user_muse_accessories", ["user_muse_id"])
    op.create_table(
        "muse_daily_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_date", sa.Date(), nullable=False),
        sa.Column("muse_id", sa.Integer(), sa.ForeignKey("muses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("coins", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "claim_date", name="uq_muse_daily_claims_user_day"),
    )
    op.create_table(
        "muse_dates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date_day", sa.Date(), nullable=False),
        sa.Column("game", sa.String(16), nullable=False),
        sa.Column("muse_id", sa.Integer(), sa.ForeignKey("muses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "date_day", name="uq_muse_dates_user_day"),
    )
    op.create_index("ix_muse_dates_session_id", "muse_dates", ["session_id"])

    op.add_column("packs", sa.Column("muse_drop_chance", sa.Numeric(5, 4), nullable=False, server_default="0"))
    op.add_column("pack_opening_cards", sa.Column(
        "user_muse_id", sa.Integer(), sa.ForeignKey("user_muses.id", ondelete="CASCADE"), nullable=True,
    ))
    op.drop_constraint("ck_pack_opening_card_exactly_one_kind", "pack_opening_cards", type_="check")
    op.create_check_constraint("ck_pack_opening_card_exactly_one_kind", "pack_opening_cards", NEW_KIND_CHECK)

    op.add_column("game_config", sa.Column("muses_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("game_config", sa.Column("muse_max_stat", sa.Integer(), nullable=False, server_default="6"))
    op.add_column("game_config", sa.Column("muse_max_pp", sa.Integer(), nullable=False, server_default="12"))
    op.add_column("game_config", sa.Column("muse_max_xp_pct", sa.Integer(), nullable=False, server_default="30"))
    op.add_column("game_config", sa.Column("muse_max_daily_coins", sa.Integer(), nullable=False, server_default="1000"))
    op.add_column("game_config", sa.Column("muse_max_accessory_pct", sa.Integer(), nullable=False, server_default="100"))
    op.add_column("game_config", sa.Column(
        "muse_spare_coins", sa.JSON(), nullable=False,
        server_default='{"common": 150, "rare": 400, "epic": 1000, "legendary": 3000}',
    ))
    op.add_column("game_config", sa.Column(
        "muse_date_games", sa.JSON(), nullable=False, server_default='["memory", "pairs", "hangman"]',
    ))
    op.add_column("game_config", sa.Column("muse_date_coins", sa.Integer(), nullable=False, server_default="150"))
    op.add_column("game_config", sa.Column("muse_date_required", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("game_config", sa.Column("muse_inspiration_hours", sa.Integer(), nullable=False, server_default="36"))

    bind = op.get_bind()
    bind.execute(collections.insert().values(name=COLLECTION[0], description=COLLECTION[1], is_active=True, sort_order=1))
    collection_id = bind.execute(sa.select(collections.c.id).where(collections.c.name == COLLECTION[0])).scalar_one()
    op.bulk_insert(muses, [
        {
            "collection_id": collection_id, "name": name, "title": title, "description": desc, "icon": icon,
            "rarity": rarity, "effect": effect, "effect_value": value, "drop_weight": 100, "is_active": True,
            "sort_order": sort,
        }
        for name, title, desc, icon, rarity, effect, value, sort in MUSES
    ])
    op.bulk_insert(accessories, [
        {
            "name": name, "description": desc, "icon": icon, "kind": kind, "rarity": rarity, "boost_pct": boost,
            "coins_price": coins, "stars_price": stars, "is_active": True, "sort_order": sort,
        }
        for name, desc, icon, kind, rarity, boost, coins, stars, sort in ACCESSORIES
    ])
    _seed_pack(bind)


def downgrade() -> None:
    bind = op.get_bind()
    # Muse slots of past openings go; the seeded pack goes unless it was opened.
    bind.execute(sa.text("DELETE FROM pack_opening_cards WHERE user_muse_id IS NOT NULL"))
    bind.execute(sa.text(
        "DELETE FROM packs WHERE slug = 'muses' AND NOT EXISTS (SELECT 1 FROM pack_openings o WHERE o.pack_id = packs.id)"
    ))
    op.drop_constraint("ck_pack_opening_card_exactly_one_kind", "pack_opening_cards", type_="check")
    op.create_check_constraint("ck_pack_opening_card_exactly_one_kind", "pack_opening_cards", OLD_KIND_CHECK)
    op.drop_column("pack_opening_cards", "user_muse_id")
    op.drop_column("packs", "muse_drop_chance")
    for name in ("muse_inspiration_hours", "muse_date_required", "muse_date_coins", "muse_date_games",
                 "muse_spare_coins", "muse_max_accessory_pct", "muse_max_daily_coins", "muse_max_xp_pct",
                 "muse_max_pp", "muse_max_stat", "muses_enabled"):
        op.drop_column("game_config", name)
    op.drop_index("ix_muse_dates_session_id", table_name="muse_dates")
    op.drop_table("muse_dates")
    op.drop_table("muse_daily_claims")
    op.drop_table("user_muse_accessories")
    op.drop_table("muse_accessories")
    op.drop_table("user_muses")
    op.drop_index("ix_muses_collection_id", table_name="muses")
    op.drop_table("muses")
    op.drop_table("muse_collections")
    # transaction_type_enum keeps the muse_* values (Postgres cannot drop an enum value).
