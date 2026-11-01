"""«Менеджер»: preseason 48 h instead of 72 h.

Revision ID: 0230
Revises: 0229
Create Date: 2026-11-01

15 rounds at 3 a day take 5 days: with a 72 h preseason (Mon–Thu) the
season ran Thursday to Monday 21:00, into the next week's preseason. 48 h
(Mon–Wed) fits the week: window Mon–Wed, season Wed–Sun. Only a config
still at the old default is moved — an admin's own value stays.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0230"
down_revision: Union[str, None] = "0229"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("game_config", "manager_preseason_hours", server_default=sa.text("48"))
    op.execute("UPDATE game_config SET manager_preseason_hours = 48 WHERE manager_preseason_hours = 72")


def downgrade() -> None:
    op.alter_column("game_config", "manager_preseason_hours", server_default=sa.text("72"))
    op.execute("UPDATE game_config SET manager_preseason_hours = 72 WHERE manager_preseason_hours = 48")
