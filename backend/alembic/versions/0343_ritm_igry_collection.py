"""«Ритм игры»: a new collection — 36 footballers (cover
static/card_collections/ritm-igry.webp, art in
static/players/<rarity>/rig_*.webp). Ratings are the admin's call: the main
stat (attack or defence) is at most 2 above the overall, nothing above 95.
Rarity by rating: 90+ legendary, 85–89 epic, 80–84 rare.

Диего Марадона is a numbered edition of 10 copies (Player.edition_size;
packs stop dropping him once they are out) with players.chemistry_shield —
«без отрицательной химии» (added in 0332).

Revision ID: 0343
Revises: 0342
"""
from alembic import op
import sqlalchemy as sa

revision = "0343"
down_revision = "0342"
branch_labels = None
depends_on = None

COLLECTION = "Ритм игры"
DESCRIPTION = "Футбол — это музыка. Собери весь оркестр — получи награду."
COVER = "card_collections/ritm-igry.webp"
REWARD_COINS = 5000
SORT_ORDER = 980
SELL_PRICE = {"common": 10, "rare": 35, "epic": 120, "legendary": 400}

# name, art slug, position, country, club, rating, attack, defence
PLAYERS = (
    ("Диего Марадона", "maradona", "CAM", "Аргентина", "Наполи", 95, 95, 75),
    ("Джанлуиджи Буффон", "buffon", "GK", "Италия", "Ювентус", 94, 30, 95),
    ("Роберто Баджо", "baggio", "CAM", "Италия", "Ювентус", 94, 95, 50),
    ("Джордж Веа", "weah", "ST", "Либерия", "Милан", 93, 95, 50),
    ("Златан Ибрагимович", "ibrahimovic", "ST", "Швеция", "Милан", 93, 95, 52),
    ("Ламин Ямаль", "yamal", "RW", "Испания", "Барселона", 92, 94, 45),
    ("Павел Недвед", "nedved", "LM", "Чехия", "Ювентус", 92, 94, 70),
    ("Серхио Рамос", "ramos", "CB", "Испания", "Реал Мадрид", 92, 70, 94),
    ("Хуан Роман Рикельме", "riquelme", "CAM", "Аргентина", "Бока Хуниорс", 91, 93, 50),
    ("Кларенс Зеедорф", "seedorf", "CM", "Нидерланды", "Милан", 90, 90, 86),
    ("Майкл Олисе", "olise", "RW", "Франция", "Бавария", 90, 92, 48),
    ("Мохамед Салах", "salah", "RW", "Египет", "Ливерпуль", 90, 92, 50),
    ("Гаиска Мендьета", "mendieta", "CM", "Испания", "Валенсия", 88, 89, 80),
    ("Джей-Джей Окоча", "okocha", "CAM", "Нигерия", "ПСЖ", 88, 90, 55),
    ("Димитар Бербатов", "berbatov", "ST", "Болгария", "Манчестер Юнайтед", 88, 90, 45),
    ("Жоау Невеш", "neves", "CM", "Португалия", "ПСЖ", 88, 86, 88),
    ("Марек Гамшик", "hamsik", "CM", "Словакия", "Наполи", 88, 89, 72),
    ("Антуан Гризманн", "griezmann", "CAM", "Франция", "Атлетико Мадрид", 87, 89, 62),
    ("Санти Касорла", "cazorla", "CM", "Испания", "Арсенал", 87, 88, 68),
    ("Сон Хын Мин", "son", "LW", "Южная Корея", "Тоттенхэм", 87, 89, 50),
    ("Денилсон", "denilson", "LW", "Бразилия", "Бетис", 86, 88, 45),
    ("Кевин Де Брёйне", "de_bruyne", "CAM", "Бельгия", "Наполи", 86, 88, 64),
    ("Нико Уильямс", "nico_williams", "LW", "Испания", "Атлетик", 86, 88, 45),
    ("Рикарду Куарежма", "quaresma", "RW", "Португалия", "Порту", 86, 88, 42),
    ("Томаш Росицки", "rosicky", "CM", "Чехия", "Арсенал", 86, 87, 70),
    ("Федерико Димарко", "dimarco", "LB", "Италия", "Интер", 86, 87, 84),
    ("Хидэтоси Наката", "nakata", "CAM", "Япония", "Рома", 86, 88, 62),
    ("Тиджани Рейндерс", "reijnders", "CM", "Нидерланды", "Манчестер Сити", 85, 86, 78),
    ("Алекс Баэна", "baena", "LM", "Испания", "Атлетико Мадрид", 84, 86, 60),
    ("Брайан Мбемо", "mbeumo", "RM", "Камерун", "Манчестер Юнайтед", 84, 86, 50),
    ("Джек Грилиш", "grealish", "LW", "Англия", "Эвертон", 84, 86, 55),
    ("Морган Роджерс", "rogers", "CAM", "Англия", "Астон Вилла", 84, 86, 60),
    ("Эберечи Эзе", "eze", "CAM", "Англия", "Арсенал", 84, 86, 55),
    ("Джеймс Мэддисон", "maddison", "CAM", "Англия", "Тоттенхэм", 83, 85, 58),
    ("Такэфуса Кубо", "kubo", "RW", "Япония", "Реал Сосьедад", 83, 85, 50),
    ("Алекс Ивоби", "iwobi", "CAM", "Нигерия", "Фулхэм", 80, 82, 62),
)

