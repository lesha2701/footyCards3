"""«Последний рубеж»: a new collection — 42 footballers (cover
static/card_collections/posledniy-rubezh.webp, art in
static/players/<rarity>/lr_*.webp). Ratings follow EA SPORTS FC 27 where we
found them; the rest are our estimate. Rarity by rating: 90+ legendary,
85–89 epic, 80–84 rare, below 80 common. Attack/defence use the default
position split (player_stats_service.compute_default_attack_defense); duel
style and character are left to their derived defaults. Everything drops
from the regular packs.

Revision ID: 0331
Revises: 0330
"""
from alembic import op
import sqlalchemy as sa

revision = "0331"
down_revision = "0330"
branch_labels = None
depends_on = None

COLLECTION = "Последний рубеж"
DESCRIPTION = "Когда отступать некуда, выходят они. Собери весь рубеж — получи награду."
COVER = "card_collections/posledniy-rubezh.webp"
REWARD_COINS = 5000
SORT_ORDER = 960
SELL_PRICE = {"common": 10, "rare": 35, "epic": 120, "legendary": 400}

# player_stats_service._SKEW / _DEFENSIVE_POSITIONS
SKEW = {"GK": 18, "CB": 14, "LB": 8, "RB": 8, "CDM": 6, "CM": 0, "CAM": 8, "LM": 6, "RM": 6, "LW": 12, "RW": 12, "ST": 16}
DEFENSIVE = {"GK", "CB", "LB", "RB", "CDM"}

# name, art slug, position, country, club, rating
PLAYERS = (
    ("Адемола Лукман", "lookman", "ST", "Нигерия", "Атлетико Мадрид", 83),
    ("Алекс Ремиро", "remiro", "GK", "Испания", "Реал Сосьедад", 83),
    ("Александер Сёрлот", "sorloth", "ST", "Норвегия", "Атлетико Мадрид", 83),
    ("Алехандро Гримальдо", "grimaldo", "LM", "Испания", "Атлетико Мадрид", 85),
    ("Брайан Мбемо", "mbeumo", "RM", "Камерун", "Манчестер Юнайтед", 84),
    ("Виктор Дьёкереш", "gyokeres", "ST", "Швеция", "Арсенал", 86),
    ("Виктор Осимхен", "osimhen", "ST", "Нигерия", "Галатасарай", 86),
    ("Гранит Джака", "xhaka", "CDM", "Швейцария", "Сандерленд", 85),
    ("Давид Райя", "raya", "GK", "Испания", "Арсенал", 88),
    ("Дензел Думфрис", "dumfries", "RB", "Нидерланды", "Интер", 83),
    ("Джон Макгинн", "mcginn", "RM", "Шотландия", "Астон Вилла", 83),
    ("Диогу Кошта", "diogo_costa", "GK", "Португалия", "Порту", 84),
    ("Доминик Соланке", "solanke", "ST", "Англия", "Тоттенхэм", 79),
    ("Жоау Пальинья", "palhinha", "CDM", "Португалия", "Бавария", 83),
    ("Исмаила Сарр", "sarr", "RW", "Сенегал", "Кристал Пэлас", 81),
    ("Йоаким Андерсен", "andersen", "CB", "Дания", "Фулхэм", 81),
    ("Каору Митома", "mitoma", "LW", "Япония", "Брайтон", 82),
    ("Кевин Де Брёйне", "de_bruyne", "CAM", "Бельгия", "Наполи", 85),
    ("Крис Вуд", "wood", "ST", "Новая Зеландия", "Ноттингем Форест", 81),
    ("Леон Горецка", "goretzka", "CM", "Германия", "Астон Вилла", 82),
    ("Матео Ковачич", "kovacic", "CM", "Хорватия", "Манчестер Сити", 81),
    ("Микель Оярсабаль", "oyarzabal", "ST", "Испания", "Реал Сосьедад", 84),
    ("Мортен Юльманн", "hjulmand", "CDM", "Дания", "Атлетико Мадрид", 83),
    ("Мохаммед Кудус", "kudus", "RM", "Гана", "Тоттенхэм", 81),
    ("Нголо Канте", "kante", "CDM", "Франция", "Аль-Иттихад", 83),
    ("Николо Барелла", "barella", "CM", "Италия", "Интер", 87),
    ("Омар Мармуш", "marmoush", "LW", "Египет", "Манчестер Сити", 82),
    ("Паскаль Гросс", "gross", "CM", "Германия", "Боруссия Дортмунд", 81),
    ("Патрик Шик", "schick", "ST", "Чехия", "Байер", 83),
    ("Пьер-Эмиль Хёйбьерг", "hojbjerg", "CDM", "Дания", "Марсель", 81),
    ("Сандро Тонали", "tonali", "CDM", "Италия", "Тоттенхэм", 85),
    ("Серу Гирасси", "guirassy", "ST", "Гвинея", "Боруссия Дортмунд", 86),
    ("Такуми Минамино", "minamino", "CAM", "Япония", "Монако", 80),
    ("Такэфуса Кубо", "kubo", "RW", "Япония", "Реал Сосьедад", 83),
    ("Унаи Симон", "unai_simon", "GK", "Испания", "Атлетик", 84),
    ("Фабиан Руис", "fabian_ruiz", "CM", "Испания", "ПСЖ", 84),
    ("Хакан Чалханоглу", "calhanoglu", "CDM", "Турция", "Интер", 85),
    ("Хвича Кварацхелия", "kvaratskhelia", "LW", "Грузия", "ПСЖ", 88),
    ("Эберечи Эзе", "eze", "CAM", "Англия", "Арсенал", 84),
    ("Юри Тилеманс", "tielemans", "CM", "Бельгия", "Манчестер Юнайтед", 85),
    ("Ян Зоммер", "sommer", "GK", "Швейцария", "Интер", 84),
    ("Яссин Буну", "bounou", "GK", "Марокко", "Аль-Хиляль", 85),
)


