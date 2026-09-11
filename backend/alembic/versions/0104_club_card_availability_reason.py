"""ClubCardAvailability.reason (red_card/injury) + club-tactical tackle/injury chance config,
replacing two previously-hardcoded probability literals

Revision ID: 0104
Revises: 0103
Create Date: 2026-09-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0104"
down_revision: Union[str, None] = "0103"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    reason_enum = sa.Enum("red_card", "injury", name="club_card_availability_reason_enum")
    reason_enum.create(bind, checkfirst=True)
    op.add_column(
        "club_card_availabilities",
        sa.Column(
            "reason",
            sa.Enum("red_card", "injury", name="club_card_availability_reason_enum", create_type=False),
            nullable=False, server_default="red_card",
        ),
    )

    op.add_column("game_config", sa.Column("club_tactical_tackle_attempt_chance", sa.Numeric(4, 2), nullable=False, server_default="0.20"))
    op.add_column("game_config", sa.Column("club_tactical_injury_chance", sa.Numeric(4, 2), nullable=False, server_default="0.35"))


def downgrade() -> None:
    op.drop_column("game_config", "club_tactical_injury_chance")
    op.drop_column("game_config", "club_tactical_tackle_attempt_chance")
    op.drop_column("club_card_availabilities", "reason")
    sa.Enum(name="club_card_availability_reason_enum").drop(op.get_bind(), checkfirst=True)
