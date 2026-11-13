"""«Лига чемпионов»: Atlético Madrid of the 3 Nov 2026 home loss to Bayern (0:2) —
the starting XI and five substitutes (art in static/players/<rarity>/ucl_atm_*.webp). Ratings follow EA SPORTS
FC 27; rarity by rating: 90+ legendary, 85–89 epic, 80–84 rare, below 80
common. They drop from the regular packs like the rest of the collection.
Jonathan David has no FC 27 Atlético item yet — 82 is our estimate.
Same collection lookup as 0279.

Revision ID: 0283
Revises: 0282
"""
from alembic import op
import sqlalchemy as sa

revision = "0283"
down_revision = "0282"
branch_labels = None
depends_on = None

COLLECTION = "Лига чемпионов"
DESCRIPTION = "Звёзды главного клубного турнира Европы. Собери всю коллекцию — получи награду."
SORT_ORDER = 920
CLUB = "Атлетико Мадрид"
SELL_PRICE = {"common": 10, "rare": 35, "epic": 120, "legendary": 400}

# name, art slug, position, country, rating, attack, defence, rarity, duel style, character trait
PLAYERS = (
    # starting XI
    ("Ян Облак", "oblak", "GK", "Словения", 88, 52, 91, "epic", "reading", "stoic"),
    ("Марк Пубиль", "pubill", "CB", "Испания", 81, 64, 83, "rare", "power", "emotional"),
    ("Робен Ле Норман", "le_normand", "CB", "Испания", 81, 60, 84, "rare", "reading", "stoic"),
    ("Давид Ганцко", "hancko", "CB", "Словакия", 83, 66, 85, "rare", "power", "peacemaker"),
    ("Алехандро Гримальдо", "grimaldo", "LM", "Испания", 85, 86, 72, "epic", "technique", "spark"),
    ("Джулиано Симеоне", "giuliano", "RM", "Аргентина", 82, 82, 70, "rare", "speed", "emotional"),
    ("Пабло Барриос", "barrios", "CM", "Испания", 83, 82, 78, "rare", "technique", "spark"),
    ("Маркос Льоренте", "llorente", "RB", "Испания", 85, 80, 82, "epic", "speed", "stoic"),
    ("Алекс Баэна", "baena", "LM", "Испания", 83, 86, 58, "rare", "technique", "emotional"),
    ("Александер Сёрлот", "sorloth", "ST", "Норвегия", 83, 87, 45, "rare", "power", "peacemaker"),
    ("Хулиан Альварес", "alvarez", "ST", "Аргентина", 86, 89, 55, "epic", "technique", "spark"),
    # substitutes
    ("Коке", "koke", "CM", "Испания", 81, 79, 77, "rare", "reading", "peacemaker"),
    ("Ли Кан Ин", "lee_kang_in", "RW", "Корея", 80, 83, 45, "rare", "technique", "spark"),
    ("Адемола Лукман", "lookman", "ST", "Нигерия", 83, 86, 42, "rare", "speed", "emotional"),
    ("Родриго Мендоса", "rodri_mendoza", "CM", "Испания", 71, 70, 66, "common", "technique", "spark"),
    ("Джонатан Дэвид", "jonathan_david", "ST", "Канада", 82, 86, 40, "rare", "speed", "stoic"),
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
            "image": f"players/{rarity}/ucl_atm_{slug}.webp", "sell": SELL_PRICE[rarity], "collection": collection_id,
            "style": style, "trait": trait,
        })


def downgrade() -> None:
    conn = op.get_bind()
    collection_id = _collection_id(conn)
    if collection_id is None:
        return
    # Only designs nobody owns yet; owned cards stay.
    conn.execute(sa.text(
        "DELETE FROM players p WHERE p.collection_id = :c AND p.image_path LIKE 'players/%/ucl_atm_%' "
        "AND NOT EXISTS (SELECT 1 FROM user_cards uc WHERE uc.player_id = p.id)"
    ), {"c": collection_id})
