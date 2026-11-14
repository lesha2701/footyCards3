"""«Клуб Центурионов»: fourteen legends with 100+ caps for their country,
drawn as Roman centurions (art in static/players/<rarity>/cent_*.webp), and
the collection switched on.

They drop only from «Юбилейный пак» (pack_service._pick_collection_player
ignores is_pack_droppable): is_pack_droppable false keeps them out of the
regular packs, the wheel and random card rewards. Ratings follow the rarity
bands (legendary 90+, epic 85–89, rare 80–84).

Revision ID: 0295
Revises: 0294
"""
from alembic import op
import sqlalchemy as sa

revision = "0295"
down_revision = "0294"
branch_labels = None
depends_on = None

COLLECTION = "Клуб Центурионов"
SELL_PRICE = {"rare": 35, "epic": 120, "legendary": 400}

# name, art slug, position, country, club, rating, attack, defence, rarity, duel style, character trait
PLAYERS = (
    ("Криштиану Роналду", "ronaldo", "ST", "Португалия", "Реал Мадрид", 95, 97, 42, "legendary", "power", "spark"),
    ("Джанлуиджи Буффон", "buffon", "GK", "Италия", "Ювентус", 93, 55, 95, "legendary", "reading", "stoic"),
    ("Лука Модрич", "modric", "CM", "Хорватия", "Реал Мадрид", 91, 89, 74, "legendary", "technique", "peacemaker"),
    ("Кафу", "cafu", "RB", "Бразилия", "Милан", 91, 84, 89, "legendary", "speed", "spark"),
    ("Тьерри Анри", "henry", "ST", "Франция", "Арсенал", 90, 94, 40, "legendary", "speed", "stoic"),
    ("Серхио Рамос", "ramos", "CB", "Испания", "Реал Мадрид", 89, 70, 91, "epic", "power", "grumbler"),
    ("Мирослав Клозе", "klose", "ST", "Германия", "Лацио", 88, 90, 42, "epic", "reading", "stoic"),
    ("Филипп Лам", "lahm", "RB", "Германия", "Бавария", 88, 80, 89, "epic", "reading", "peacemaker"),
    ("Дидье Дрогба", "drogba", "ST", "Кот-д'Ивуар", "Челси", 87, 90, 45, "epic", "power", "spark"),
    ("Гарри Кейн", "kane", "ST", "Англия", "Бавария", 87, 90, 44, "epic", "technique", "stoic"),
    ("Эдвин ван дер Сар", "van_der_sar", "GK", "Нидерланды", "Манчестер Юнайтед", 84, 50, 86, "rare", "reading", "stoic"),
    ("Игорь Акинфеев", "akinfeev", "GK", "Россия", "ЦСКА", 83, 48, 85, "rare", "reading", "stoic"),
    ("Сергей Игнашевич", "ignashevich", "CB", "Россия", "ЦСКА", 82, 55, 84, "rare", "reading", "grumbler"),
    ("Андрес Гуардадо", "guardado", "CM", "Мексика", "Бетис", 81, 80, 70, "rare", "technique", "peacemaker"),
)


def _split(display_name: str) -> tuple[str, str]:
    parts = display_name.split(maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else parts[0]


def upgrade() -> None:
    conn = op.get_bind()
    collection_id = conn.execute(sa.text("SELECT id FROM card_collections WHERE name = :n"), {"n": COLLECTION}).scalar()
    if collection_id is None:  # made by 0292; absent only if an admin renamed it
        return
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
            "CAST(:position AS position_enum), :image, :sell, true, false, :collection, :style, :trait, 1, 1, "
            "now(), now())"
        ), {
            "first": first, "last": last, "name": name, "rating": rating, "atk": attack, "dfn": defence,
            "rarity": rarity, "country": country, "club": club, "position": position,
            "image": f"players/{rarity}/cent_{slug}.webp", "sell": SELL_PRICE[rarity], "collection": collection_id,
            "style": style, "trait": trait,
        })
    conn.execute(sa.text("UPDATE card_collections SET is_active = true WHERE id = :c"), {"c": collection_id})


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE card_collections SET is_active = false WHERE name = :n"), {"n": COLLECTION})
    # Only designs nobody owns yet; owned cards stay.
    conn.execute(sa.text(
        "DELETE FROM players p WHERE p.image_path LIKE 'players/%/cent_%' "
        "AND NOT EXISTS (SELECT 1 FROM user_cards uc WHERE uc.player_id = p.id)"
    ))
