"""«Стадионы» club pack: one stadium card per opening for the club squad's
stadium slot (club_lineups.club_stadium_card_id, already in the lineup and
in team strength). Price and picture are edited in Админка → Клубные паки.

Revision ID: 0188
Revises: 0187
Create Date: 2026-10-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0188"
down_revision: Union[str, None] = "0187"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SLUG = "club-stadiums"
ODDS = (("common", 0.55), ("rare", 0.30), ("epic", 0.12), ("legendary", 0.03))


def upgrade() -> None:
    conn = op.get_bind()
    if conn.execute(sa.text("SELECT 1 FROM club_packs WHERE slug = :s"), {"s": SLUG}).first():
        return
    pack_id = conn.execute(
        sa.text(
            "INSERT INTO club_packs (slug, name, description, price, card_count, is_active, sort_order, "
            "coach_drop_chance, stadium_drop_chance, created_at, updated_at) "
            "VALUES (:slug, :name, :description, :price, 1, true, 90, 0, 1, now(), now()) RETURNING id"
        ),
        {
            "slug": SLUG,
            "name": "Стадионы",
            "description": "Один стадион для состава клуба: домашние матчи сильнее на бонус стадиона.",
            "price": 500,
        },
    ).scalar_one()
    for rarity, probability in ODDS:
        conn.execute(
            sa.text(
                "INSERT INTO club_pack_rarity_probabilities (club_pack_id, rarity, probability) "
                "VALUES (:pack, CAST(:rarity AS rarity_enum), :p)"
            ),
            {"pack": pack_id, "rarity": rarity, "p": probability},
        )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM club_packs WHERE slug = 'club-stadiums'"))
