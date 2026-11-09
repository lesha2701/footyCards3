"""«Город»: opened for coins and renamed for Stars, houses and the hotel
bought for coins, their daily rent, closed places on the map (pier, park,
island), «Жители города» (resident cards, their
packs and shop offers) and the town settings.

Revision ID: 0267
Revises: 0266
Create Date: 2026-11-07
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0267"
down_revision: Union[str, None] = "0266"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The same values as models/game_config.DEFAULT_TOWN_DISTRICTS.
_DISTRICTS = {
    "favela": {"price": 1000, "rent": 15},
    "center": {"price": 2000, "rent": 25},
    "mountains": {"price": 3000, "rent": 35},
    "beach": {"price": 4000, "rent": 45},
    "business": {"price": 6000, "rent": 60},
}
# The same values as models/game_config.DEFAULT_TOWN_RESIDENT_SPARE_COINS.
_SPARE = {"common": 10, "rare": 30, "epic": 100, "legendary": 300}
# The same values as models/game_config.DEFAULT_TOWN_DECOR.
_DECOR = {
    "pier": {"price": 20000, "rent_pct": 5},
    "park": {"price": 40000, "rent_pct": 8},
    "island": {"price": 75000, "rent_pct": 12},
}

OLD_KIND_CHECK = (
    "(CASE WHEN user_card_id IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN user_coach_card_id IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN user_stadium_card_id IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN skill_code IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN user_muse_id IS NOT NULL THEN 1 ELSE 0 END) = 1"
)
NEW_KIND_CHECK = (
    "(CASE WHEN user_card_id IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN user_coach_card_id IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN user_stadium_card_id IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN skill_code IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN user_muse_id IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN user_town_resident_id IS NOT NULL THEN 1 ELSE 0 END) = 1"
)
OLD_OFFER_CHECK = (
    "(player_id IS NOT NULL)::int + (coach_id IS NOT NULL)::int + (stadium_id IS NOT NULL)::int "
    "+ (muse_id IS NOT NULL)::int = 1"
)
NEW_OFFER_CHECK = (
    "(player_id IS NOT NULL)::int + (coach_id IS NOT NULL)::int + (stadium_id IS NOT NULL)::int "
    "+ (muse_id IS NOT NULL)::int + (resident_id IS NOT NULL)::int = 1"
)

# The «Жители» packs: residents only (resident_drop_chance 1), the legendary
# ones rare and never forced by the legendary pity. Active: RESIDENTS below fill them.
# slug, name, description, coins price, stars price, cards, guaranteed rarity
RESIDENT_PACKS = (
    ("residents", "Жители", "Новый житель для твоего города: ещё один житель и монеты в ренту каждый день",
     1000, None, 1, None),
    ("residents_stars", "Жители ⭐", "Житель с повышенным шансом на редкого и эпического",
     0, 5, 1, None),
)
RESIDENT_PROBABILITIES = {
    "residents": (("common", 0.63), ("rare", 0.27), ("epic", 0.09), ("legendary", 0.01)),
    "residents_stars": (("common", 0.49), ("rare", 0.35), ("epic", 0.15), ("legendary", 0.01)),
}


# The first residents of the town (pictures in static/residents/town; the admin
# edits or adds more in «Жители»). Bonuses only on the legendary ones.
# slug, name, title, description, icon, rarity, bonus, bonus value
RESIDENTS = (
    ("augushtu", "Аугушту", "мэр города", "В цилиндре и с лентой мэра: открывает каждый матч и каждый новый дом", "🎩", "legendary", "rent_pct", 5),
    ("enrike", "Энрике", "архитектор стадиона", "Чертит новый стадион прямо на набережной — и весь город растёт за ним", "📐", "legendary", "rent_pct", 3),
    ("karlos", "Карлос", "хозяин отеля", "Знает каждого гостя по имени и всегда находит свободный номер", "🏨", "legendary", "hotel_pct", 10),
    ("duarte", "Дуарте", "смотритель маяка", "Зажигает маяк в любой шторм, чтобы корабли с болельщиками дошли до порта", "🗼", "legendary", "daily_coins", 15),
    ("marta", "Марта", "волейболистка", "Тренируется на пляже с рассвета — и твой игрок с ней", "🏐", "legendary", "xp_pct", 10),
    ("matilde", "Матилде", "футболистка", "Зовёт сыграть ещё одну — и в любой мини-игре найдётся лишняя попытка", "⚽", "legendary", "game_attempts", 1),
    ("oksana", "Оксана", "инженер", "Рассчитывает трибуны и корпуса — бригада на базе строит быстрее", "📏", "legendary", "build_pct", 10),
    ("mariana", "Мариана", "стадионный фотограф", "Ловит каждый гол с бровки поля", "📸", "epic", "none", 0),
    ("tomash", "Томаш", "юный болельщик", "Мечтает выйти на этот стадион в форме своего клуба", "🧒", "epic", "none", 0),
    ("nunu", "Нуну", "барабанщик", "Задаёт ритм трибунам с первой до последней минуты", "🥁", "epic", "none", 0),
    ("irma", "Ирма", "консьерж", "Хранит ключи от всех номеров и все секреты отеля", "🔑", "epic", "none", 0),
    ("marko", "Марко", "шеф-повар", "Жарит рыбу так, что на запах приходит весь квартал", "👨‍🍳", "epic", "none", 0),
    ("leo", "Лео", "душа пляжа", "С мячом и в цветастой рубашке — где Лео, там праздник", "🤙", "epic", "none", 0),
    ("ana", "Ана", "художница", "Расписывает стены города футбольными фресками", "🎨", "rare", "none", 0),
    ("brunu", "Бруну", "трамвайщик", "Довозит болельщиков до стадиона минута в минуту", "🚋", "rare", "none", 0),
    ("rafael", "Рафаэл", "сапожник", "Чинит бутсы всей городской команде", "👞", "rare", "none", 0),
    ("klara", "Клара", "керамистка", "Лепит кубки и тарелки с гербом клуба", "🏺", "rare", "none", 0),
    ("irina", "Ирина", "журналистка", "Первой берёт интервью после каждого матча", "🎙️", "rare", "none", 0),
    ("tiagu", "Тиагу", "сёрфер", "Ловит волну утром и идёт на матч вечером", "🏄", "rare", "none", 0),
    ("sofia-spasatel", "София", "спасательница", "Следит за пляжем с вышки весь день", "🛟", "rare", "none", 0),
    ("sofia-biolog", "София", "морской биолог", "Изучает ракушки и рыб у городского берега", "🐚", "rare", "none", 0),
    ("katarina", "Катарина", "барменша", "Смешивает фирменный коктейль в цветах клуба", "🍹", "rare", "none", 0),
    ("paulo", "Паулу", "таксист", "Знает все короткие дороги к стадиону", "🚕", "rare", "none", 0),
    ("rikardu", "Рикарду", "курьер", "Развозит посылки на мотоцикле по серпантину", "🏍️", "rare", "none", 0),
    ("jorji", "Жоржи", "рыбак", "Чинит сети на причале и рассказывает о старых матчах", "🎣", "rare", "none", 0),
    ("bianka", "Бьянка", "пляжный волейбол", "Играет на песке до самого заката", "🏐", "common", "none", 0),
    ("joze", "Жозе", "торговец с рынка", "Продаёт самые сладкие апельсины на площади", "🍊", "common", "none", 0),
    ("fernandu", "Фернанду", "старожил набережной", "Помнит, как построили первый стадион", "👍", "common", "none", 0),
    ("maria", "Мария", "фруктовая лавка", "Торгует фруктами у самой гавани", "🍋", "common", "none", 0),
    ("amelia", "Амелия", "соседка с цветами", "Поливает герань на каждом балконе улицы", "🌺", "common", "none", 0),
    ("antoniu", "Антониу", "читатель газет", "Каждое утро разбирает вчерашний матч за кофе", "📰", "common", "none", 0),
    ("beatris", "Беатрис", "флористка", "Собирает букеты для победителей", "💐", "common", "none", 0),
    ("vasku", "Васку", "гуляет с собакой", "Каждый вечер обходит набережную со своим псом", "🐕", "common", "none", 0),
    ("gonsalu", "Гонсалу", "автомеханик", "Починит любую машину, пока идёт тайм", "🔧", "common", "none", 0),
    ("daniel", "Даниэл", "скейтер", "Катается по ступенькам старого города", "🛹", "common", "none", 0),
    ("joana", "Жоана", "механик", "Перебирает моторы в мастерской у порта", "🛠️", "common", "none", 0),
    ("inesh", "Инеш", "студентка", "Рисует стадион в скетчбуке под музыку", "🎧", "common", "none", 0),
    ("leonor", "Леонор", "малышка", "Пускает мыльные пузыри на площади", "🫧", "common", "none", 0),
    ("lusia", "Лусия", "бариста", "Рисует мяч на пенке каждого капучино", "☕", "common", "none", 0),
    ("migel", "Мигел", "пекарь", "Печёт хлеб для всего квартала с рассвета", "🥖", "common", "none", 0),
    ("roza", "Роза", "бабушка с рынка", "Несёт с рынка корзину овощей и все новости", "🧺", "common", "none", 0),
    ("tereza", "Тереза", "почтальонка", "Приносит письма и билеты на матчи", "✉️", "common", "none", 0),
)

# slug, Stars price, tile title — residents sold in «Карты ⭐».
RESIDENT_OFFERS = (("marta", 500, "Легенда пляжа"),)


def _seed_residents(bind) -> None:
    if bind.execute(sa.text("SELECT 1 FROM town_residents LIMIT 1")).first():
        return
    for order, (slug, name, title, description, icon, rarity, bonus, value) in enumerate(RESIDENTS):
        bind.execute(sa.text(
            "INSERT INTO town_residents (name, title, description, icon, image_path, rarity, bonus, bonus_value, "
            "drop_weight, is_pack_droppable, is_active, sort_order, created_at, updated_at) VALUES "
            "(:name, :title, :d, :icon, :image, :rarity, :bonus, :value, 100, true, true, :order, now(), now())"
        ), {"name": name, "title": title, "d": description, "icon": icon, "image": f"residents/town/{slug}.webp",
            "rarity": rarity, "bonus": bonus, "value": value, "order": order})
    # «Марта» is also sold in the shop for Stars (one per player, no stock limit).
    for slug, stars, offer_title in RESIDENT_OFFERS:
        resident_id = bind.execute(sa.text("SELECT id FROM town_residents WHERE image_path = :p"),
                                   {"p": f"residents/town/{slug}.webp"}).scalar_one()
        bind.execute(sa.text(
            "INSERT INTO card_offers (resident_id, stars_price, title, per_user_limit, sold_count, is_active, "
            "sort_order, created_at, updated_at) VALUES (:r, :stars, :title, 1, 0, true, 0, now(), now())"
        ), {"r": resident_id, "stars": stars, "title": offer_title})


def _seed_packs(bind) -> None:
    for slug, name, description, price, stars, count, guaranteed in RESIDENT_PACKS:
        if bind.execute(sa.text("SELECT id FROM packs WHERE slug = :s"), {"s": slug}).first():
            continue
        pack_id = bind.execute(sa.text(
            "INSERT INTO packs (slug, name, description, image_path, price, stars_price, card_count, guaranteed_min_rarity, "
            "is_active, pity_enabled, sort_order, coach_drop_chance, stadium_drop_chance, skill_token_drop_chance, "
            "muse_drop_chance, resident_drop_chance, player_pool, created_at, updated_at) VALUES "
            "(:slug, :name, :d, :image, :price, :stars, :count, :g, true, false, 70, 0, 0, 0, 0, 1, :pool, now(), now()) "
            "RETURNING id"
        ), {"slug": slug, "name": name, "d": description, "image": f"packs/{slug}.webp", "price": price,
            "stars": stars, "count": count, "g": guaranteed, "pool": "default"}).scalar_one()
        for rarity, probability in RESIDENT_PROBABILITIES[slug]:
            bind.execute(sa.text(
                "INSERT INTO pack_rarity_probabilities (pack_id, rarity, probability) VALUES (:p, :r, :v)"
            ), {"p": pack_id, "r": rarity, "v": probability})


def upgrade() -> None:
    for value in ("town_house", "town_income", "town_unlock", "town_resident_sale"):
        op.execute(f"ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS '{value}'")

    op.create_table(
        "user_towns",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("income_accrued", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("income_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(24), nullable=True),
        sa.Column("hotel_bought_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "user_town_houses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("district", sa.String(16), nullable=False),
        sa.Column("building_code", sa.String(24), nullable=False),
        sa.Column("price_paid", sa.Integer(), nullable=False),
        sa.Column("bought_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "district", "building_code", name="uq_user_town_houses_building"),
    )
    op.create_index("ix_user_town_houses_user_id", "user_town_houses", ["user_id"])
    op.create_table(
        "town_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("district", sa.String(16), nullable=True),
        sa.Column("building_code", sa.String(24), nullable=True),
        sa.Column("coins_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coins_earned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_town_ledger_user_key"),
    )
    op.create_index("ix_town_ledger_user_id", "town_ledger", ["user_id"])
    op.create_index("ix_town_ledger_created_at", "town_ledger", ["created_at"])

    op.create_table(
        "town_residents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("title", sa.String(64), nullable=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("icon", sa.String(16), nullable=False, server_default="🧑"),
        sa.Column("image_path", sa.String(255), nullable=True),
        sa.Column("rarity", sa.String(16), nullable=False, server_default="common"),
        sa.Column("bonus", sa.String(24), nullable=False, server_default="none"),
        sa.Column("bonus_value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("drop_weight", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_pack_droppable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "user_town_residents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resident_id", sa.Integer(), sa.ForeignKey("town_residents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("copies", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "resident_id", name="uq_user_town_residents_user_resident"),
    )
    op.create_index("ix_user_town_residents_user_id", "user_town_residents", ["user_id"])
    op.create_index("ix_user_town_residents_resident_id", "user_town_residents", ["resident_id"])

    op.add_column("packs", sa.Column("resident_drop_chance", sa.Numeric(5, 4), nullable=False, server_default="0"))
    op.add_column("pack_opening_cards", sa.Column(
        "user_town_resident_id", sa.Integer(), sa.ForeignKey("user_town_residents.id", ondelete="CASCADE"),
        nullable=True,
    ))
    op.drop_constraint("ck_pack_opening_card_exactly_one_kind", "pack_opening_cards", type_="check")
    op.create_check_constraint("ck_pack_opening_card_exactly_one_kind", "pack_opening_cards", NEW_KIND_CHECK)
    op.add_column("card_offers", sa.Column(
        "resident_id", sa.Integer(), sa.ForeignKey("town_residents.id", ondelete="CASCADE"), nullable=True,
    ))
    op.drop_constraint("ck_card_offers_one_item", "card_offers", type_="check")
    op.create_check_constraint("ck_card_offers_one_item", "card_offers", NEW_OFFER_CHECK)

    op.add_column("game_config", sa.Column("town_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("game_config", sa.Column("town_districts", sa.JSON(), nullable=False, server_default=json.dumps(_DISTRICTS)))
    op.add_column("game_config", sa.Column("town_price_growth_pct", sa.Integer(), nullable=False, server_default="4"))
    op.add_column("game_config", sa.Column("town_income_max_hours", sa.Integer(), nullable=False, server_default="24"))
    for name, default in (("town_unlock_coins", "5000"), ("town_rename_stars", "99"), ("town_hotel_price", "5000"),
                          ("town_hotel_rent_per_100_cards", "30"), ("town_hotel_max_cards", "1000"),
                          ("town_resident_rent", "1"), ("town_resident_bonus_max_pct", "100"),
                          ("town_resident_max_daily_coins", "500")):
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=default))
    op.add_column("game_config", sa.Column("town_residents_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("game_config", sa.Column("town_resident_spare_coins", sa.JSON(), nullable=False,
                                           server_default=json.dumps(_SPARE)))
    op.add_column("game_config", sa.Column("town_decor", sa.JSON(), nullable=False, server_default=json.dumps(_DECOR)))
    _seed_packs(op.get_bind())
    _seed_residents(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM pack_opening_cards WHERE user_town_resident_id IS NOT NULL"))
    bind.execute(sa.text(
        "DELETE FROM packs WHERE slug IN ('residents', 'residents_stars') "
        "AND NOT EXISTS (SELECT 1 FROM pack_openings o WHERE o.pack_id = packs.id)"
    ))
    bind.execute(sa.text("DELETE FROM card_offers WHERE resident_id IS NOT NULL"))
    op.drop_constraint("ck_card_offers_one_item", "card_offers", type_="check")
    op.create_check_constraint("ck_card_offers_one_item", "card_offers", OLD_OFFER_CHECK)
    op.drop_column("card_offers", "resident_id")
    op.drop_constraint("ck_pack_opening_card_exactly_one_kind", "pack_opening_cards", type_="check")
    op.create_check_constraint("ck_pack_opening_card_exactly_one_kind", "pack_opening_cards", OLD_KIND_CHECK)
    op.drop_column("pack_opening_cards", "user_town_resident_id")
    op.drop_column("packs", "resident_drop_chance")
    for name in ("town_decor", "town_resident_spare_coins", "town_residents_enabled", "town_resident_max_daily_coins",
                 "town_resident_bonus_max_pct", "town_resident_rent", "town_hotel_max_cards",
                 "town_hotel_rent_per_100_cards", "town_hotel_price", "town_rename_stars", "town_unlock_coins",
                 "town_income_max_hours", "town_price_growth_pct", "town_districts", "town_enabled"):
        op.drop_column("game_config", name)
    op.drop_index("ix_user_town_residents_resident_id", table_name="user_town_residents")
    op.drop_index("ix_user_town_residents_user_id", table_name="user_town_residents")
    op.drop_table("user_town_residents")
    op.drop_table("town_residents")
    op.drop_index("ix_town_ledger_created_at", table_name="town_ledger")
    op.drop_index("ix_town_ledger_user_id", table_name="town_ledger")
    op.drop_table("town_ledger")
    op.drop_index("ix_user_town_houses_user_id", table_name="user_town_houses")
    op.drop_table("user_town_houses")
    op.drop_table("user_towns")
    # Enum values stay (Postgres cannot drop a single enum value).
