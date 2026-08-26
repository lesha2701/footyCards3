"""ClubCard: club-owned card pool with its own serial-number sequence

Revision ID: 0058
Revises: 0057
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0058"
down_revision: Union[str, None] = "0057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("players", sa.Column("next_club_serial_number", sa.Integer(), nullable=False, server_default="1"))

    op.create_table(
        "club_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("serial_number", sa.Integer(), nullable=False),
        sa.Column("source", sa.Enum("starter_seed", "club_pack", name="club_card_source_enum"), nullable=False),
        sa.Column("source_ref_id", sa.Integer(), nullable=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_club_cards_club_id", "club_cards", ["club_id"])
    op.create_index("ix_club_cards_player_id", "club_cards", ["player_id"])


def downgrade() -> None:
    op.drop_index("ix_club_cards_player_id", table_name="club_cards")
    op.drop_index("ix_club_cards_club_id", table_name="club_cards")
    op.drop_table("club_cards")
    op.drop_column("players", "next_club_serial_number")
    bind = op.get_bind()
    sa.Enum(name="club_card_source_enum").drop(bind, checkfirst=True)
