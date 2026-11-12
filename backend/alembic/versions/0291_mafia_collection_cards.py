"""«Мафия»: four footballers, coach Антонио Конте, three stadiums and the
Muse Джессика (art in static/players|coaches|stadiums/<rarity>/maf_*.webp and
static/muses/mafia/). Everything drops from the regular packs, the Muse
from the «Музы» pack.

The collection was made in the admin panel, so it is found by name
(contains «мафи»); a fresh database without it gets a new one.

Revision ID: 0291
Revises: 0290
"""
from alembic import op
import sqlalchemy as sa

revision = "0291"
down_revision = "0290"
branch_labels = None
depends_on = None

COLLECTION = "Мафия"
DESCRIPTION = "Футбольная семья держит город. Собери всю коллекцию — получи награду."
SORT_ORDER = 930
SELL_PRICE = {"rare": 35, "epic": 120, "legendary": 400}
COACH_SELL_PRICE = {"epic": 200, "legendary": 500}

# name, art slug, position, country, club, rating, attack, defence, rarity, duel style, character trait
PLAYERS = (
    ("Алессандро Дель Пьеро", "del_piero", "ST", "Италия", "Ювентус", 92, 95, 52, "legendary", "technique", "stoic"),
    ("Уэсли Снейдер", "sneijder", "CAM", "Нидерланды", "Интер", 89, 91, 62, "epic", "technique", "grumbler"),
    ("Райан Шерки", "cherki", "RW", "Франция", "Манчестер Сити", 87, 90, 45, "epic", "technique", "emotional"),
    ("Нико Пас", "nico_paz", "CAM", "Аргентина", "Комо", 85, 87, 55, "epic", "technique", "spark"),
)

# name, art, country, rarity, boosts. Epic magnitude = base × 3 (coach_service.magnitude_for).
COACHES = (
    ("Антонио Конте", "coaches/epic/maf_conte.webp", "Италия", "epic",
     (("defence_central", 6), ("defence_wing", 6), ("defensive_discipline", 0.03))),
)

# name, rarity, art, sell price, boost_pct (own squad strength), opp_malus (−N to every opponent player)
STADIUMS = (
    ("Стадион Наполи", "legendary", "stadiums/legendary/maf_napoli.webp", 500, 0.05, 3),
    ("Велодром", "epic", "stadiums/epic/maf_velodrome.webp", 200, 0.03, 0),
    ("Арена Мафиози", "epic", "stadiums/epic/maf_arena_mafiosi.webp", 200, 0.02, 2),
)

# name, title, description, icon, art, rarity, effect, value, sort
MUSES = (
    ("Джессика", "королева покерного стола",
     "Ставит всё на зеро — и семья выигрывает. При ней никто не играет вполсилы.", "♠️",
     "muses/mafia/jessica.webp", "legendary", "match_rating", 3, 1),
)


