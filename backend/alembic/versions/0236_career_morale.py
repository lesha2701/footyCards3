"""Team morale of «Карьера тренера»: the GameConfig switch, the coach's
skills on the career profile and a character trait per footballer (NULL =
derived) — services/career_morale_service.py.

Revision ID: 0236
Revises: 0235
Create Date: 2026-11-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0236"
down_revision: Union[str, None] = "0235"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_config", sa.Column("career_morale_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("career_profiles", sa.Column("coach_skills", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("players", sa.Column("character_trait", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("players", "character_trait")
    op.drop_column("career_profiles", "coach_skills")
    op.drop_column("game_config", "career_morale_enabled")