# slug -> (edition_size, chemistry_shield)
SPECIAL = {"maradona": (10, True)}


def _rarity(rating: int) -> str:
    return "legendary" if rating >= 90 else "epic" if rating >= 85 else "rare" if rating >= 80 else "common"


def _split(display_name: str) -> tuple[str, str]:
    parts = display_name.split(maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else parts[0]


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

    for name, slug, position, country, club, rating, attack, defence in PLAYERS:
        assert max(rating, attack, defence) <= 95 and max(attack, defence) <= rating + 2, slug
        if conn.execute(sa.text(
            "SELECT 1 FROM players WHERE display_name = :n AND collection_id = :c"
        ), {"n": name, "c": collection_id}).first():
            continue
        rarity = _rarity(rating)
        edition, shield = SPECIAL.get(slug, (None, False))
        first, last = _split(name)
        conn.execute(sa.text(
            "INSERT INTO players (first_name, last_name, display_name, rating, attack_rating, defense_rating, rarity, "
            "country, club, position, image_path, quick_sell_price, is_active, is_pack_droppable, collection_id, "
            "edition_size, chemistry_shield, next_serial_number, next_club_serial_number, created_at, updated_at) "
            "VALUES (:first, :last, :name, :rating, :atk, :dfn, CAST(:rarity AS rarity_enum), :country, :club, "
            "CAST(:position AS position_enum), :image, :sell, true, true, :collection, :edition, :shield, 1, 1, "
            "now(), now())"
        ), {
            "first": first, "last": last, "name": name, "rating": rating, "atk": attack, "dfn": defence,
            "rarity": rarity, "country": country, "club": club, "position": position,
            "image": f"players/{rarity}/rig_{slug}.webp", "sell": SELL_PRICE[rarity], "collection": collection_id,
            "edition": edition, "shield": shield,
        })


def downgrade() -> None:
    conn = op.get_bind()
    collection_id = _collection_id(conn)
    if collection_id is not None:
        # Only designs nobody owns yet; owned cards and the collection stay then.
        conn.execute(sa.text(
            "DELETE FROM players p WHERE p.collection_id = :c AND p.image_path LIKE 'players/%/rig_%' "
            "AND NOT EXISTS (SELECT 1 FROM user_cards uc WHERE uc.player_id = p.id)"
        ), {"c": collection_id})
        conn.execute(sa.text(
            "DELETE FROM card_collections c WHERE c.id = :c "
            "AND NOT EXISTS (SELECT 1 FROM players p WHERE p.collection_id = c.id)"
        ), {"c": collection_id})
