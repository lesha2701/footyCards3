"""«Лига чемпионов»: Manchester City — the starting XI and five substitutes
(art in static/players/<rarity>/ucl_mci_*.webp). Ratings follow EA SPORTS
FC 27; rarity by rating: 90+ legendary, 85–89 epic, 80–84 rare, below 80
common. They drop from the regular packs like the rest of the collection.
Same collection lookup as 0279.

Revision ID: 0280
Revises: 0279
"""
from alembic import op
import sqlalchemy as sa

revision = "0280"
down_revision = "0279"
branch_labels = None
depends_on = None

COLLECTION = "Лига чемпионов"
DESCRIPTION = "Звёзды главного клубного турнира Европы. Собери всю коллекцию — получи награду."
SORT_ORDER = 920
CLUB = "Манчестер Сити"
SELL_PRICE = {"common": 10, "rare": 35, "epic": 120, "legendary": 400}

# name, art slug, position, country, rating, attack, defence, rarity, duel style, character trait
PLAYERS = (
    # starting XI
    ("Джанлуиджи Доннарумма", "donnarumma", "GK", "Италия", 89, 55, 91, "epic", "reading", "stoic"),
    ("Матеуш Нунеш", "nunes", "RB", "Португалия", 83, 78, 80, "rare", "speed", "emotional"),
    ("Абдукодир Хусанов", "khusanov", "CB", "Узбекистан", 82, 62, 84, "rare", "speed", "spark"),
    ("Марк Гехи", "guehi", "CB", "Англия", 85, 64, 87, "epic", "reading", "stoic"),
    ("Нико О’Райли", "oreilly", "LB", "Англия", 83, 80, 79, "rare", "technique", "peacemaker"),
    ("Эллиот Андерсон", "anderson", "CDM", "Англия", 84, 78, 83, "rare", "power", "stoic"),
    ("Энцо Фернандес", "enzo_fernandez", "CM", "Аргентина", 86, 84, 78, "epic", "reading", "emotional"),
    ("Илиман Ндиайе", "ndiaye", "LW", "Сенегал", 82, 85, 45, "rare", "technique", "spark"),
    ("Райан Шерки", "cherki", "RW", "Франция", 86, 89, 45, "epic", "technique", "emotional"),
    ("Фил Фоден", "foden", "CAM", "Англия", 84, 86, 58, "rare", "technique", "peacemaker"),
    ("Эрлинг Холанд", "haaland", "ST", "Норвегия", 91, 95, 50, "legendary", "power", "spark"),
    # substitutes
    ("Жереми Доку", "doku", "LW", "Бельгия", 84, 86, 42, "rare", "speed", "spark"),
    ("Рубен Диаш", "ruben_dias", "CB", "Португалия", 87, 65, 89, "epic", "power", "grumbler"),
    ("Матео Ковачич", "kovacic", "CM", "Хорватия", 81, 79, 76, "rare", "technique", "peacemaker"),
    ("Айюб Буадди", "bouaddi", "CDM", "Франция", 80, 74, 80, "rare", "reading", "stoic"),
    ("Аллан Элиас", "allan_elias", "CM", "Бразилия", 70, 70, 64, "common", "technique", "spark"),
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
            "image": f"players/{rarity}/ucl_mci_{slug}.webp", "sell": SELL_PRICE[rarity], "collection": collection_id,
            "style": style, "trait": trait,
        })


def downgrade() -> None:
    conn = op.get_bind()
    collection_id = _collection_id(conn)
    if collection_id is None:
        return
    # Only designs nobody owns yet; owned cards stay.
    conn.execute(sa.text(
        "DELETE FROM players p WHERE p.collection_id = :c AND p.image_path LIKE 'players/%/ucl_mci_%' "
        "AND NOT EXISTS (SELECT 1 FROM user_cards uc WHERE uc.player_id = p.id)"
    ), {"c": collection_id})
