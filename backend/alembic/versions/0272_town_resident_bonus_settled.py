"""«Город»: a resident's bonus works only while he is settled in a district
(GameConfig.town_mood.bonus_settled_only). The residents with a bonus a
player already owns move into districts with free slots, so nobody loses a
bonus on the deploy.

Revision ID: 0272
Revises: 0271
Create Date: 2026-11-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0272"
down_revision: Union[str, None] = "0271"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DISTRICTS = ("center", "favela", "beach", "mountains", "business")  # town_service.HOUSES
SLOTS = 3  # town_service.MOOD_DEFAULTS["resident_slots"]


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT utr.id, utr.user_id, utr.district FROM user_town_residents utr "
        "JOIN town_residents tr ON tr.id = utr.resident_id "
        "WHERE utr.copies > 0 AND tr.is_active AND ("
        "  utr.district IS NOT NULL OR tr.bonus <> 'none') "
        "ORDER BY utr.user_id, utr.district IS NULL, tr.bonus_value DESC, utr.id"
    )).fetchall()
    taken: dict[int, dict[str, int]] = {}
    for row_id, user_id, district in rows:
        used = taken.setdefault(user_id, {d: 0 for d in DISTRICTS})
        if district is not None:
            used[district] = used.get(district, 0) + 1
            continue
        free = next((d for d in DISTRICTS if used[d] < SLOTS), None)
        if free is None:
            continue
        used[free] += 1
        conn.execute(sa.text("UPDATE user_town_residents SET district = :d WHERE id = :id"), {"d": free, "id": row_id})


def downgrade() -> None:
    pass  # who lives where stays; the bonus rule is the config's
