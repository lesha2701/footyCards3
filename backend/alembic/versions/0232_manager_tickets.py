"""«Кабинет президента», phase 3: the ticket price of a club
(manager_clubs.ticket_pct, % of the base price).

Revision ID: 0232
Revises: 0231
Create Date: 2026-11-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0232"
down_revision: Union[str, None] = "0231"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("manager_clubs", sa.Column("ticket_pct", sa.Integer(), nullable=False, server_default="100"))


def downgrade() -> None:
    op.drop_column("manager_clubs", "ticket_pct")
