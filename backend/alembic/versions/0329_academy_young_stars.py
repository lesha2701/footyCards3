"""«Академия»: four young stars as path cards — diamond, start ~60 and grow
by playing (services/path_service.py), each with a talent that fits his
position (path_talent_catalog). Art in static/players/diamond/acad_*.webp.
They drop from diamond slots of the «Академия» pack (player_pool "path").

If a card collection named like «Академия» exists they join it; otherwise
they stay outside collections, like the other path cards.

Revision ID: 0329
Revises: 0328
"""
from alembic import op
import sqlalchemy as sa

revision = "0329"
down_revision = "0328"
branch_labels = None
depends_on = None

SELL_PRICE = 900  # diamond (seed.RARITY_SELL_PRICE)

# name, art slug, position, country, club, rating, attack, defence, talent, duel style, character trait
PLAYERS = (
    ("Неймар", "neymar", "LW", "Бразилия", "Сантос", 64, 76, 52, "big_matches", "technique", "spark"),
    ("Лука Модрич", "modric", "CM", "Хорватия", "Динамо Загреб", 62, 62, 62, "captain", "technique", "stoic"),
    ("Серхио Рамос", "ramos", "CB", "Испания", "Севилья", 62, 48, 76, "hold_lead", "power", "emotional"),
    ("Мануэль Нойер", "neuer", "GK", "Германия", "Шальке", 61, 43, 79, "composure", "reading", "stoic"),
)


def _split(display_name: str) -> tuple[str, str]:
    parts = display_name.split(maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else parts[0]


def upgrade() -> None:
    conn = op.get_bind()
    collection_id = conn.execute(sa.text(
        "SELECT id FROM card_collections WHERE lower(name) LIKE '%академи%' ORDER BY id LIMIT 1"
    )).scalar()
    for name, slug, position, country, club, rating, attack, defence, talent, style, trait in PLAYERS:
        image = f"players/diamond/acad_{slug}.webp"
        if conn.execute(sa.text("SELECT 1 FROM players WHERE image_path = :img"), {"img": image}).first():
            continue
        if not conn.execute(sa.text("SELECT 1 FROM path_talents WHERE code = :c"), {"c": talent}).first():
            talent = None  # never expected: 0145 seeds every talent
        first, last = _split(name)
        conn.execute(sa.text(
            "INSERT INTO players (first_name, last_name, display_name, rating, attack_rating, defense_rating, rarity, "
            "country, club, position, image_path, quick_sell_price, is_active, is_pack_droppable, collection_id, "
            "path_talent_code, duel_style, character_trait, next_serial_number, next_club_serial_number, "
            "created_at, updated_at) "
            "VALUES (:first, :last, :name, :rating, :atk, :dfn, CAST('diamond' AS rarity_enum), :country, :club, "
            "CAST(:position AS position_enum), :image, :sell, true, true, :collection, :talent, :style, :trait, 1, 1, "
            "now(), now())"
        ), {
            "first": first, "last": last, "name": name, "rating": rating, "atk": attack, "dfn": defence,
            "country": country, "club": club, "position": position, "image": image, "sell": SELL_PRICE,
            "collection": collection_id, "talent": talent, "style": style, "trait": trait,
        })


def downgrade() -> None:
    conn = op.get_bind()
    for slug in ("neymar", "modric", "ramos", "neuer"):
        conn.execute(sa.text(
            "DELETE FROM players p WHERE p.image_path = :img "
            "AND NOT EXISTS (SELECT 1 FROM user_cards uc WHERE uc.player_id = p.id)"
        ), {"img": f"players/diamond/acad_{slug}.webp"})
