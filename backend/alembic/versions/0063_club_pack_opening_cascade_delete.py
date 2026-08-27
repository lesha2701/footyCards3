"""club_pack_openings.club_pack_id FK: add ON DELETE CASCADE

Revision ID: 0063
Revises: 0062
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0063"
down_revision: Union[str, None] = "0062"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("club_pack_openings_club_pack_id_fkey", "club_pack_openings", type_="foreignkey")
    op.create_foreign_key(
        "club_pack_openings_club_pack_id_fkey", "club_pack_openings", "club_packs",
        ["club_pack_id"], ["id"], ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("club_pack_openings_club_pack_id_fkey", "club_pack_openings", type_="foreignkey")
    op.create_foreign_key(
        "club_pack_openings_club_pack_id_fkey", "club_pack_openings", "club_packs",
        ["club_pack_id"], ["id"],
    )
