"""hourly limits, free pack, referrals, card collections, per-player serials

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE card_source_enum ADD VALUE IF NOT EXISTS 'free_pack'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'premium_task_available'")

    op.create_table(
        "card_collections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(512), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_card_collections_name"),
    )

    op.add_column(
        "players",
        sa.Column("collection_id", sa.Integer(), sa.ForeignKey("card_collections.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("players", sa.Column("next_serial_number", sa.Integer(), nullable=False, server_default="1"))

    # Backfill each player's counter from its current max serial_number, so
    # forward-numbering continues sensibly and doesn't collide with the new
    # composite unique constraint below. Existing UserCard.serial_number
    # values are NOT rewritten (historical numbers stay as-is).
    op.execute(
        """UPDATE players SET next_serial_number = COALESCE(
               (SELECT MAX(serial_number) + 1 FROM user_cards WHERE user_cards.player_id = players.id), 1
           )"""
    )

    op.drop_constraint("uq_user_cards_serial", "user_cards", type_="unique")
    op.drop_index("ix_user_cards_serial_number", table_name="user_cards")
    op.create_unique_constraint("uq_user_cards_player_serial", "user_cards", ["player_id", "serial_number"])

    op.add_column("game_config", sa.Column("hourly_game_limit", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("game_config", sa.Column("free_pack_interval_hours", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("game_config", sa.Column("free_pack_pack_slug", sa.String(), nullable=False, server_default="basic"))

    for game in ("memory", "match", "saboteur", "penalty", "free_kick"):
        op.add_column("users", sa.Column(f"{game}_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
        op.add_column("users", sa.Column(f"{game}_hour_started_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("users", sa.Column("free_pack_available_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("free_pack_notified", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column(
        "users",
        sa.Column("referred_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("users", sa.Column("referral_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("users", "referral_count")
    op.drop_column("users", "referred_by_id")
    op.drop_column("users", "free_pack_notified")
    op.drop_column("users", "free_pack_available_at")

    for game in ("memory", "match", "saboteur", "penalty", "free_kick"):
        op.drop_column("users", f"{game}_hour_started_at")
        op.drop_column("users", f"{game}_hourly_attempts")

    op.drop_column("game_config", "free_pack_pack_slug")
    op.drop_column("game_config", "free_pack_interval_hours")
    op.drop_column("game_config", "hourly_game_limit")

    # Restore the old global-unique constraint on serial_number alone. Note:
    # this can fail if per-player numbering has produced duplicate
    # serial_number values across different players since the upgrade — the
    # same asymmetric-downgrade limitation already accepted for ADD VALUE in
    # 0002 applies here.
    op.drop_constraint("uq_user_cards_player_serial", "user_cards", type_="unique")
    op.create_index("ix_user_cards_serial_number", "user_cards", ["serial_number"])
    op.create_unique_constraint("uq_user_cards_serial", "user_cards", ["serial_number"])

    op.drop_column("players", "next_serial_number")
    op.drop_column("players", "collection_id")

    op.drop_table("card_collections")

    # Enum values added above are left in place on downgrade (same precedent as 0002).
