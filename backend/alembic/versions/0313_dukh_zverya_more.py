"""«Дух Зверя»: six more footballers with their spirit animals (art in
static/players/<rarity>/beast_*.webp). Doué follows EA SPORTS FC 27 (86);
the rest are peak-career versions (our estimate). Rarity by rating: 90+
legendary, 85–89 epic, 80–84 rare. They drop from the regular packs.

Revision ID: 0313
Revises: 0312
"""
from alembic import op
import sqlalchemy as sa

revision = "0313"
down_revision = "0312"
branch_labels = None
depends_on = None

COLLECTION = "Дух Зверя"
SELL_PRICE = {"common": 10, "rare": 35, "epic": 120, "legendary": 400}

# name, art slug, position, country, club, rating, attack, defence, rarity, duel style, character trait
PLAYERS = (
    ("Гарринча", "garrincha", "RW", "Бразилия", "Ботафого", 94, 97, 45, "legendary", "technique", "spark"),
    ("Поль Погба", "pogba", "CM", "Франция", "Ювентус", 86, 87, 78, "epic", "power", "emotional"),
    ("Дезире Дуэ", "doue", "RW", "Франция", "ПСЖ", 86, 89, 50, "epic", "technique", "spark"),
    ("Джейми Варди", "vardy", "ST", "Англия", "Лестер Сити", 84, 88, 42, "rare", "speed", "grumbler"),
    ("Марио Балотелли", "balotelli", "ST", "Италия", "Милан", 83, 87, 40, "rare", "power", "emotional"),
    ("Питер Крауч", "crouch", "ST", "Англия", "Ливерпуль", 80, 84, 45, "rare", "power", "peacemaker"),
)


def _split(display_name: str) -> tuple[str, str]:
    parts = display_name.split(maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else parts[0]


def upgrade() -> None:
    conn = op.get_bind()
    collection_id = conn.execute(sa.text("SELECT id FROM card_collections WHERE name = :n"), {"n": COLLECTION}).scalar()
    if collection_id is None:  # 0303 creates it; never expected
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
            "CAST(:position AS position_enum), :image, :sell, true, true, :collection, :style, :trait, 1, 1, now(), now())"
        ), {
            "first": first, "last": last, "name": name, "rating": rating, "atk": attack, "dfn": defence,
            "rarity": rarity, "country": country, "club": club, "position": position,
            "image": f"players/{rarity}/beast_{slug}.webp", "sell": SELL_PRICE[rarity], "collection": collection_id,
            "style": style, "trait": trait,
        })


def downgrade() -> None:
    conn = op.get_bind()
    for _name, slug, *_rest, rarity, _style, _trait in PLAYERS:
        conn.execute(sa.text(
            "DELETE FROM players p WHERE p.image_path = :img "
            "AND NOT EXISTS (SELECT 1 FROM user_cards uc WHERE uc.player_id = p.id)"
        ), {"img": f"players/{rarity}/beast_{slug}.webp"})
