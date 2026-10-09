"""Three more card skills: crosser (Мастер навесов), last_line (Последний
рубеж), one_on_one (Один на один). Catalog rows only — what they do lives in
app/services/card_skill_catalog.py; matches without them are unchanged.

Revision ID: 0125
Revises: 0124
Create Date: 2026-10-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0125"
down_revision: Union[str, None] = "0124"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_SKILLS = [("crosser", 6), ("last_line", 7), ("one_on_one", 8)]


def upgrade() -> None:
    for code, sort_order in NEW_SKILLS:
        op.execute(
            sa.text(
                "INSERT INTO card_skills (code, is_enabled, sort_order, pack_drop_weight, pack_drop_quantity) "
                "VALUES (:code, true, :sort, 1, 1) ON CONFLICT (code) DO NOTHING"
            ).bindparams(code=code, sort=sort_order)
        )


def downgrade() -> None:
    # Rows referenced by cards, tokens or task rewards stay (FKs RESTRICT and
    # player data is never dropped); unused ones are just closed.
    op.execute(
        "UPDATE card_skills SET is_enabled = false, pack_drop_weight = 0 "
        "WHERE code IN ('crosser', 'last_line', 'one_on_one')"
    )
