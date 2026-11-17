"""«Лига чемпионов»: Inter of the 3 Nov 2026 away win at Feyenoord (3:0) —
the starting XI and five substitutes (art in static/players/<rarity>/ucl_int_*.webp). Ratings follow EA SPORTS
FC 27; rarity by rating: 90+ legendary, 85–89 epic, 80–84 rare, below 80
common. They drop from the regular packs like the rest of the collection.
EA lists Inter as «Lombardia FC». Same collection lookup as 0279.

Revision ID: 0288
Revises: 0287
"""
from alembic import op
import sqlalchemy as sa

revision = "0288"
down_revision = "0287"
branch_labels = None
depends_on = None

COLLECTION = "Лига чемпионов"
DESCRIPTION = "Звёзды главного клубного турнира Европы. Собери всю коллекцию — получи награду."
SORT_ORDER = 920
CLUB = "Интер"
SELL_PRICE = {"common": 10, "rare": 35, "epic": 120, "legendary": 400}

# name, art slug, position, country, rating, attack, defence, rarity, duel style, character trait
PLAYERS = (
    # starting XI
    ("Жозеп Мартинес", "josep_martinez", "GK", "Испания", 76, 45, 79, "common", "reading", "peacemaker"),
    ("Янн Биссек", "bisseck", "CB", "Германия", 78, 60, 81, "common", "power", "spark"),
    ("Мануэль Аканджи", "akanji", "CB", "Швейцария", 83, 66, 85, "rare", "reading", "stoic"),
    ("Карлос Аугусто", "carlos_augusto", "LB", "Бразилия", 80, 74, 79, "rare", "speed", "peacemaker"),
    ("Джед Спенс", "spence", "RB", "Англия", 80, 76, 77, "rare", "speed", "emotional"),
    ("Николо Барелла", "barella", "CM", "Италия", 87, 86, 80, "epic", "power", "emotional"),
    ("Хакан Чалханоглу", "calhanoglu", "CDM", "Турция", 85, 84, 80, "epic", "technique", "stoic"),
    ("Пётр Зелиньский", "zielinski", "CM", "Польша", 82, 82, 74, "rare", "technique", "peacemaker"),
    ("Федерико Димарко", "dimarco", "LB", "Италия", 86, 85, 80, "epic", "technique", "spark"),
    ("Франческо Пио Эспозито", "pio_esposito", "ST", "Италия", 77, 82, 40, "common", "power", "spark"),
    ("Маркус Тюрам", "thuram", "ST", "Франция", 85, 89, 48, "epic", "power", "emotional"),
    # substitutes
    ("Генрих Мхитарян", "mkhitaryan", "CM", "Армения", 81, 81, 74, "rare", "reading", "stoic"),
    ("Анж-Йоан Бонни", "bonny", "ST", "Кот-д'Ивуар", 78, 83, 40, "common", "speed", "spark"),
    ("Петар Сучич", "sucic", "CM", "Хорватия", 78, 78, 72, "common", "technique", "emotional"),
    ("Александар Станкович", "stankovic", "CDM", "Сербия", 76, 70, 76, "common", "reading", "grumbler"),
    ("Бенжамен Павар", "pavard", "CB", "Франция", 80, 64, 82, "rare", "reading", "peacemaker"),
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
            "image": f"players/{rarity}/ucl_int_{slug}.webp", "sell": SELL_PRICE[rarity], "collection": collection_id,
            "style": style, "trait": trait,
        })


def downgrade() -> None:
    conn = op.get_bind()
    collection_id = _collection_id(conn)
    if collection_id is None:
        return
    # Only designs nobody owns yet; owned cards stay.
    conn.execute(sa.text(
        "DELETE FROM players p WHERE p.collection_id = :c AND p.image_path LIKE 'players/%/ucl_int_%' "
        "AND NOT EXISTS (SELECT 1 FROM user_cards uc WHERE uc.player_id = p.id)"
    ), {"c": collection_id})
