"""Drop the ClubCoachPack/ClubCoachPackOpening tables — coaches now drop
from ClubPack directly (see 0094)

Revision ID: 0095
Revises: 0094
Create Date: 2026-09-08

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0095"
down_revision: Union[str, None] = "0094"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("club_coach_pack_opening_cards")
    op.drop_table("club_coach_pack_openings")
    op.drop_table("club_coach_pack_rarity_probabilities")
    op.drop_table("club_coach_packs")


def downgrade() -> None:
    # These tables held only local-only, never-pushed, zero-real-data test
    # rows (confirmed at the time this migration was written) — an
    # asymmetric downgrade is accepted, same convention as every other
    # "add a new optional thing, remove it cleanly, don't bother recreating
    # the exact schema on rollback" migration in this codebase.
    raise NotImplementedError("This migration is not reversible — see its own docstring.")
