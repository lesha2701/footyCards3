"""Stadiums: a new card entity like Coaches, but with a single flat boost_pct
instead of a boost sub-table. Personal (UserStadiumCard) and club
(ClubStadiumCard) ownership, pack drop chance on both Pack and ClubPack,
mirroring the Coach system exactly.

Revision ID: 0121
Revises: 0120
Create Date: 2026-09-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0121"
down_revision: Union[str, None] = "0120"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# rarity_enum already exists (created in 0001_initial, extended with
# "diamond" in 0083_diamond_rarity) — reuse it, don't re-declare, or
# Postgres will try to CREATE TYPE again and fail. Matches 0090_coach_cards.py.
rarity_enum = postgresql.ENUM(
    "common", "rare", "epic", "legendary", "diamond", name="rarity_enum", create_type=False
)


def upgrade() -> None:
    op.create_table(
        "stadiums",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("rarity", rarity_enum, nullable=False),
        sa.Column("image_path", sa.String(length=255), nullable=True),
        sa.Column("quick_sell_price", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_pack_droppable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_serial_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("next_club_serial_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("boost_pct", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("rarity != 'diamond'", name="ck_stadiums_rarity_not_diamond"),
    )
    op.create_index("ix_stadiums_display_name", "stadiums", ["display_name"])
    op.create_index("ix_stadiums_rarity", "stadiums", ["rarity"])

    op.create_table(
        "user_stadium_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stadium_id", sa.Integer(), sa.ForeignKey("stadiums.id"), nullable=False),
        sa.Column("serial_number", sa.Integer(), nullable=False),
        sa.Column("source", postgresql.ENUM(name="card_source_enum", create_type=False), nullable=False),
        sa.Column("source_ref_id", sa.Integer(), nullable=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_user_stadium_cards_user_id", "user_stadium_cards", ["user_id"])
    op.create_index("ix_user_stadium_cards_stadium_id", "user_stadium_cards", ["stadium_id"])

    op.create_table(
        "club_stadium_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stadium_id", sa.Integer(), sa.ForeignKey("stadiums.id"), nullable=False),
        sa.Column("serial_number", sa.Integer(), nullable=False),
        # ClubStadiumCardSource has a single member (club_pack) — read from
        # app/models/enums.py: ClubCoachCardSource (the analogous type this
        # mirrors) only has "club_pack" too, not "club_pack"/"admin_grant".
        sa.Column("source", sa.Enum("club_pack", name="club_stadium_card_source_enum"), nullable=False),
        sa.Column("source_ref_id", sa.Integer(), nullable=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_club_stadium_cards_club_id", "club_stadium_cards", ["club_id"])
    op.create_index("ix_club_stadium_cards_stadium_id", "club_stadium_cards", ["stadium_id"])

    # Pack drop chance (personal + club), same shape as coach_drop_chance
    # (0097_pack_coach_slots.py / 0094_club_pack_coach_slots.py).
    op.add_column("packs", sa.Column("stadium_drop_chance", sa.Numeric(5, 4), nullable=False, server_default="0"))
    op.add_column("club_packs", sa.Column("stadium_drop_chance", sa.Numeric(5, 4), nullable=False, server_default="0"))

    # Opening-card rows gain a third nullable FK; the old two-way CHECK
    # becomes a three-way "exactly one of the three" CHECK. Bare add_column +
    # named create_foreign_key, matching 0097_pack_coach_slots.py /
    # 0094_club_pack_coach_slots.py exactly (not an inline FK column def).
    op.drop_constraint("ck_pack_opening_card_exactly_one_kind", "pack_opening_cards", type_="check")
    op.add_column("pack_opening_cards", sa.Column("user_stadium_card_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_pack_opening_cards_user_stadium_card_id", "pack_opening_cards",
        "user_stadium_cards", ["user_stadium_card_id"], ["id"], ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_pack_opening_card_exactly_one_kind",
        "pack_opening_cards",
        "(CASE WHEN user_card_id IS NOT NULL THEN 1 ELSE 0 END + "
        "CASE WHEN user_coach_card_id IS NOT NULL THEN 1 ELSE 0 END + "
        "CASE WHEN user_stadium_card_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
    )

    op.drop_constraint("ck_club_pack_opening_card_exactly_one_kind", "club_pack_opening_cards", type_="check")
    op.add_column("club_pack_opening_cards", sa.Column("club_stadium_card_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_club_pack_opening_cards_club_stadium_card_id", "club_pack_opening_cards",
        "club_stadium_cards", ["club_stadium_card_id"], ["id"], ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_club_pack_opening_card_exactly_one_kind",
        "club_pack_opening_cards",
        "(CASE WHEN club_card_id IS NOT NULL THEN 1 ELSE 0 END + "
        "CASE WHEN club_coach_card_id IS NOT NULL THEN 1 ELSE 0 END + "
        "CASE WHEN club_stadium_card_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
    )

    # Equip slots on the three in-scope squad tables. lineups.user_coach_card_id
    # (0098_lineup_coach.py) used bare add_column + named create_foreign_key,
    # no index — mirrored here for the personal-squad/lineup slot. club_lineups
    # used an inline FK + explicit index (0093_club_lineup_coach.py) — mirrored
    # here too for that table specifically.
    op.add_column("lineups", sa.Column("user_stadium_card_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_lineups_user_stadium_card_id", "lineups", "user_stadium_cards", ["user_stadium_card_id"], ["id"], ondelete="SET NULL",
    )

    op.add_column(
        "club_lineups",
        sa.Column("club_stadium_card_id", sa.Integer(), sa.ForeignKey("club_stadium_cards.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_club_lineups_club_stadium_card_id", "club_lineups", ["club_stadium_card_id"])

    op.add_column("personal_squads", sa.Column("user_stadium_card_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_personal_squads_user_stadium_card_id", "personal_squads", "user_stadium_cards", ["user_stadium_card_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_personal_squads_user_stadium_card_id", "personal_squads", type_="foreignkey")
    op.drop_column("personal_squads", "user_stadium_card_id")

    op.drop_index("ix_club_lineups_club_stadium_card_id", table_name="club_lineups")
    op.drop_column("club_lineups", "club_stadium_card_id")

    op.drop_constraint("fk_lineups_user_stadium_card_id", "lineups", type_="foreignkey")
    op.drop_column("lineups", "user_stadium_card_id")

    op.drop_constraint("ck_club_pack_opening_card_exactly_one_kind", "club_pack_opening_cards", type_="check")
    op.drop_constraint("fk_club_pack_opening_cards_club_stadium_card_id", "club_pack_opening_cards", type_="foreignkey")
    op.drop_column("club_pack_opening_cards", "club_stadium_card_id")
    op.create_check_constraint(
        "ck_club_pack_opening_card_exactly_one_kind", "club_pack_opening_cards",
        "(club_card_id IS NOT NULL AND club_coach_card_id IS NULL) OR (club_card_id IS NULL AND club_coach_card_id IS NOT NULL)",
    )

    op.drop_constraint("ck_pack_opening_card_exactly_one_kind", "pack_opening_cards", type_="check")
    op.drop_constraint("fk_pack_opening_cards_user_stadium_card_id", "pack_opening_cards", type_="foreignkey")
    op.drop_column("pack_opening_cards", "user_stadium_card_id")
    op.create_check_constraint(
        "ck_pack_opening_card_exactly_one_kind", "pack_opening_cards",
        "(user_card_id IS NOT NULL AND user_coach_card_id IS NULL) OR (user_card_id IS NULL AND user_coach_card_id IS NOT NULL)",
    )

    op.drop_column("club_packs", "stadium_drop_chance")
    op.drop_column("packs", "stadium_drop_chance")

    op.drop_table("club_stadium_cards")
    bind = op.get_bind()
    sa.Enum(name="club_stadium_card_source_enum").drop(bind, checkfirst=True)
    op.drop_table("user_stadium_cards")
    op.drop_table("stadiums")
