"""Thanks to Stars buyers: «Покровитель недели» and «Преторианец».

Revision ID: 0286
Revises: 0285
Create Date: 2026-11-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0286"
down_revision: Union[str, None] = "0285"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TROPHIES = (
    ("stars_patron_week", "Покровитель недели", "Больше всех поддержал VICTOR FC звёздами за неделю", "👑", 901),
    ("stars_praetorian", "Преторианец", "Личная гвардия VICTOR FC: 10 000 ⭐ поддержки игры", "🛡️", 900),
)


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column("game_config", sa.Column("stars_patron_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("game_config", sa.Column("stars_patron_week_min", sa.Integer(), nullable=False, server_default="100"))
    op.add_column("game_config", sa.Column("stars_patron_week_places", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("game_config", sa.Column("stars_patron_week_card_rarity", sa.String(16), nullable=False, server_default="legendary"))
    op.add_column("game_config", sa.Column("stars_patron_week_coins", sa.Integer(), nullable=False, server_default="5000"))
    op.add_column("game_config", sa.Column("stars_praetorian_threshold", sa.Integer(), nullable=False, server_default="10000"))
    op.add_column("game_config", sa.Column("stars_praetorian_badge_id", sa.Integer(), nullable=True))
    op.create_table(
        "stars_patron_awards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("place", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("stars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("week_start", "place", name="uq_stars_patron_week_place"),
    )
    op.create_index("ix_stars_patron_awards_user_id", "stars_patron_awards", ["user_id"])

    badge_id = bind.execute(sa.text(
        "INSERT INTO badges (name, icon, is_active, sort_order, created_at, updated_at) "
        "VALUES ('Преторианец', '🛡️', true, 900, now(), now()) RETURNING id"
    )).scalar_one()
    bind.execute(sa.text("UPDATE game_config SET stars_praetorian_badge_id = :b"), {"b": badge_id})
    existing = {r[0] for r in bind.execute(sa.text("SELECT code FROM trophy_definitions")).fetchall()}
    for code, name, description, icon, sort in TROPHIES:
        if code in existing:
            continue
        bind.execute(sa.text(
            "INSERT INTO trophy_definitions (code, name, description, icon, is_active, sort_order, created_at, updated_at) "
            "VALUES (:c, :n, :d, :i, true, :s, now(), now())"
        ), {"c": code, "n": name, "d": description, "i": icon, "s": sort})


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM trophy_definitions WHERE code IN ('stars_patron_week', 'stars_praetorian')"))
    bind.execute(sa.text(
        "DELETE FROM badges WHERE id = (SELECT stars_praetorian_badge_id FROM game_config WHERE id = 1)"
    ))
    op.drop_index("ix_stars_patron_awards_user_id", table_name="stars_patron_awards")
    op.drop_table("stars_patron_awards")
    for name in (
        "stars_praetorian_badge_id", "stars_praetorian_threshold", "stars_patron_week_coins",
        "stars_patron_week_card_rarity", "stars_patron_week_places", "stars_patron_week_min", "stars_patron_enabled",
    ):
        op.drop_column("game_config", name)
