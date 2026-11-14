"""«Лига чемпионов»: Aston Villa of the 3 Nov 2026 match with Barcelona —
the starting XI and five substitutes (art in static/players/<rarity>/ucl_avl_*.webp). Ratings follow EA SPORTS
FC 27; rarity by rating: 90+ legendary, 85–89 epic, 80–84 rare, below 80
common. They drop from the regular packs like the rest of the collection.
Nicolas Jackson, Leon Goretzka and Ibrahim Mbaye have no FC 27 Villa item
yet — their ratings are our estimate. Same collection lookup as 0279.

Revision ID: 0284
Revises: 0283
"""
from alembic import op
import sqlalchemy as sa

revision = "0284"
down_revision = "0283"
branch_labels = None
depends_on = None

COLLECTION = "Лига чемпионов"
DESCRIPTION = "Звёзды главного клубного турнира Европы. Собери всю коллекцию — получи награду."
SORT_ORDER = 920
CLUB = "Астон Вилла"
SELL_PRICE = {"common": 10, "rare": 35, "epic": 120, "legendary": 400}

# name, art slug, position, country, rating, attack, defence, rarity, duel style, character trait
PLAYERS = (
    # starting XI
    ("Дзион Судзуки", "suzuki", "GK", "Япония", 76, 45, 79, "common", "reading", "stoic"),
    ("Мэтти Кэш", "cash", "RB", "Польша", 81, 76, 80, "rare", "speed", "emotional"),
    ("Виктор Линделёф", "lindelof", "CB", "Швеция", 77, 58, 80, "common", "reading", "stoic"),
    ("Пау Торрес", "pau_torres", "CB", "Испания", 81, 64, 83, "rare", "reading", "peacemaker"),
    ("Ян Матсен", "maatsen", "LB", "Нидерланды", 79, 76, 75, "common", "speed", "spark"),
    ("Бубакар Камара", "kamara", "CDM", "Франция", 84, 74, 85, "rare", "reading", "stoic"),
    ("Жоау Гомес", "joao_gomes", "CDM", "Бразилия", 78, 72, 78, "common", "power", "grumbler"),
    ("Джон Макгинн", "mcginn", "RM", "Шотландия", 83, 84, 74, "rare", "power", "spark"),
    ("Йохан Манзамби", "manzambi", "CM", "Швейцария", 80, 80, 74, "rare", "power", "emotional"),
    ("Эмилиано Буэндия", "buendia", "LM", "Аргентина", 80, 84, 55, "rare", "technique", "emotional"),
    ("Николас Джексон", "jackson", "ST", "Сенегал", 80, 84, 42, "rare", "speed", "grumbler"),
    # substitutes
    ("Леон Горецка", "goretzka", "CM", "Германия", 82, 81, 79, "rare", "power", "peacemaker"),
    ("Ибрагим Мбайе", "mbaye", "LW", "Сенегал", 72, 77, 38, "common", "speed", "spark"),
    ("Росс Баркли", "barkley", "CM", "Англия", 77, 77, 70, "common", "technique", "peacemaker"),
    ("Алиссон да Роша", "alysson", "RM", "Бразилия", 70, 75, 45, "common", "speed", "spark"),
    ("Тэмми Абрахам", "abraham", "ST", "Англия", 77, 82, 40, "common", "power", "emotional"),
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
            "image": f"players/{rarity}/ucl_avl_{slug}.webp", "sell": SELL_PRICE[rarity], "collection": collection_id,
            "style": style, "trait": trait,
        })


def downgrade() -> None:
    conn = op.get_bind()
    collection_id = _collection_id(conn)
    if collection_id is None:
        return
    # Only designs nobody owns yet; owned cards stay.
    conn.execute(sa.text(
        "DELETE FROM players p WHERE p.collection_id = :c AND p.image_path LIKE 'players/%/ucl_avl_%' "
        "AND NOT EXISTS (SELECT 1 FROM user_cards uc WHERE uc.player_id = p.id)"
    ), {"c": collection_id})
