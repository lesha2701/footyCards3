"""«Дух Зверя»: a new collection — 18 footballers, each with the spirit
animal behind him (cover static/card_collections/dukh-zverya.webp, art in
static/players/<rarity>/beast_*.webp). Ratings follow EA SPORTS FC 27;
Ronaldinho and Yashin are legends, Lewis Hall and James Trafford have no FC 27
item yet (our estimate). Rarity by rating: 90+ legendary, 85–89 epic, 80–84
rare, below 80 common. Everything drops from the regular packs.

Revision ID: 0303
Revises: 0302
"""
from alembic import op
import sqlalchemy as sa

revision = "0303"
down_revision = "0302"
branch_labels = None
depends_on = None

COLLECTION = "Дух Зверя"
DESCRIPTION = "В каждой звезде живёт зверь: ягуар, волк, орёл, бык… Собери всю стаю — получи награду."
COVER = "card_collections/dukh-zverya.webp"
REWARD_COINS = 5000
SORT_ORDER = 940
SELL_PRICE = {"common": 10, "rare": 35, "epic": 120, "legendary": 400}

# name, art slug, position, country, club, rating, attack, defence, rarity, duel style, character trait
PLAYERS = (
    ("Роналдиньо", "ronaldinho", "CAM", "Бразилия", "Барселона", 93, 96, 50, "legendary", "technique", "spark"),
    ("Федерико Вальверде", "valverde", "CM", "Уругвай", "Реал Мадрид", 87, 86, 80, "epic", "power", "stoic"),
    ("Лев Яшин", "yashin", "GK", "Россия", "Динамо", 91, 55, 94, "legendary", "reading", "stoic"),
    ("Килиан Мбаппе", "mbappe", "ST", "Франция", "Реал Мадрид", 91, 95, 42, "legendary", "speed", "emotional"),
    ("Витинья", "vitinha", "CM", "Португалия", "ПСЖ", 90, 89, 80, "legendary", "technique", "peacemaker"),
    ("Ламин Ямаль", "yamal", "RW", "Испания", "Барселона", 90, 94, 42, "legendary", "technique", "spark"),
    ("Майкл Олисе", "olise", "RW", "Франция", "Бавария", 90, 93, 45, "legendary", "technique", "stoic"),
    ("Эрлинг Холанд", "haaland", "ST", "Норвегия", "Манчестер Сити", 91, 95, 50, "legendary", "power", "spark"),
    ("Родри", "rodri", "CDM", "Испания", "Барселона", 90, 84, 90, "legendary", "reading", "stoic"),
    ("Нуну Мендеш", "nuno_mendes", "LB", "Португалия", "ПСЖ", 89, 84, 87, "epic", "speed", "emotional"),
    ("Жоау Невеш", "joao_neves", "CM", "Португалия", "ПСЖ", 88, 85, 84, "epic", "reading", "spark"),
    ("Джанлуиджи Доннарумма", "donnarumma", "GK", "Италия", "Манчестер Сити", 89, 55, 91, "epic", "reading", "stoic"),
    ("Педри", "pedri", "CM", "Испания", "Барселона", 90, 89, 78, "legendary", "technique", "peacemaker"),
    ("Дин Хёйсен", "huijsen", "CB", "Испания", "Реал Мадрид", 81, 64, 84, "rare", "reading", "stoic"),
    ("Джеймс Траффорд", "trafford", "GK", "Англия", "Манчестер Сити", 78, 48, 81, "common", "reading", "peacemaker"),
    ("Эллиот Андерсон", "anderson", "CDM", "Англия", "Манчестер Сити", 84, 78, 83, "rare", "power", "stoic"),
    ("Льюис Холл", "lewis_hall", "LB", "Англия", "Ньюкасл", 80, 76, 78, "rare", "speed", "spark"),
    ("Марк Кукурелья", "cucurella", "LB", "Испания", "Реал Мадрид", 86, 80, 86, "epic", "power", "grumbler"),
)


def _split(display_name: str) -> tuple[str, str]:
    parts = display_name.split(maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else parts[0]


def _collection_id(conn):
    return conn.execute(sa.text(
        "SELECT id FROM card_collections WHERE lower(name) LIKE '%мафи%' ORDER BY id LIMIT 1"
    )).scalar()


def _collection_id(conn):
    return conn.execute(sa.text("SELECT id FROM card_collections WHERE name = :n"), {"n": COLLECTION}).scalar()


def upgrade() -> None:
    conn = op.get_bind()
    collection_id = _collection_id(conn)
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
            "image": f"players/{rarity}/beast_{slug}.webp", "sell": SELL_PRICE[rarity], "collection": collection_id,
            "style": style, "trait": trait,
        })


def downgrade() -> None:
    conn = op.get_bind()
    collection_id = _collection_id(conn)
    if collection_id is None:
        return
    # Only designs nobody owns yet; owned cards and the collection stay then.
    conn.execute(sa.text(
        "DELETE FROM players p WHERE p.collection_id = :c AND p.image_path LIKE 'players/%/beast_%' "
        "AND NOT EXISTS (SELECT 1 FROM user_cards uc WHERE uc.player_id = p.id)"
    ), {"c": collection_id})
    conn.execute(sa.text(
        "DELETE FROM card_collections c WHERE c.id = :c AND NOT EXISTS (SELECT 1 FROM players p WHERE p.collection_id = c.id)"
    ), {"c": collection_id})
