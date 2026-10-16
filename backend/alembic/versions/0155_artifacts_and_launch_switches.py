"""artifacts for «Мой игрок»; richer club pass; new paid features off by default

Revision ID: 0155
Revises: 0154
Create Date: 2026-10-16

- artifacts / user_artifacts: shop collectibles for the club or «Мой игрок»
  with a small capped bonus while active (artifact_service.EFFECTS); many
  copies per player, giftable, 3 active slots, the rest on the shelf.
- club pass: a bonus with every paid month, +season XP %, free calendar
  catch-ups; daily coins 150 -> 300, extra rewarded attempts 1 -> 2.
- club pass, season pass, starter offer and artifacts start switched OFF —
  the admin configures and launches them.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0155"
down_revision: Union[str, None] = "0154"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'artifact_purchase'")

    op.create_table(
        "artifacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("image_path", sa.String(255), nullable=True),
        sa.Column("icon", sa.String(16), nullable=False, server_default="🏺"),
        sa.Column("rarity", sa.String(16), nullable=False, server_default="rare"),
        sa.Column("target", sa.String(16), nullable=False, server_default="my_player"),
        sa.Column("effect", sa.String(32), nullable=False, server_default="none"),
        sa.Column("effect_value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stadium_id", sa.Integer(), sa.ForeignKey("stadiums.id", ondelete="SET NULL"), nullable=True),
        sa.Column("stadium_effect_value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coins_price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stars_price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_supply", sa.Integer(), nullable=True),
        sa.Column("sold_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "user_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_id", sa.Integer(), sa.ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("serial_number", sa.Integer(), nullable=False),
        sa.Column("equipped", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("gifted_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("artifact_id", "serial_number", name="uq_user_artifact_serial"),
    )
    op.create_index("ix_user_artifacts_user_id", "user_artifacts", ["user_id"])

    for name, type_, default in [
        ("club_pass_bonus_coins", sa.Integer(), "2000"),
        ("club_pass_season_xp_bonus_pct", sa.Integer(), "50"),
        ("club_pass_free_catchups", sa.Integer(), "3"),
        ("artifacts_enabled", sa.Boolean(), sa.false()),
        ("artifact_slots", sa.Integer(), "3"),
        ("artifact_max_opp_pct", sa.Integer(), "5"),
        ("artifact_max_stat", sa.Integer(), "6"),
    ]:
        op.add_column("game_config", sa.Column(name, type_, nullable=False, server_default=default))
    op.add_column("game_config", sa.Column("club_pass_bonus_pack_id", sa.Integer(), nullable=True))
    op.add_column("game_config", sa.Column("club_pass_bonus_card_rarity", sa.String(16), nullable=True))

    for col in ("club_pass_enabled", "season_pass_enabled", "starter_offer_enabled"):
        op.alter_column("game_config", col, server_default=sa.false())
    op.alter_column("game_config", "club_pass_daily_coins", server_default="300")
    op.alter_column("game_config", "club_pass_extra_rewarded_attempts", server_default="2")
    op.execute(
        """
        UPDATE game_config SET
          club_pass_enabled = false, season_pass_enabled = false, starter_offer_enabled = false,
          club_pass_daily_coins = 300, club_pass_extra_rewarded_attempts = 2,
          club_pass_bonus_card_rarity = 'epic',
          club_pass_bonus_pack_id = (SELECT id FROM packs WHERE slug = 'premium' LIMIT 1)
        """
    )


def downgrade() -> None:
    for name in ("club_pass_bonus_coins", "club_pass_season_xp_bonus_pct", "club_pass_free_catchups",
                 "artifacts_enabled", "artifact_slots", "artifact_max_opp_pct", "artifact_max_stat",
                 "club_pass_bonus_pack_id", "club_pass_bonus_card_rarity"):
        op.drop_column("game_config", name)
    for col in ("club_pass_enabled", "season_pass_enabled", "starter_offer_enabled"):
        op.alter_column("game_config", col, server_default=sa.true())
    op.drop_index("ix_user_artifacts_user_id", table_name="user_artifacts")
    op.drop_table("user_artifacts")
    op.drop_table("artifacts")
