"""«Лига чемпионов»: Napoli of the 4 Nov 2026 home loss to Porto (1:4) —
the starting XI and three substitutes (art in static/players/<rarity>/ucl_nap_*.webp). Ratings follow EA SPORTS
FC 27; rarity by rating: 90+ legendary, 85–89 epic, 80–84 rare, below 80
common. They drop from the regular packs like the rest of the collection.
McTominay also has a «Реальные Пацаны» version. Same collection lookup as 0279.

Revision ID: 0289
Revises: 0288
"""
from alembic import op
import sqlalchemy as sa

revision = "0289"
down_revision = "0288"
branch_labels = None
depends_on = None

COLLECTION = "Лига чемпионов"
DESCRIPTION = "Звёзды главного клубного турнира Европы. Собери всю коллекцию — получи награду."
SORT_ORDER = 920
CLUB = "Наполи"
SELL_PRICE = {"common": 10, "rare": 35, "epic": 120, "legendary": 400}

# name, art slug, position, country, rating, attack, defence, rarity, duel style, character trait
PLAYERS = (
    # starting XI
    ("Алекс Мерет", "meret", "GK", "Италия", 81, 50, 84, "rare", "reading", "stoic"),
    ("Сэм Бёкема", "beukema", "CB", "Нидерланды", 78, 60, 81, "common", "power", "peacemaker"),
    ("Амир Ррахмани", "rrahmani", "CB", "Косово", 83, 64, 86, "rare", "reading", "stoic"),
    ("Рафа Марин", "rafa_marin", "CB", "Испания", 76, 58, 79, "common", "speed", "emotional"),
    ("Маттео Политано", "politano", "RW", "Италия", 80, 84, 50, "rare", "technique", "spark"),
    ("Франк Ангисса", "anguissa", "CM", "Камерун", 82, 80, 80, "rare", "power", "grumbler"),
    ("Скотт Мактоминей", "mctominay", "CM", "Шотландия", 86, 86, 80, "epic", "power", "stoic"),
    ("Антонио Вергара", "vergara", "CAM", "Италия", 69, 74, 48, "common", "technique", "spark"),
    ("Билли Гилмор", "gilmour", "CM", "Шотландия", 75, 74, 72, "common", "reading", "peacemaker"),
    ("Расмус Хёйлунн", "hojlund", "ST", "Дания", 78, 83, 42, "common", "power", "emotional"),
    ("Кевин Де Брёйне", "de_bruyne", "CAM", "Бельгия", 85, 89, 60, "epic", "technique", "stoic"),
    # substitutes
    ("Ноа Ланг", "lang", "LM", "Нидерланды", 79, 83, 45, "common", "speed", "grumbler"),
    ("Джоване", "giovane", "ST", "Бразилия", 71, 76, 38, "common", "speed", "spark"),
    ("Лоренцо Лукка", "lucca", "ST", "Италия", 75, 80, 45, "common", "power", "emotional"),
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
            "image": f"players/{rarity}/ucl_nap_{slug}.webp", "sell": SELL_PRICE[rarity], "collection": collection_id,
            "style": style, "trait": trait,
        })


def downgrade() -> None:
    conn = op.get_bind()
    collection_id = _collection_id(conn)
    if collection_id is None:
        return
    # Only designs nobody owns yet; owned cards stay.
    conn.execute(sa.text(
        "DELETE FROM players p WHERE p.collection_id = :c AND p.image_path LIKE 'players/%/ucl_nap_%' "
        "AND NOT EXISTS (SELECT 1 FROM user_cards uc WHERE uc.player_id = p.id)"
    ), {"c": collection_id})