def _split(display_name: str) -> tuple[str, str]:
    parts = display_name.split(maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else parts[0]


def _collection_id(conn):
    return conn.execute(sa.text(
        "SELECT id FROM card_collections WHERE lower(name) LIKE '%мафи%' ORDER BY id LIMIT 1"
    )).scalar()


def upgrade() -> None:
    conn = op.get_bind()
    collection_id = _collection_id(conn)
    if collection_id is None:
        collection_id = conn.execute(sa.text(
            "INSERT INTO card_collections (name, description, is_active, sort_order, reward_coins, "
            "created_at, updated_at) VALUES (:n, :d, true, :sort, 0, now(), now()) RETURNING id"
        ), {"n": COLLECTION, "d": DESCRIPTION, "sort": SORT_ORDER}).scalar_one()

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
            "image": f"players/{rarity}/maf_{slug}.webp", "sell": SELL_PRICE[rarity], "collection": collection_id,
            "style": style, "trait": trait,
        })

    for name, image, country, rarity, boosts in COACHES:
        if conn.execute(sa.text(
            "SELECT 1 FROM coaches WHERE display_name = :n AND collection_id = :c"
        ), {"n": name, "c": collection_id}).first():
            continue
        coach_id = conn.execute(sa.text(
            "INSERT INTO coaches (display_name, rarity, image_path, country, quick_sell_price, is_active, "
            "is_pack_droppable, next_serial_number, next_club_serial_number, collection_id, created_at, updated_at) "
            "VALUES (:n, CAST(:rarity AS rarity_enum), :img, :country, :sell, true, true, 1, 1, :c, now(), now()) "
            "RETURNING id"
        ), {
            "n": name, "rarity": rarity, "img": image, "country": country,
            "sell": COACH_SELL_PRICE[rarity], "c": collection_id,
        }).scalar_one()
        for boost_type, magnitude in boosts:
            conn.execute(sa.text(
                "INSERT INTO coach_boosts (coach_id, boost_type, magnitude) "
                "VALUES (:coach, CAST(:type AS coach_boost_type_enum), :m)"
            ), {"coach": coach_id, "type": boost_type, "m": magnitude})

    for name, rarity, image, sell, boost_pct, opp_malus in STADIUMS:
        if conn.execute(sa.text("SELECT 1 FROM stadiums WHERE display_name = :n"), {"n": name}).first():
            continue
        conn.execute(sa.text(
            "INSERT INTO stadiums (display_name, rarity, image_path, club, quick_sell_price, is_active, "
            "is_pack_droppable, next_serial_number, next_club_serial_number, boost_pct, opp_malus, collection_id, "
            "created_at, updated_at) VALUES (:n, CAST(:rarity AS rarity_enum), :img, NULL, :sell, true, true, 1, 1, "
            ":boost, :malus, :c, now(), now())"
        ), {"n": name, "rarity": rarity, "img": image, "sell": sell, "boost": boost_pct, "malus": opp_malus,
            "c": collection_id})

    # Their own line in the «Музы» gallery, like «Реальные Пацаны».
    line_id = conn.execute(sa.text("SELECT id FROM muse_collections WHERE name = :n"), {"n": COLLECTION}).scalar()
    if line_id is None:
        line_id = conn.execute(sa.text(
            "INSERT INTO muse_collections (name, description, is_active, sort_order, created_at, updated_at) "
            "VALUES (:n, :d, true, 110, now(), now()) RETURNING id"
        ), {"n": COLLECTION, "d": "Музы семьи из коллекции «Мафия»."}).scalar_one()
    for name, title, description, icon, image, rarity, effect, value, sort in MUSES:
        if conn.execute(sa.text("SELECT 1 FROM muses WHERE image_path = :img"), {"img": image}).first():
            continue
        conn.execute(sa.text(
            "INSERT INTO muses (collection_id, card_collection_id, name, title, description, icon, image_path, rarity, "
            "effect, effect_value, drop_weight, is_pack_droppable, is_active, sort_order, created_at, updated_at) "
            "VALUES (:line, :c, :n, :title, :descr, :icon, :img, :rarity, :effect, :value, 100, true, true, :sort, "
            "now(), now())"
        ), {
            "line": line_id, "c": collection_id, "n": name, "title": title, "descr": description, "icon": icon,
            "img": image, "rarity": rarity, "effect": effect, "value": value, "sort": sort,
        })


def downgrade() -> None:
    conn = op.get_bind()
    # Only designs nobody owns yet; owned cards stay.
    conn.execute(sa.text(
        "DELETE FROM players p WHERE p.image_path LIKE 'players/%/maf_%' "
        "AND NOT EXISTS (SELECT 1 FROM user_cards uc WHERE uc.player_id = p.id)"
    ))
    conn.execute(sa.text(
        "DELETE FROM coaches WHERE image_path LIKE 'coaches/%/maf_%' AND next_serial_number = 1"
    ))
    conn.execute(sa.text(
        "DELETE FROM stadiums WHERE image_path LIKE 'stadiums/%/maf_%' AND next_serial_number = 1"
    ))
    conn.execute(sa.text("DELETE FROM muses WHERE image_path LIKE 'muses/mafia/%'"
                         " AND NOT EXISTS (SELECT 1 FROM user_muses um WHERE um.muse_id = muses.id)"))
