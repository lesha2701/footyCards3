""""Мой игрок", этап 2: skill, cosmetics, daily training + settings and the
my_player_cosmetic transaction type.

Revision ID: 0131
Revises: 0130
Create Date: 2026-10-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0131"
down_revision: Union[str, None] = "0130"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json(value: str):
    return sa.text(f"'{value}'::json")


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'my_player_cosmetic'")
    op.add_column("my_players", sa.Column("skill_code", sa.String(32), nullable=True))
    op.add_column("my_players", sa.Column("cosmetics", sa.JSON(), nullable=False, server_default=_json("{}")))
    op.add_column("my_players", sa.Column("training_day", sa.Date(), nullable=True))
    op.add_column("my_players", sa.Column("training_started_at", sa.DateTime(timezone=True), nullable=True))
    gc = "game_config"
    op.add_column(gc, sa.Column("my_player_training_xp_base", sa.Integer(), nullable=False, server_default="20"))
    op.add_column(gc, sa.Column("my_player_training_xp_per_hit", sa.Integer(), nullable=False, server_default="15"))
    op.add_column(gc, sa.Column(
        "my_player_cosmetic_prices", sa.JSON(), nullable=False,
        server_default=_json(
            '{"headband": 300, "earring": 400, "chain": 600, "goggles": 800, '
            '"bg_sunset": 500, "bg_neon": 700, "bg_gold": 1200}'
        ),
    ))


def downgrade() -> None:
    gc = "game_config"
    for column in (
        "my_player_cosmetic_prices",
        "my_player_training_xp_per_hit", "my_player_training_xp_base",
    ):
        op.drop_column(gc, column)
    for column in ("training_started_at", "training_day", "cosmetics", "skill_code"):
        op.drop_column("my_players", column)
    # The enum value stays: Postgres can't drop enum values.
