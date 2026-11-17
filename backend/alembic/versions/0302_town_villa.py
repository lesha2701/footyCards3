"""«Моя вилла»: the player's own plot in the town — villa and garage levels,
staff and the chosen car (user_town_villas), things placed on the grid
(user_town_villa_items), «Вилла недели» likes (town_visits.villa_liked) and
the GameConfig.town_villa overrides.

Revision ID: 0302
Revises: 0301
Create Date: 2026-11-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0302"
down_revision: Union[str, None] = "0301"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'town_villa'")
    op.add_column("game_config", sa.Column("town_villa", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("town_visits", sa.Column("villa_liked", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "user_town_villas",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("villa_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("garage_level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("car_item_id", sa.Integer(), nullable=True),
        sa.Column("staff", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "user_town_villa_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("code", sa.String(24), nullable=False),
        sa.Column("x", sa.Integer(), nullable=True),
        sa.Column("y", sa.Integer(), nullable=True),
        sa.Column("rot", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("serial", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", "serial", name="uq_town_villa_item_serial"),
    )


def downgrade() -> None:
    op.drop_table("user_town_villa_items")
    op.drop_table("user_town_villas")
    op.drop_column("town_visits", "villa_liked")
    op.drop_column("game_config", "town_villa")
