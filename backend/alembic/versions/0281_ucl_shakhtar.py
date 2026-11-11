"""«Лига чемпионов»: Shakhtar Donetsk — the starting XI and five substitutes
(art in static/players/<rarity>/ucl_shk_*.webp). Ratings follow EA SPORTS
FC 27; rarity by rating: 90+ legendary, 85–89 epic, 80–84 rare, below 80
common. They drop from the regular packs like the rest of the collection.
All of them are below 80, so all common. Same collection lookup as 0279.

Revision ID: 0281
Revises: 0280
"""
from alembic import op
import sqlalchemy as sa

revision = "0281"
down_revision = "0280"
branch_labels = None
depends_on = None

COLLECTION = "Лига чемпионов"
DESCRIPTION = "Звёзды главного клубного турнира Европы. Собери всю коллекцию — получи награду."
SORT_ORDER = 920
CLUB = "Шахтёр Донецк"
SELL_PRICE = {"common": 10, "rare": 35, "epic": 120, "legendary": 400}

# name, art slug, position, country, rating, attack, defence, rarity, duel style, character trait
PLAYERS = (
    # starting XI
    ("Дмитрий Ризнык", "riznyk", "GK", "Украина", 74, 45, 77, "common", "reading", "stoic"),
    ("Винисиус Тобиас", "tobias", "RB", "Бразилия", 71, 68, 70, "common", "speed", "emotional"),
    ("Валерий Бондарь", "bondar", "CB", "Украина", 75, 55, 78, "common", "reading", "peacemaker"),
    ("Николай Матвиенко", "matviienko", "CB", "Украина", 77, 60, 80, "common", "power", "stoic"),
    ("Педро Энрике", "pedro_henrique", "LB", "Бразилия", 72, 68, 70, "common", "speed", "spark"),
    ("Егор Назарына", "nazaryna", "CM", "Украина", 69, 67, 66, "common", "reading", "grumbler"),
    ("Алиссон Сантана", "alisson_santana", "RW", "Бразилия", 70, 75, 38, "common", "speed", "spark"),
    ("Олег Очеретько", "ocheretko", "CAM", "Украина", 66, 70, 55, "common", "technique", "peacemaker"),
    ("Марлон Гомес", "marlon_gomes", "CM", "Бразилия", 70, 70, 66, "common", "technique", "emotional"),
    ("Глейкер Мендоса", "mendoza", "LW", "Венесуэла", 65, 70, 35, "common", "speed", "spark"),
    ("Кауа Элиас", "kaua_elias", "ST", "Бразилия", 71, 76, 38, "common", "power", "emotional"),
    # substitutes
    ("Ньюэртон", "newerton", "LW", "Бразилия", 70, 75, 38, "common", "speed", "spark"),
    ("Исаке Силва", "isaque", "CAM", "Бразилия", 66, 71, 50, "common", "technique", "peacemaker"),
    ("Лассина Траоре", "traore", "ST", "Буркина-Фасо", 71, 76, 40, "common", "power", "grumbler"),
    ("Лукас Феррейра", "lucas_ferreira", "RW", "Бразилия", 67, 72, 38, "common", "speed", "spark"),
    ("Лука Мейреллеш", "meirelles", "ST", "Бразилия", 66, 72, 36, "common", "power", "emotional"),
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
            "image": f"players/{rarity}/ucl_shk_{slug}.webp", "sell": SELL_PRICE[rarity], "collection": collection_id,
            "style": style, "trait": trait,
        })


def downgrade() -> None:
    conn = op.get_bind()
    collection_id = _collection_id(conn)
    if collection_id is None:
        return
    # Only designs nobody owns yet; owned cards stay.
    conn.execute(sa.text(
        "DELETE FROM players p WHERE p.collection_id = :c AND p.image_path LIKE 'players/%/ucl_shk_%' "
        "AND NOT EXISTS (SELECT 1 FROM user_cards uc WHERE uc.player_id = p.id)"
    ), {"c": collection_id})
