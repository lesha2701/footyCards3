"""«Топ недели»: weekly rewards for the top places of every ranking —
weekly_top_runs / weekly_top_awards, GameConfig weekly_top_*, two exclusive
profile frames («Чемпион недели» for 1st place, «Топ недели» for the rest),
the transaction and notification types. The default ladder pays coins to
places 1–10, the two most expensive active packs to places 1–3 and a frame
to everyone in the top.

Revision ID: 0199
Revises: 0198
Create Date: 2026-10-24
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0199"
down_revision: Union[str, None] = "0198"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COINS = (5000, 3500, 2500, 1800, 1500, 1200, 1000, 800, 600, 500)


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'weekly_top_reward'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'weekly_top'")

    op.create_table(
        "weekly_top_runs",
        sa.Column("week_start", sa.Date(), primary_key=True),
        sa.Column("winners", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "weekly_top_awards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("metric", sa.String(32), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rewards", sa.JSON(), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("week_start", "metric", "rank", name="uq_weekly_top_awards_place"),
    )
    op.create_index("ix_weekly_top_awards_user_seen", "weekly_top_awards", ["user_id", "seen_at"])

    op.add_column("game_config", sa.Column("weekly_top_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("game_config", sa.Column("weekly_top_size", sa.Integer(), nullable=False, server_default="10"))
    op.add_column("game_config", sa.Column("weekly_top_rewards", sa.JSON(), nullable=True))
    op.add_column("game_config", sa.Column("weekly_top_metrics", sa.JSON(), nullable=True))

    conn = op.get_bind()
    frames = {}
    for style, name, description, sort in (
        ("weekly_champion", "Чемпион недели", "1-е место в рейтинге недели", 90),
        ("weekly_top", "Топ недели", "Место в топ-10 рейтинга недели", 91),
    ):
        frames[style] = conn.execute(sa.text(
            "INSERT INTO cosmetics (kind, name, description, style_key, coins_price, stars_price, is_exclusive, "
            "is_active, sort_order, status, win_bonus_coins, created_at, updated_at) "
            "VALUES ('profile_frame', :name, :description, :style, 0, 0, true, true, :sort, 0, 0, now(), now()) RETURNING id"
        ), {"name": name, "description": description, "style": style, "sort": sort}).scalar_one()
    packs = [r[0] for r in conn.execute(sa.text(
        "SELECT id FROM packs WHERE is_active ORDER BY price DESC, id LIMIT 2"
    )).all()]
    ladder = []
    for i, coins in enumerate(COINS, start=1):
        pack = (packs[0] if i == 1 else packs[-1] if i <= 3 else None) if packs else None
        ladder.append({
            "coins": coins, "pack_id": pack, "card_rarity": None, "badge_id": None,
            "cosmetic_id": frames["weekly_champion"] if i == 1 else frames["weekly_top"],
        })
    conn.execute(
        sa.text("UPDATE game_config SET weekly_top_rewards = CAST(:ladder AS JSON), weekly_top_metrics = CAST('[]' AS JSON)"),
        {"ladder": json.dumps(ladder)},
    )
    op.alter_column("game_config", "weekly_top_rewards", nullable=False)
    op.alter_column("game_config", "weekly_top_metrics", nullable=False)


def downgrade() -> None:
    op.execute("DELETE FROM cosmetics WHERE style_key IN ('weekly_champion', 'weekly_top') AND kind = 'profile_frame'")
    for column in ("weekly_top_metrics", "weekly_top_rewards", "weekly_top_size", "weekly_top_enabled"):
        op.drop_column("game_config", column)
    op.drop_index("ix_weekly_top_awards_user_seen", table_name="weekly_top_awards")
    op.drop_table("weekly_top_awards")
    op.drop_table("weekly_top_runs")
