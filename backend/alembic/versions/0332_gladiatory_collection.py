"""«Гладиаторы»: a new collection — 28 footballers (cover
static/card_collections/gladiatory.webp, art in
static/players/<rarity>/glad_*.webp). Ratings are the admin's call: the main
stat (attack or defence) is at most 2 above the overall, nothing above 95.
Rarity by rating: 90+ legendary, 85–89 epic, 80–84 rare.

Франческо Тотти is a numbered edition of 20 copies (Player.edition_size;
packs stop dropping him once they are out) and carries the new
players.chemistry_shield — «без отрицательной химии»: no red links and no
chemistry minus in any mode (chemistry_service.compute_chemistry).

Revision ID: 0332
Revises: 0331
"""
from alembic import op
import sqlalchemy as sa

revision = "0332"
down_revision = "0331"
branch_labels = None
depends_on = None

COLLECTION = "Гладиаторы"
DESCRIPTION = "Арена ревёт, пощады не будет. Собери всех гладиаторов — получи награду."
COVER = "card_collections/gladiatory.webp"
REWARD_COINS = 5000
SORT_ORDER = 970
SELL_PRICE = {"common": 10, "rare": 35, "epic": 120, "legendary": 400}

# name, art slug, position, country, club, rating, attack, defence
PLAYERS = (
    ("Франческо Тотти", "totti", "CAM", "Италия", "Рома", 93, 95, 75),
    ("Карлес Пуйоль", "puyol", "CB", "Испания", "Барселона", 91, 62, 93),
    ("Франк Рибери", "ribery", "LW", "Франция", "Бавария", 91, 93, 52),
    ("Уэйн Руни", "rooney", "ST", "Англия", "Манчестер Юнайтед", 91, 93, 60),
    ("Радамель Фалькао", "falcao", "ST", "Колумбия", "Атлетико Мадрид", 90, 92, 45),
    ("Рой Кин", "keane", "CDM", "Ирландия", "Манчестер Юнайтед", 90, 72, 92),
    ("Адриано", "adriano", "ST", "Бразилия", "Интер", 89, 91, 45),
    ("Давид Трезеге", "trezeguet", "ST", "Франция", "Ювентус", 89, 91, 40),
    ("Лаутаро Мартинес", "lautaro", "ST", "Аргентина", "Интер", 89, 91, 50),
    ("Карлос Тевес", "tevez", "ST", "Аргентина", "Манчестер Юнайтед", 88, 90, 55),
    ("Дженнаро Гаттузо", "gattuso", "CDM", "Италия", "Милан", 88, 66, 90),
    ("Майкон", "maicon", "RB", "Бразилия", "Интер", 88, 82, 89),
    ("Александер Исак", "isak", "ST", "Швеция", "Ливерпуль", 87, 89, 44),
    ("Хавьер Маскерано", "mascherano", "CDM", "Аргентина", "Барселона", 87, 64, 89),
    ("Майкл Эссьен", "essien", "CM", "Гана", "Челси", 87, 85, 88),
    ("Рафаэл Леау", "leao", "LW", "Португалия", "Милан", 87, 89, 45),
    ("Робер Пирес", "pires", "LM", "Франция", "Арсенал", 87, 89, 58),
    ("Вальтер Самуэль", "samuel", "CB", "Аргентина", "Интер", 87, 55, 89),
    ("Антонио Рюдигер", "rudiger", "CB", "Германия", "Реал Мадрид", 86, 62, 88),
    ("Диего Коста", "diego_costa", "ST", "Испания", "Атлетико Мадрид", 86, 88, 52),
    ("Виктор Осимхен", "osimhen", "ST", "Нигерия", "Галатасарай", 86, 88, 44),
    ("Бранислав Иванович", "ivanovic", "RB", "Сербия", "Челси", 85, 74, 87),
    ("Аритс Адурис", "aduriz", "ST", "Испания", "Атлетик", 84, 86, 45),
    ("Эсекьель Лавесси", "lavezzi", "LW", "Аргентина", "Наполи", 84, 86, 48),
    ("Мартин Шкртел", "skrtel", "CB", "Словакия", "Ливерпуль", 84, 55, 86),
    ("Джибриль Сиссе", "cisse", "ST", "Франция", "Ливерпуль", 82, 84, 45),
    ("Маруан Феллайни", "fellaini", "CM", "Бельгия", "Манчестер Юнайтед", 81, 81, 80),
    ("Ренату Санчес", "sanches", "CM", "Португалия", "Бенфика", 80, 81, 76),
)

# slug -> (edition_size, chemistry_shield)
SPECIAL = {"totti": (20, True)}


def _rarity(rating: int) -> str:
    return "legendary" if rating >= 90 else "epic" if rating >= 85 else "rare" if rating >= 80 else "common"


def _split(display_name: str) -> tuple[str, str]:
    parts = display_name.split(maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else parts[0]


def _collection_id(conn):
    return conn.execute(sa.text("SELECT id FROM card_collections WHERE name = :n"), {"n": COLLECTION}).scalar()


def upgrade() -> None:
    op.add_column(
        "players",
        sa.Column("chemistry_shield", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
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
            "image": f"players/{rarity}/glad_{slug}.webp", "sell": SELL_PRICE[rarity], "collection": collection_id,
            "edition": edition, "shield": shield,
        })


def downgrade() -> None:
    conn = op.get_bind()
    collection_id = _collection_id(conn)
    if collection_id is not None:
        # Only designs nobody owns yet; owned cards and the collection stay then.
        conn.execute(sa.text(
            "DELETE FROM players p WHERE p.collection_id = :c AND p.image_path LIKE 'players/%/glad_%' "
            "AND NOT EXISTS (SELECT 1 FROM user_cards uc WHERE uc.player_id = p.id)"
        ), {"c": collection_id})
        conn.execute(sa.text(
            "DELETE FROM card_collections c WHERE c.id = :c "
            "AND NOT EXISTS (SELECT 1 FROM players p WHERE p.collection_id = c.id)"
        ), {"c": collection_id})
    op.drop_column("players", "chemistry_shield")
