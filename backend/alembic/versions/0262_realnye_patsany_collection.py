"""The «Реальные Пацаны» collection: 14 footballers, 2 coaches, 2 Muses and a
stadium (art in static/). No pack of its own: everything drops from the
regular packs (is_pack_droppable), the Muses from the «Музы» pack.

Revision ID: 0262
Revises: 0261
"""
from alembic import op
import sqlalchemy as sa

revision = "0262"
down_revision = "0261"
branch_labels = None
depends_on = None

COLLECTION = "Реальные Пацаны"
DESCRIPTION = "Звёзды вернулись на район: панельки, гаражи и футбол до темноты. Собери весь двор — получи награду."
COVER = "card_collections/realnye-patsany.webp"
REWARD_COINS = 5000
SORT_ORDER = 910
SELL_PRICE = {"rare": 35, "epic": 120, "legendary": 400}
COACH_SELL_PRICE = {"epic": 200, "legendary": 500}

# name, art slug, position, country, club, rating, attack, defence, rarity, duel style, character trait
PLAYERS = (
    ("Уэйн Руни", "rooney", "ST", "Англия", "Манчестер Юнайтед", 92, 95, 60, "legendary", "power", "emotional"),
    ("Фернандо Редондо", "redondo", "CDM", "Аргентина", "Реал Мадрид", 91, 74, 93, "legendary", "reading", "stoic"),
    ("Пол Гаскойн", "gascoigne", "CM", "Англия", "Тоттенхэм", 90, 91, 76, "legendary", "technique", "emotional"),
    ("Роже Милла", "milla", "ST", "Камерун", "Монпелье", 90, 92, 50, "legendary", "technique", "spark"),
    ("Синиша Михайлович", "mihajlovic", "CB", "Сербия", "Лацио", 88, 72, 90, "epic", "power", "grumbler"),
    ("Альваро Рекоба", "recoba", "CAM", "Уругвай", "Интер", 87, 90, 55, "epic", "technique", "peacemaker"),
    ("Хвича Кварацхелия", "kvaratskhelia", "LW", "Грузия", "ПСЖ", 87, 89, 58, "epic", "speed", "spark"),
    ("Скотт Мактоминей", "mctominay", "CM", "Шотландия", "Наполи", 86, 86, 80, "epic", "power", "stoic"),
    ("Аилтон", "ailton", "ST", "Бразилия", "Вердер", 86, 89, 48, "epic", "speed", "spark"),
    ("Антонио Кассано", "cassano", "ST", "Италия", "Сампдория", 85, 88, 50, "epic", "technique", "grumbler"),
    ("Ян Коллер", "koller", "ST", "Чехия", "Боруссия Дортмунд", 85, 86, 60, "epic", "power", "peacemaker"),
    ("Джордан Пикфорд", "pickford", "GK", "Англия", "Эвертон", 84, 54, 86, "epic", "reading", "emotional"),
    ("Микель Мерино", "merino", "CM", "Испания", "Арсенал", 84, 80, 82, "epic", "reading", "stoic"),
    ("Алексей Батраков", "batrakov", "CAM", "Россия", "Локомотив", 78, 80, 56, "rare", "technique", "emotional"),
)

# name, art, country, rarity, boosts. Magnitude = base × tier
# (coach_service.magnitude_for): legendary ×4, epic ×3.
COACHES = (
    ("Марсело Бьелса", "coaches/legendary/bielsa.webp", "Аргентина", "legendary",
     (("attack_wing", 8), ("midfield_control", 8), ("opp_defence", 4))),
    ("Феликс Магат", "coaches/epic/magath.webp", "Германия", "epic",
     (("defence_central", 6), ("squad_stability", 3), ("defensive_discipline", 0.03))),
)

# name, rarity, art, sell price, boost_pct, opp_malus
STADIUM = ("Дворовая арена", "epic", "stadiums/epic/dvorovaya_arena.webp", 200, 0, 3)

