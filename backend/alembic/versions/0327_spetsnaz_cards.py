"""«Спецназ»: 18 footballers on a special-forces mission (art in
static/players/<rarity>/spn_*.webp). Peak-career versions (our estimate);
rarity by rating: 90+ legendary, 85–89 epic, 80–84 rare. They drop from the
regular packs.

The collection was made in the admin panel, so it is found by name
(contains «спецназ»); a fresh database without it gets a new one.

Revision ID: 0327
Revises: 0326
"""
from alembic import op
import sqlalchemy as sa

revision = "0327"
down_revision = "0326"
branch_labels = None
depends_on = None

COLLECTION = "Спецназ"
SELL_PRICE = {"common": 10, "rare": 35, "epic": 120, "legendary": 400}

# name, art slug, position, country, club, rating, attack, defence, rarity, duel style, character trait
PLAYERS = (
    ("Хакан Чалханоглу", "calhanoglu", "CDM", "Турция", "Интер", 85, 84, 80, "epic", "technique", "stoic"),
    ("Кевин Де Брёйне", "de_bruyne", "CAM", "Бельгия", "Манчестер Сити", 91, 93, 65, "legendary", "technique", "stoic"),
    ("Дуглас Коста", "douglas_costa", "LW", "Бразилия", "Ювентус", 84, 88, 40, "rare", "speed", "spark"),
    ("Федерико Кьеза", "chiesa", "RW", "Италия", "Ювентус", 84, 87, 50, "rare", "speed", "emotional"),
    ("Джорджо Кьеллини", "chiellini", "CB", "Италия", "Ювентус", 89, 65, 92, "epic", "power", "grumbler"),
    ("Иван Перишич", "perisic", "LW", "Хорватия", "Интер", 84, 85, 65, "rare", "power", "stoic"),
    ("Якуб Блащиковский", "blaszczykowski", "RM", "Польша", "Боруссия Дортмунд", 81, 83, 55, "rare", "speed", "peacemaker"),
    ("Хамес Родригес", "james_rodriguez", "CAM", "Колумбия", "Реал Мадрид", 86, 89, 50, "epic", "technique", "emotional"),
    ("Калиду Кулибали", "koulibaly", "CB", "Сенегал", "Наполи", 88, 64, 91, "epic", "power", "stoic"),
    ("Мартен де Рон", "de_roon", "CDM", "Нидерланды", "Аталанта", 81, 74, 82, "rare", "reading", "grumbler"),
    ("Мемфис Депай", "depay", "ST", "Нидерланды", "Лион", 84, 88, 42, "rare", "technique", "emotional"),
    ("Пауло Дибала", "dybala", "CAM", "Аргентина", "Ювентус", 88, 91, 45, "epic", "technique", "spark"),
    ("Рикарду Карвалью", "carvalho", "CB", "Португалия", "Челси", 87, 62, 90, "epic", "reading", "stoic"),
    ("Рияд Марез", "mahrez", "RW", "Алжир", "Лестер Сити", 86, 89, 45, "epic", "technique", "peacemaker"),
    ("Гави", "gavi", "CM", "Испания", "Барселона", 84, 82, 76, "rare", "power", "emotional"),
    ("Филипп Лам", "lahm", "RB", "Германия", "Бавария", 90, 82, 91, "legendary", "reading", "stoic"),
    ("Нуну Мендеш", "nuno_mendes", "LB", "Португалия", "ПСЖ", 89, 84, 87, "epic", "speed", "emotional"),
    ("Александр Шовковский", "shovkovskyi", "GK", "Украина", "Динамо Киев", 85, 50, 88, "epic", "reading", "stoic"),
)


def _split(display_name: str) -> tuple[str, str]:
    parts = display_name.split(maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else parts[0]




def _split(display_name: str) -> tuple[str, str]:
    parts = display_name.split(maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else parts[0]


def upgrade() -> None:
    conn = op.get_bind()
    collection_id = conn.execute(sa.text(
        "SELECT id FROM card_collections WHERE lower(name) LIKE '%спецназ%' ORDER BY id LIMIT 1"
    )).scalar()
    if collection_id is None:
        collection_id = conn.execute(sa.text(
            "INSERT INTO card_collections (name, description, is_active, sort_order, reward_coins, "
            "created_at, updated_at) VALUES (:n, :d, true, 950, 0, now(), now()) RETURNING id"
        ), {"n": COLLECTION, "d": "Звёзды футбола на спецзадании. Собери весь отряд — получи награду."}).scalar_one()
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
            "image": f"players/{rarity}/spn_{slug}.webp", "sell": SELL_PRICE[rarity], "collection": collection_id,
            "style": style, "trait": trait,
        })


def downgrade() -> None:
    conn = op.get_bind()
    for _name, slug, *_rest, rarity, _style, _trait in PLAYERS:
        conn.execute(sa.text(
            "DELETE FROM players p WHERE p.image_path = :img "
            "AND NOT EXISTS (SELECT 1 FROM user_cards uc WHERE uc.player_id = p.id)"
        ), {"img": f"players/{rarity}/spn_{slug}.webp"})
