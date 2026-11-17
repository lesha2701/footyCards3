"""«Лига чемпионов»: Arsenal of the 4 Nov 2026 away win at Slavia Prague (2:1) —
the starting XI and five substitutes (art in static/players/<rarity>/ucl_ars_*.webp). Ratings follow EA SPORTS
FC 27; rarity by rating: 90+ legendary, 85–89 epic, 80–84 rare, below 80
common. They drop from the regular packs like the rest of the collection.
Max Dowman has no FC 27 item yet — his rating is our estimate.
Same collection lookup as 0279.

Revision ID: 0287
Revises: 0286
"""
from alembic import op
import sqlalchemy as sa

revision = "0287"
down_revision = "0286"
branch_labels = None
depends_on = None

COLLECTION = "Лига чемпионов"
DESCRIPTION = "Звёзды главного клубного турнира Европы. Собери всю коллекцию — получи награду."
SORT_ORDER = 920
CLUB = "Арсенал"
SELL_PRICE = {"common": 10, "rare": 35, "epic": 120, "legendary": 400}

# name, art slug, position, country, rating, attack, defence, rarity, duel style, character trait
PLAYERS = (
    # starting XI
    ("Давид Райя", "raya", "GK", "Испания", 88, 55, 90, "epic", "reading", "stoic"),
    ("Бен Уайт", "white", "RB", "Англия", 81, 74, 81, "rare", "reading", "peacemaker"),
    ("Эзри Конса", "konsa", "CB", "Англия", 84, 64, 86, "rare", "speed", "stoic"),
    ("Габриэл Магальяйнс", "gabriel", "CB", "Бразилия", 89, 70, 91, "epic", "power", "emotional"),
    ("Пьеро Инкапье", "hincapie", "LB", "Эквадор", 84, 74, 85, "rare", "speed", "spark"),
    ("Мартин Субименди", "zubimendi", "CDM", "Испания", 84, 78, 85, "rare", "reading", "stoic"),
    ("Деклан Райс", "rice", "CDM", "Англия", 88, 84, 87, "epic", "power", "spark"),
    ("Нони Мадуэке", "madueke", "RW", "Англия", 80, 84, 42, "rare", "speed", "emotional"),
    ("Микель Мерино", "merino", "CM", "Испания", 83, 82, 80, "rare", "reading", "stoic"),
    ("Эберечи Эзе", "eze", "CAM", "Англия", 84, 87, 55, "rare", "technique", "spark"),
    ("Виктор Дьёкереш", "gyokeres", "ST", "Швеция", 86, 90, 48, "epic", "power", "grumbler"),
    # substitutes
    ("Кристиан Москера", "mosquera", "CB", "Испания", 78, 58, 81, "common", "speed", "peacemaker"),
    ("Христос Цолис", "tzolis", "LW", "Греция", 82, 86, 40, "rare", "technique", "emotional"),
    ("Юрриен Тимбер", "timber", "RB", "Нидерланды", 84, 78, 84, "rare", "speed", "spark"),
    ("Мартин Эдегор", "odegaard", "CM", "Норвегия", 86, 88, 65, "epic", "technique", "peacemaker"),
    ("Макс Дауман", "dowman", "CAM", "Англия", 68, 73, 45, "common", "technique", "spark"),
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
            "image": f"players/{rarity}/ucl_ars_{slug}.webp", "sell": SELL_PRICE[rarity], "collection": collection_id,
            "style": style, "trait": trait,
        })


def downgrade() -> None:
    conn = op.get_bind()
    collection_id = _collection_id(conn)
    if collection_id is None:
        return
    # Only designs nobody owns yet; owned cards stay.
    conn.execute(sa.text(
        "DELETE FROM players p WHERE p.collection_id = :c AND p.image_path LIKE 'players/%/ucl_ars_%' "
        "AND NOT EXISTS (SELECT 1 FROM user_cards uc WHERE uc.player_id = p.id)"
    ), {"c": collection_id})
