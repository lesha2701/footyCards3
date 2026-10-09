"""Card-skill tokens from packs, same mechanism as stadiums: a per-slot
skill_token_drop_chance on every pack (0 = unchanged behavior for every
existing pack) plus a per-skill drop table on card_skills (weight, tokens per
drop). A token slot is recorded as a pack_opening_cards row with
skill_code/skill_token_quantity, so the exactly-one-kind CHECK gains a 4th kind.

Revision ID: 0123
Revises: 0122
Create Date: 2026-10-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0123"
down_revision: Union[str, None] = "0122"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_KIND_CHECK = (
    "(CASE WHEN user_card_id IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN user_coach_card_id IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN user_stadium_card_id IS NOT NULL THEN 1 ELSE 0 END) = 1"
)
NEW_KIND_CHECK = (
    "(CASE WHEN user_card_id IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN user_coach_card_id IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN user_stadium_card_id IS NOT NULL THEN 1 ELSE 0 END + "
    "CASE WHEN skill_code IS NOT NULL THEN 1 ELSE 0 END) = 1"
)


def upgrade() -> None:
    op.add_column(
        "packs", sa.Column("skill_token_drop_chance", sa.Numeric(5, 4), nullable=False, server_default="0"),
    )
    op.add_column("card_skills", sa.Column("pack_drop_weight", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("card_skills", sa.Column("pack_drop_quantity", sa.Integer(), nullable=False, server_default="1"))
    # The engine has no aerial duel yet — its tokens never drop.
    op.execute("UPDATE card_skills SET pack_drop_weight = 0 WHERE code = 'aerial_master'")

    op.add_column(
        "pack_opening_cards",
        sa.Column("skill_code", sa.String(length=32), sa.ForeignKey("card_skills.code", ondelete="RESTRICT"), nullable=True),
    )
    op.add_column("pack_opening_cards", sa.Column("skill_token_quantity", sa.Integer(), nullable=True))
    op.drop_constraint("ck_pack_opening_card_exactly_one_kind", "pack_opening_cards", type_="check")
    op.create_check_constraint("ck_pack_opening_card_exactly_one_kind", "pack_opening_cards", NEW_KIND_CHECK)
    op.create_check_constraint(
        "ck_pack_opening_card_skill_tokens", "pack_opening_cards",
        "(skill_code IS NULL AND skill_token_quantity IS NULL) OR "
        "(skill_code IS NOT NULL AND skill_token_quantity IS NOT NULL AND skill_token_quantity >= 1)",
    )


def downgrade() -> None:
    # Token slots can't be expressed by the old 3-kind CHECK, so they go
    # (the tokens themselves stay granted in user_skill_tokens / ledger).
    op.execute("DELETE FROM pack_opening_cards WHERE skill_code IS NOT NULL")
    op.drop_constraint("ck_pack_opening_card_skill_tokens", "pack_opening_cards", type_="check")
    op.drop_constraint("ck_pack_opening_card_exactly_one_kind", "pack_opening_cards", type_="check")
    op.create_check_constraint("ck_pack_opening_card_exactly_one_kind", "pack_opening_cards", OLD_KIND_CHECK)
    op.drop_column("pack_opening_cards", "skill_token_quantity")
    op.drop_column("pack_opening_cards", "skill_code")
    op.drop_column("card_skills", "pack_drop_quantity")
    op.drop_column("card_skills", "pack_drop_weight")
    op.drop_column("packs", "skill_token_drop_chance")
