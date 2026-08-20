"""Card upgrade: stake several same-rarity cards in one attempt for a
boosted (but admin-capped) success chance

Revision ID: 0050
Revises: 0049
Create Date: 2026-08-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0050"
down_revision: Union[str, None] = "0049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "card_upgrade_rules",
        sa.Column("extra_card_bonus", sa.Numeric(5, 4), nullable=False, server_default="0"),
    )
    # Nullable during backfill so existing rows can be set to their own
    # success_chance (a genuine no-op cap until an admin deliberately raises
    # it) rather than a single literal that would be wrong for every rule.
    op.add_column("card_upgrade_rules", sa.Column("max_success_chance", sa.Numeric(5, 4), nullable=True))
    op.execute("UPDATE card_upgrade_rules SET max_success_chance = success_chance")
    op.alter_column("card_upgrade_rules", "max_success_chance", nullable=False)

    op.add_column(
        "card_upgrade_attempts",
        sa.Column("card_count", sa.Integer(), nullable=False, server_default="1"),
    )
    # Nullable during backfill, same reasoning as max_success_chance above —
    # existing single-card attempts get the rule's own success_chance at
    # backfill time (the best available approximation; the exact value used
    # historically isn't otherwise recoverable).
    op.add_column("card_upgrade_attempts", sa.Column("success_chance", sa.Numeric(5, 4), nullable=True))
    op.execute(
        "UPDATE card_upgrade_attempts a SET success_chance = r.success_chance "
        "FROM card_upgrade_rules r WHERE r.from_rarity = a.from_rarity AND r.to_rarity = a.to_rarity"
    )
    # A handful of very old attempts could in principle predate today's rule
    # set (from_rarity/to_rarity no longer matching any current row) — fall
    # back to 0 rather than leave nullable/NULL, since this column reflects
    # "what was used at the time" and 0 is a safe, inert default for display.
    op.execute("UPDATE card_upgrade_attempts SET success_chance = 0 WHERE success_chance IS NULL")
    op.alter_column("card_upgrade_attempts", "success_chance", nullable=False)


def downgrade() -> None:
    op.drop_column("card_upgrade_attempts", "success_chance")
    op.drop_column("card_upgrade_attempts", "card_count")
    op.drop_column("card_upgrade_rules", "max_success_chance")
    op.drop_column("card_upgrade_rules", "extra_card_bonus")
