"""Тактико squads become 5 named templates per user (template_index 1..5,
one active) instead of a single row, mirroring migration 0116's Card
Arena change. Templates 2-5 are lazily created by tactico_service on
first read, not backfilled here.

Revision ID: 0117
Revises: 0116
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0117"
down_revision: Union[str, None] = "0116"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tactico_squads", sa.Column("template_index", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("tactico_squads", sa.Column("name", sa.String(length=64), nullable=False, server_default="Основной состав"))
    op.add_column("tactico_squads", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"))
    op.drop_constraint("uq_tactico_squads_user_id", "tactico_squads", type_="unique")
    op.create_unique_constraint("uq_tactico_squad_user_template", "tactico_squads", ["user_id", "template_index"])
    op.create_index(
        "uq_tactico_squad_one_active_per_user", "tactico_squads", ["user_id"], unique=True,
        postgresql_where=sa.text("is_active"), sqlite_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index("uq_tactico_squad_one_active_per_user", table_name="tactico_squads")
    op.drop_constraint("uq_tactico_squad_user_template", "tactico_squads", type_="unique")
    op.create_unique_constraint("uq_tactico_squads_user_id", "tactico_squads", ["user_id"])
    op.drop_column("tactico_squads", "is_active")
    op.drop_column("tactico_squads", "name")
    op.drop_column("tactico_squads", "template_index")
