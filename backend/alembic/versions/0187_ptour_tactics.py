"""«Личный турнир»: Card Arena tactics — a style of four in a circle
(personal_squads.style) on top of the formation, played as a transparent
% on each line's ratings (manager_tactics). Old squads get the style
closest to their mentality / playstyle. GameConfig: the edge of the
winning style and the strength of the formation tilt.

Revision ID: 0187
Revises: 0186
Create Date: 2026-10-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0187"
down_revision: Union[str, None] = "0186"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("personal_squads", sa.Column("style", sa.String(16), nullable=False, server_default="possession"))
    op.execute(
        "UPDATE personal_squads SET style = CASE "
        "WHEN playstyle = 'COUNTER_ATTACK' THEN 'counter' "
        "WHEN mentality IN ('PARK_THE_BUS', 'DEFENSIVE') THEN 'defensive' "
        "WHEN mentality = 'ATTACKING' OR playstyle = 'HIGH_PRESS' THEN 'attacking' "
        "ELSE 'possession' END"
    )
    op.add_column("game_config", sa.Column("ptour_style_edge_pct", sa.Integer(), nullable=False, server_default="4"))
    op.add_column("game_config", sa.Column("ptour_formation_effect_pct", sa.Integer(), nullable=False, server_default="100"))


def downgrade() -> None:
    op.drop_column("game_config", "ptour_formation_effect_pct")
    op.drop_column("game_config", "ptour_style_edge_pct")
    op.drop_column("personal_squads", "style")
