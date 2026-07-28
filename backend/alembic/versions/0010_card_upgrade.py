"""card rarity upgrade (risk a card + coins for a chance at a higher rarity)

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# rarity_enum was already created in 0001_initial; reuse it rather than
# re-declaring (which would try to CREATE TYPE again and fail).
rarity_enum = postgresql.ENUM("common", "rare", "epic", "legendary", name="rarity_enum", create_type=False)


RULES = [
    # (from_rarity, to_rarity, success_chance, coin_cost)
    ("common", "rare", 0.55, 50),
    ("common", "epic", 0.20, 70),
    ("common", "legendary", 0.06, 90),
    ("rare", "epic", 0.40, 130),
    ("rare", "legendary", 0.12, 170),
    ("epic", "legendary", 0.28, 280),
]


def upgrade() -> None:
    op.execute("ALTER TYPE card_source_enum ADD VALUE IF NOT EXISTS 'card_upgrade'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'card_upgrade'")

    op.create_table(
        "card_upgrade_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("from_rarity", rarity_enum, nullable=False),
        sa.Column("to_rarity", rarity_enum, nullable=False),
        sa.Column("success_chance", sa.Numeric(5, 4), nullable=False),
        sa.Column("coin_cost", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("from_rarity", "to_rarity", name="uq_card_upgrade_rule"),
    )

    op.create_table(
        "card_upgrade_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("source_player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("from_rarity", rarity_enum, nullable=False),
        sa.Column("to_rarity", rarity_enum, nullable=False),
        sa.Column("coin_cost", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("result_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_card_upgrade_attempt_idem"),
    )

    # A card being risked in an upgrade is deleted regardless of outcome; if
    # it happens to be the card a past daily reward randomly granted, that
    # historical record should just lose the reference, not block the delete.
    op.drop_constraint("daily_rewards_random_card_id_fkey", "daily_rewards", type_="foreignkey")
    op.create_foreign_key(
        "daily_rewards_random_card_id_fkey", "daily_rewards", "user_cards", ["random_card_id"], ["id"],
        ondelete="SET NULL",
    )

    conn = op.get_bind()
    for from_rarity, to_rarity, chance, cost in RULES:
        conn.execute(
            sa.text(
                "INSERT INTO card_upgrade_rules (from_rarity, to_rarity, success_chance, coin_cost, is_active, created_at, updated_at) "
                "VALUES (:from_rarity, :to_rarity, :chance, :cost, true, now(), now())"
            ),
            {"from_rarity": from_rarity, "to_rarity": to_rarity, "chance": chance, "cost": cost},
        )


def downgrade() -> None:
    op.drop_constraint("daily_rewards_random_card_id_fkey", "daily_rewards", type_="foreignkey")
    op.create_foreign_key(
        "daily_rewards_random_card_id_fkey", "daily_rewards", "user_cards", ["random_card_id"], ["id"],
    )

    op.drop_table("card_upgrade_attempts")
    op.drop_table("card_upgrade_rules")

    # Note: Postgres has no clean "ALTER TYPE ... DROP VALUE" — the
    # 'card_upgrade' values added to card_source_enum/transaction_type_enum
    # in upgrade() are intentionally left in place on downgrade.
