"""Add Lineup.user_coach_card_id — personal Card Arena coach equip

Revision ID: 0098
Revises: 0097
Create Date: 2026-09-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0098"
down_revision: Union[str, None] = "0097"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("lineups", sa.Column("user_coach_card_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_lineups_user_coach_card_id", "lineups", "user_coach_cards", ["user_coach_card_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_lineups_user_coach_card_id", "lineups", type_="foreignkey")
    op.drop_column("lineups", "user_coach_card_id")
