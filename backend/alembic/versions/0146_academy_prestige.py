"""«Академия» prestige: tiers of a path card bought with duplicates of the
same player (status, never rating), the «Икона» number, one talent reforge,
their journal and GameConfig tuning. Additive only.

Revision ID: 0146
Revises: 0145
Create Date: 2026-10-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0146"
down_revision: Union[str, None] = "0145"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_REWARDS = (
    '[{"coins": 300, "attempts": 1, "skill_tokens": 0}, {"coins": 600, "attempts": 2, "skill_tokens": 0}, '
    '{"coins": 1000, "attempts": 3, "skill_tokens": 1}, {"coins": 2000, "attempts": 5, "skill_tokens": 2}]'
)


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'path_prestige'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'path_prestige_reward'")

    op.add_column("user_cards", sa.Column("prestige", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user_cards", sa.Column("prestige_icon_number", sa.Integer(), nullable=True))
    op.create_unique_constraint("uq_user_cards_prestige_icon_number", "user_cards", ["prestige_icon_number"])
    op.add_column("user_cards", sa.Column(
        "talent_override", sa.String(32), sa.ForeignKey("path_talents.code", ondelete="RESTRICT"), nullable=True,
    ))
    op.add_column("user_cards", sa.Column("talent_reforged", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        "path_prestige_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("tier_after", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumed_card_ids", sa.JSON(), nullable=False),
        sa.Column("coins_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reward", sa.JSON(), nullable=False),
        sa.Column("from_talent", sa.String(32), nullable=True),
        sa.Column("to_talent", sa.String(32), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_path_prestige_ledger_user_key"),
    )
    op.create_index("ix_path_prestige_ledger_user_id", "path_prestige_ledger", ["user_id"])
    op.create_index("ix_path_prestige_ledger_user_card_id", "path_prestige_ledger", ["user_card_id"])

    for name, type_, default in (
        ("path_prestige_dupes", sa.JSON(), "[1, 2, 3, 5]"),
        ("path_prestige_coins", sa.JSON(), "[0, 0, 0, 0]"),
        ("path_prestige_names", sa.JSON(), '["Бронза", "Серебро", "Золото", "Икона"]'),
        ("path_prestige_rewards", sa.JSON(), _REWARDS),
        ("path_prestige_xp_pct", sa.Integer(), "5"),
        ("path_prestige_xp_cap_pct", sa.Integer(), "15"),
        ("path_prestige_free_attempts", sa.Integer(), "1"),
        ("path_prestige_sell_pct", sa.Integer(), "50"),
        ("path_prestige_other_ratio", sa.Integer(), "5"),
    ):
        op.add_column("game_config", sa.Column(name, type_, nullable=False, server_default=default))


def downgrade() -> None:
    for name in (
        "path_prestige_other_ratio", "path_prestige_sell_pct", "path_prestige_free_attempts", "path_prestige_xp_cap_pct", "path_prestige_xp_pct",
        "path_prestige_rewards", "path_prestige_names", "path_prestige_coins", "path_prestige_dupes",
    ):
        op.drop_column("game_config", name)
    op.drop_table("path_prestige_ledger")
    op.drop_column("user_cards", "talent_reforged")
    op.drop_column("user_cards", "talent_override")
    op.drop_constraint("uq_user_cards_prestige_icon_number", "user_cards", type_="unique")
    op.drop_column("user_cards", "prestige_icon_number")
    op.drop_column("user_cards", "prestige")
