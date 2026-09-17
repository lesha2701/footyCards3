"""Club lineups become 5 named templates per club (template_index 1..5,
one active) instead of a single row, mirroring migrations 0116/0117's
Card Arena/Тактико changes. Templates 2-5 are lazily created by
club_squad_service on first access by the club's own manager, not
backfilled here.

Revision ID: 0118
Revises: 0117
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0118"
down_revision: Union[str, None] = "0117"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("club_lineups", sa.Column("template_index", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("club_lineups", sa.Column("name", sa.String(length=64), nullable=False, server_default="Основной состав"))
    op.add_column("club_lineups", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"))
    op.drop_constraint("club_lineups_club_id_key", "club_lineups", type_="unique")
    op.create_unique_constraint("uq_club_lineup_club_template", "club_lineups", ["club_id", "template_index"])
    op.create_index(
        "uq_club_lineup_one_active_per_club", "club_lineups", ["club_id"], unique=True,
        postgresql_where=sa.text("is_active"), sqlite_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index("uq_club_lineup_one_active_per_club", table_name="club_lineups")
    op.drop_constraint("uq_club_lineup_club_template", "club_lineups", type_="unique")
    op.create_unique_constraint("club_lineups_club_id_key", "club_lineups", ["club_id"])
    op.drop_column("club_lineups", "is_active")
    op.drop_column("club_lineups", "name")
    op.drop_column("club_lineups", "template_index")
