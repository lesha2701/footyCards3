"""«Моя вилла» in the game: the pitch's extra training (my_players.villa_training_day),
the villa's daily income, the week's party (user_town_villas.income_day / party_until /
party_week, town_visits.party_coins) and the prestige «Вилла месяца» ranks by.

Revision ID: 0306
Revises: 0305
Create Date: 2026-11-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0306"
down_revision: Union[str, None] = "0305"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("my_players", sa.Column("villa_training_day", sa.Date(), nullable=True))
    op.add_column("user_town_villas", sa.Column("income_day", sa.Date(), nullable=True))
    op.add_column("user_town_villas", sa.Column("party_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_town_villas", sa.Column("party_week", sa.String(12), nullable=True))
    op.add_column("user_town_villas", sa.Column("prestige", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("town_visits", sa.Column("party_coins", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("town_visits", "party_coins")
    op.drop_column("user_town_villas", "prestige")
    op.drop_column("user_town_villas", "party_week")
    op.drop_column("user_town_villas", "party_until")
    op.drop_column("user_town_villas", "income_day")
    op.drop_column("my_players", "villa_training_day")
