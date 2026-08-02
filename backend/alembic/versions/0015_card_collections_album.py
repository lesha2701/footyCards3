"""card collections album: cover image, completion rewards

Adds the fields needed to turn "Карточки" into a football sticker album:
`CardCollection` gets a cover image and an optional completion reward
(coins + optional bonus pack), and a new `user_collection_rewards` table
gates that reward to fire exactly once per user per collection.

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'collection_completed'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'collection_reward'")
    op.execute("ALTER TYPE card_source_enum ADD VALUE IF NOT EXISTS 'collection_reward'")

    op.add_column("card_collections", sa.Column("image_path", sa.String(255), nullable=True))
    op.add_column(
        "card_collections", sa.Column("reward_coins", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("card_collections", sa.Column("reward_pack_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_card_collections_reward_pack_id", "card_collections", "packs",
        ["reward_pack_id"], ["id"], ondelete="SET NULL",
    )

    op.create_table(
        "user_collection_rewards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "collection_id", sa.Integer(), sa.ForeignKey("card_collections.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reward_coins", sa.Integer(), nullable=False),
        sa.Column("reward_pack_id", sa.Integer(), sa.ForeignKey("packs.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("user_id", "collection_id", name="uq_user_collection_rewards_user_collection"),
    )
    op.create_index("ix_user_collection_rewards_user_id", "user_collection_rewards", ["user_id"])
    op.create_index("ix_user_collection_rewards_collection_id", "user_collection_rewards", ["collection_id"])


def downgrade() -> None:
    op.drop_index("ix_user_collection_rewards_collection_id", table_name="user_collection_rewards")
    op.drop_index("ix_user_collection_rewards_user_id", table_name="user_collection_rewards")
    op.drop_table("user_collection_rewards")
    op.drop_constraint("fk_card_collections_reward_pack_id", "card_collections", type_="foreignkey")
    op.drop_column("card_collections", "reward_pack_id")
    op.drop_column("card_collections", "reward_coins")
    op.drop_column("card_collections", "image_path")
    # enum values added above are not reversible (same caveat as 0014)
