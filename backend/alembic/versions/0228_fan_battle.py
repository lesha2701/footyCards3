"""«⚔️ Битва фанатов»: sides and points (fan_battle_members /
fan_battle_ledger), the event switch, dates and numbers on game_config, the
badges «Фанат 2026» (milestone) and «Чемпион трибун 2026» (the winners of the
final) and an empty, inactive collection «Капитаны» with the side-coloured
frame (card_skin 'fans') for an admin to fill.

The event is switched on with its dates (07.11 – 20.11 Moscow): it starts by
itself at midnight of the 7th; sides can be picked as soon as this runs.

Revision ID: 0228
Revises: 0227
Create Date: 2026-10-31
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0228"
down_revision: Union[str, None] = "0227"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Real datetimes: asyncpg refuses a string for a timestamptz parameter.
_MSK = timezone(timedelta(hours=3))
STARTS_AT = datetime(2026, 11, 7, tzinfo=_MSK)
ENDS_AT = datetime(2026, 11, 21, tzinfo=_MSK)
FAN_BADGE = "Фанат 2026"
CHAMPION_BADGE = "Чемпион трибун 2026"
COLLECTION = "Капитаны"


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'fan_battle_reward'")

    op.add_column("game_config", sa.Column("fan_battle_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("game_config", sa.Column("fan_battle_starts_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("game_config", sa.Column("fan_battle_ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("game_config", sa.Column("fan_battle_settings", sa.JSON(), nullable=False, server_default="{}"))

    op.create_table(
        "fan_battle_members",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("event_key", sa.String(32), primary_key=True),
        sa.Column("side", sa.String(16), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("games_day", sa.String(10), nullable=True),
        sa.Column("games_points_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_fan_battle_members_event_side_points", "fan_battle_members", ["event_key", "side", "points"])
    op.create_table(
        "fan_battle_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_key", sa.String(32), nullable=False),
        sa.Column("side", sa.String(16), nullable=False),
        sa.Column("day", sa.String(10), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("ref_key", sa.String(96), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "ref_key", name="uq_fan_battle_ledger_user_ref"),
    )
    op.create_index("ix_fan_battle_ledger_user_id", "fan_battle_ledger", ["user_id"])
    op.create_index("ix_fan_battle_ledger_event_day_side", "fan_battle_ledger", ["event_key", "day", "side"])

    conn = op.get_bind()

    def badge(name: str, icon: str, sort_order: int) -> int:
        existing = conn.execute(sa.text("SELECT id FROM badges WHERE name = :n"), {"n": name}).scalar()
        if existing is not None:
            return existing
        return conn.execute(sa.text(
            "INSERT INTO badges (name, icon, is_active, sort_order, created_at, updated_at) "
            "VALUES (:n, :i, true, :s, now(), now()) RETURNING id"
        ), {"n": name, "i": icon, "s": sort_order}).scalar_one()

    fan_badge_id = badge(FAN_BADGE, "📣", 910)
    champion_badge_id = badge(CHAMPION_BADGE, "🏆", 911)
    collection_id = conn.execute(sa.text("SELECT id FROM card_collections WHERE name = :n"), {"n": COLLECTION}).scalar()
    if collection_id is None:
        collection_id = conn.execute(sa.text(
            "INSERT INTO card_collections (name, description, is_active, sort_order, reward_coins, card_skin, "
            "created_at, updated_at) VALUES (:n, :d, false, 910, 5000, 'fans', now(), now()) RETURNING id"
        ), {"n": COLLECTION, "d": "Капитаны великих клубов — в рамке цветов твоей стороны «Битвы фанатов»."}).scalar_one()
    conn.execute(sa.text(
        "UPDATE game_config SET fan_battle_enabled = true, fan_battle_starts_at = :start, fan_battle_ends_at = :end, "
        "fan_battle_settings = CAST(:settings AS JSON) WHERE id = 1"
    ), {"start": STARTS_AT, "end": ENDS_AT, "settings": json.dumps({
        "fan_badge_id": fan_badge_id, "champion_badge_id": champion_badge_id, "collection_id": collection_id,
    })})


def downgrade() -> None:
    op.drop_index("ix_fan_battle_ledger_event_day_side", table_name="fan_battle_ledger")
    op.drop_index("ix_fan_battle_ledger_user_id", table_name="fan_battle_ledger")
    op.drop_table("fan_battle_ledger")
    op.drop_index("ix_fan_battle_members_event_side_points", table_name="fan_battle_members")
    op.drop_table("fan_battle_members")
    op.drop_column("game_config", "fan_battle_settings")
    op.drop_column("game_config", "fan_battle_ends_at")
    op.drop_column("game_config", "fan_battle_starts_at")
    op.drop_column("game_config", "fan_battle_enabled")