def _rarity(rating: int) -> str:
    return "legendary" if rating >= 90 else "epic" if rating >= 85 else "rare" if rating >= 80 else "common"


def _attack_defence(rating: int, position: str) -> tuple[int, int]:
    skew = SKEW[position]
    attack, defence = (rating - skew, rating + skew) if position in DEFENSIVE else (rating + skew, rating - skew)
    return max(1, min(99, attack)), max(1, min(99, defence))


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

    for name, slug, position, country, club, rating in PLAYERS:
        if conn.execute(sa.text(
            "SELECT 1 FROM players WHERE display_name = :n AND collection_id = :c"
        ), {"n": name, "c": collection_id}).first():
            continue
        rarity = _rarity(rating)
        attack, defence = _attack_defence(rating, position)
        first, last = _split(name)
        conn.execute(sa.text(
            "INSERT INTO players (first_name, last_name, display_name, rating, attack_rating, defense_rating, rarity, "
            "country, club, position, image_path, quick_sell_price, is_active, is_pack_droppable, collection_id, "
            "next_serial_number, next_club_serial_number, created_at, updated_at) "
            "VALUES (:first, :last, :name, :rating, :atk, :dfn, CAST(:rarity AS rarity_enum), :country, :club, "
            "CAST(:position AS position_enum), :image, :sell, true, true, :collection, 1, 1, now(), now())"
        ), {
            "first": first, "last": last, "name": name, "rating": rating, "atk": attack, "dfn": defence,
            "rarity": rarity, "country": country, "club": club, "position": position,
            "image": f"players/{rarity}/lr_{slug}.webp", "sell": SELL_PRICE[rarity], "collection": collection_id,
        })


def downgrade() -> None:
    conn = op.get_bind()
    collection_id = _collection_id(conn)
    if collection_id is None:
        return
    # Only designs nobody owns yet; owned cards and the collection stay then.
    conn.execute(sa.text(
        "DELETE FROM players p WHERE p.collection_id = :c AND p.image_path LIKE 'players/%/lr_%' "
        "AND NOT EXISTS (SELECT 1 FROM user_cards uc WHERE uc.player_id = p.id)"
    ), {"c": collection_id})
    conn.execute(sa.text(
        "DELETE FROM card_collections c WHERE c.id = :c AND NOT EXISTS (SELECT 1 FROM players p WHERE p.collection_id = c.id)"
    ), {"c": collection_id})
