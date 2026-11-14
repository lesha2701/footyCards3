"""«Лига чемпионов»: Liverpool of the 4 Nov 2026 away win at Fenerbahçe —
the starting XI and the five substitutes (art in static/players/<rarity>/ucl_*.webp).
Ratings follow EA SPORTS FC 27; rarity by rating: 90+ legendary, 85–89 epic,
80–84 rare, below 80 common. They drop from the regular packs
(is_pack_droppable) like the rest of the collection.

The collection was made in the admin panel, so it is found by name; a
fresh database without it gets a new one.

Revision ID: 0279
Revises: 0278
"""
from alembic import op
import sqlalchemy as sa

revision = "0279"
down_revision = "0278"
branch_labels = None
depends_on = None

COLLECTION = "Лига чемпионов"
DESCRIPTION = "Звёзды главного клубного турнира Европы. Собери всю коллекцию — получи награду."
SORT_ORDER = 920
CLUB = "Ливерпуль"
SELL_PRICE = {"common": 10, "rare": 35, "epic": 120, "legendary": 400}

# name, art slug, position, country, rating, attack, defence, rarity, duel style, character trait
PLAYERS = (
    # starting XI
    ("Алиссон Бекер", "alisson", "GK", "Бразилия", 87, 55, 89, "epic", "reading", "stoic"),
    ("Джо Гомес", "gomez", "CB", "Англия", 79, 66, 81, "common", "reading", "peacemaker"),
    ("Вирджил ван Дейк", "van_dijk", "CB", "Нидерланды", 88, 72, 91, "epic", "power", "stoic"),
    ("Жереми Жаке", "jacquet", "CB", "Франция", 77, 58, 79, "common", "power", "emotional"),
    ("Доминик Собослаи", "szoboszlai", "CAM", "Венгрия", 86, 86, 75, "epic", "power", "spark"),
    ("Алексис Мак Аллистер", "mac_allister", "CM", "Аргентина", 84, 83, 78, "rare", "reading", "peacemaker"),
    ("Костас Цимикас", "tsimikas", "LB", "Греция", 76, 72, 75, "common", "speed", "emotional"),
    ("Виктор Муньос", "munoz", "LW", "Испания", 79, 82, 52, "common", "speed", "spark"),
    ("Брэдли Барколя", "barcola", "LW", "Франция", 85, 87, 45, "epic", "speed", "spark"),
    ("Трей Ньони", "nyoni", "CM", "Англия", 67, 66, 60, "common", "technique", "spark"),
    ("Рио Нгумоа", "ngumoha", "LW", "Англия", 75, 79, 40, "common", "speed", "spark"),
    # substitutes
    ("Флориан Вирц", "wirtz", "CAM", "Германия", 86, 87, 58, "epic", "technique", "stoic"),
    ("Александер Исак", "isak", "ST", "Швеция", 86, 88, 45, "epic", "technique", "stoic"),
    ("Коди Гакпо", "gakpo", "LW", "Нидерланды", 82, 84, 50, "rare", "technique", "peacemaker"),
    ("Милош Керкез", "kerkez", "LB", "Венгрия", 81, 76, 79, "rare", "speed", "emotional"),
    ("Льюис Кумас", "koumas", "LW", "Уэльс", 69, 72, 38, "common", "speed", "spark"),
)


def _split(display_name: str) -> tuple[str, str]:
    parts = display_name.split(maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else parts[0]


def _collection_id(conn):
    return conn.execute(sa.text(
        "SELECT id FROM card_collections WHERE lower(name) LIKE '%лига чемпионов%' ORDER BY id LIMIT 1"
    )).scalar()


def upgrade() -> None:
    conn = op.get_bind()
    collection_id = _collection_id(conn)
    if collection_id is None:
        collection_id = conn.execute(sa.text(
            "INSERT INTO card_collections (name, description, is_active, sort_order, reward_coins, "
            "created_at, updated_at) VALUES (:n, :d, true, :sort, 0, now(), now()) RETURNING id"
        ), {"n": COLLECTION, "d": DESCRIPTION, "sort": SORT_ORDER}).scalar_one()

    for name, slug, position, country, rating, attack, defence, rarity, style, trait in PLAYERS:
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
            "rarity": rarity, "country": country, "club": CLUB, "position": position,
            "image": f"players/{rarity}/ucl_{slug}.webp", "sell": SELL_PRICE[rarity], "collection": collection_id,
            "style": style, "trait": trait,
        })


def downgrade() -> None:
    conn = op.get_bind()
    collection_id = _collection_id(conn)
    if collection_id is None:
        return
    # Only designs nobody owns yet; owned cards stay.
    conn.execute(sa.text(
        "DELETE FROM players p WHERE p.collection_id = :c AND p.image_path LIKE 'players/%/ucl_%' "
        "AND NOT EXISTS (SELECT 1 FROM user_cards uc WHERE uc.player_id = p.id)"
    ), {"c": collection_id})