# name, title, description, icon, art, rarity, effect, value, sort
MUSES = (
    ("Ирина Шейк", "модель из Еманжелинска",
     "Заехала во двор на чёрной девятке — и весь район заиграл на класс выше.", "🖤",
     "muses/realnye-patsany/shayk.webp", "legendary", "match_rating", 3, 1),
    ("Барбара Палвин", "модель из Будапешта",
     "Смотрит дворовый матч со скамейки — при ней на тренировках никто не халтурит.", "🌇",
     "muses/realnye-patsany/palvin.webp", "epic", "xp_bonus_pct", 10, 2),
)


def _split(display_name: str) -> tuple[str, str]:
    parts = display_name.split(maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else parts[0]


def upgrade() -> None:
    conn = op.get_bind()
    collection_id = conn.execute(sa.text("SELECT id FROM card_collections WHERE name = :n"), {"n": COLLECTION}).scalar()
    if collection_id is None:
        collection_id = conn.execute(sa.text(
            "INSERT INTO card_collections (name, description, image_path, is_active, sort_order, reward_coins, "
            "created_at, updated_at) VALUES (:n, :d, :img, true, :sort, :coins, now(), now()) RETURNING id"
        ), {"n": COLLECTION, "d": DESCRIPTION, "img": COVER, "sort": SORT_ORDER, "coins": REWARD_COINS}).scalar_one()

    for name, slug, position, country, club, rating, attack, defence, rarity, style, trait in PLAYERS:
        if conn.execute(sa.text(
            "SELECT 1 FROM players WHERE display_name = :n AND collection_id = :c"
        ), {"n": name, "c": collection_id}).first():
            continue
        first, last = _split(name)
        conn.execute(sa.text(
            "INSERT INTO players (first_name, last_name, display_name, rating, attack_rating, defense_rating, rarity, "
            "country, club, position, image_path, quick_sell_price, is_active, is_pack_droppable, collection_id, "
            "duel_style, character_trait, next_serial_number, next_club_serial_number, created_at, updated_at) "
            "VALUES (:first, :last, :name, :rating, :atk, :dfn, CAST(:rarity AS rarity_enum), :country, :club, "
            "CAST(:position AS position_enum), :image, :sell, true, true, :collection, :style, :trait, 1, 1, now(), now())"
        ), {
            "first": first, "last": last, "name": name, "rating": rating, "atk": attack, "dfn": defence,
            "rarity": rarity, "country": country, "club": club, "position": position,
            "image": f"players/{rarity}/rp_{slug}.webp", "sell": SELL_PRICE[rarity], "collection": collection_id,
            "style": style, "trait": trait,
        })

    for name, image, country, rarity, boosts in COACHES:
        if conn.execute(sa.text("SELECT 1 FROM coaches WHERE display_name = :n"), {"n": name}).first():
            continue
        coach_id = conn.execute(sa.text(
            "INSERT INTO coaches (display_name, rarity, image_path, country, quick_sell_price, is_active, "
            "is_pack_droppable, next_serial_number, next_club_serial_number, collection_id, created_at, updated_at) "
            "VALUES (:n, CAST(:rarity AS rarity_enum), :img, :country, :sell, true, true, 1, 1, :c, now(), now()) "
            "RETURNING id"
        ), {
            "n": name, "rarity": rarity, "img": image, "country": country,
            "sell": COACH_SELL_PRICE[rarity], "c": collection_id,
        }).scalar_one()
        for boost_type, magnitude in boosts:
            conn.execute(sa.text(
                "INSERT INTO coach_boosts (coach_id, boost_type, magnitude) "
                "VALUES (:coach, CAST(:type AS coach_boost_type_enum), :m)"
            ), {"coach": coach_id, "type": boost_type, "m": magnitude})

    name, rarity, image, sell, boost_pct, opp_malus = STADIUM
    if not conn.execute(sa.text("SELECT 1 FROM stadiums WHERE display_name = :n"), {"n": name}).first():
        conn.execute(sa.text(
            "INSERT INTO stadiums (display_name, rarity, image_path, club, quick_sell_price, is_active, "
            "is_pack_droppable, next_serial_number, next_club_serial_number, boost_pct, opp_malus, collection_id, "
            "created_at, updated_at) VALUES (:n, CAST(:rarity AS rarity_enum), :img, NULL, :sell, true, true, 1, 1, "
            ":boost, :malus, :c, now(), now())"
        ), {"n": name, "rarity": rarity, "img": image, "sell": sell, "boost": boost_pct, "malus": opp_malus, "c": collection_id})

    # Their own line in the «Музы» gallery, like «Звёздные музы».
    line_id = conn.execute(sa.text("SELECT id FROM muse_collections WHERE name = :n"), {"n": COLLECTION}).scalar()
    if line_id is None:
        line_id = conn.execute(sa.text(
            "INSERT INTO muse_collections (name, description, is_active, sort_order, created_at, updated_at) "
            "VALUES (:n, :d, true, 100, now(), now()) RETURNING id"
        ), {"n": COLLECTION, "d": "Музы двора из коллекции «Реальные Пацаны»."}).scalar_one()
    for name, title, description, icon, image, rarity, effect, value, sort in MUSES:
        if conn.execute(sa.text("SELECT 1 FROM muses WHERE name = :n"), {"n": name}).first():
            continue
        conn.execute(sa.text(
            "INSERT INTO muses (collection_id, card_collection_id, name, title, description, icon, image_path, rarity, "
            "effect, effect_value, drop_weight, is_pack_droppable, is_active, sort_order, created_at, updated_at) "
            "VALUES (:line, :c, :n, :title, :descr, :icon, :img, :rarity, :effect, :value, 100, true, true, :sort, "
            "now(), now())"
        ), {
            "line": line_id, "c": collection_id, "n": name, "title": title, "descr": description, "icon": icon,
            "img": image, "rarity": rarity, "effect": effect, "value": value, "sort": sort,
        })


def downgrade() -> None:
    conn = op.get_bind()
    collection_id = conn.execute(sa.text("SELECT id FROM card_collections WHERE name = :n"), {"n": COLLECTION}).scalar()
    if collection_id is None:
        return
    # Only what nobody has received yet: a dropped card must stay.
    conn.execute(sa.text(
        "DELETE FROM players WHERE collection_id = :c AND next_serial_number = 1"
    ), {"c": collection_id})
    conn.execute(sa.text(
        "DELETE FROM coach_boosts WHERE coach_id IN "
        "(SELECT id FROM coaches WHERE collection_id = :c AND next_serial_number = 1)"
    ), {"c": collection_id})
    conn.execute(sa.text(
        "DELETE FROM coaches WHERE collection_id = :c AND next_serial_number = 1"
    ), {"c": collection_id})
    conn.execute(sa.text(
        "DELETE FROM stadiums WHERE collection_id = :c AND next_serial_number = 1"
    ), {"c": collection_id})
    conn.execute(sa.text(
        "DELETE FROM muses WHERE card_collection_id = :c AND id NOT IN (SELECT muse_id FROM user_muses)"
    ), {"c": collection_id})
    conn.execute(sa.text(
        "DELETE FROM muse_collections WHERE name = :n AND id NOT IN "
        "(SELECT collection_id FROM muses WHERE collection_id IS NOT NULL)"
    ), {"n": COLLECTION})
    for table, column in (
        ("players", "collection_id"), ("coaches", "collection_id"),
        ("stadiums", "collection_id"), ("muses", "card_collection_id"),
    ):
        if conn.execute(sa.text(f"SELECT 1 FROM {table} WHERE {column} = :c LIMIT 1"), {"c": collection_id}).first():
            return
    conn.execute(sa.text("DELETE FROM card_collections WHERE id = :c"), {"c": collection_id})
