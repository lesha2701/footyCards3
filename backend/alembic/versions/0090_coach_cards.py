"""Coach, CoachBoost

Revision ID: 0090
Revises: 0089
Create Date: 2026-09-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0090"
down_revision = "0089"
branch_labels = None
depends_on = None

# rarity_enum already exists (created in 0001_initial, extended with
# "diamond" in 0083_diamond_rarity) — reuse it, don't re-declare, or
# Postgres will try to CREATE TYPE again and fail.
rarity_enum = postgresql.ENUM(
    "common", "rare", "epic", "legendary", "diamond", name="rarity_enum", create_type=False
)


def upgrade() -> None:
    op.create_table(
        "coaches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("rarity", rarity_enum, nullable=False),
        sa.Column("image_path", sa.String(length=255), nullable=True),
        sa.Column("quick_sell_price", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_pack_droppable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_serial_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("next_club_serial_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("rarity != 'diamond'", name="ck_coaches_rarity_not_diamond"),
    )
    op.create_index("ix_coaches_display_name", "coaches", ["display_name"])
    op.create_index("ix_coaches_rarity", "coaches", ["rarity"])

    coach_boost_type_enum = sa.Enum(
        "attack_central", "attack_wing", "midfield_control", "defence_central", "defence_wing",
        "goalkeeping", "passing_accuracy", "ball_control", "defensive_discipline", "counter_mastery",
        "squad_stability", name="coach_boost_type_enum",
    )
    op.create_table(
        "coach_boosts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coaches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("boost_type", coach_boost_type_enum, nullable=False),
        sa.Column("magnitude", sa.Numeric(6, 3), nullable=False),
        sa.UniqueConstraint("coach_id", "boost_type", name="uq_coach_boost_type_once"),
    )
    op.create_index("ix_coach_boosts_coach_id", "coach_boosts", ["coach_id"])


def downgrade() -> None:
    op.drop_index("ix_coach_boosts_coach_id", table_name="coach_boosts")
    op.drop_table("coach_boosts")
    bind = op.get_bind()
    sa.Enum(name="coach_boost_type_enum").drop(bind, checkfirst=True)
    op.drop_index("ix_coaches_rarity", table_name="coaches")
    op.drop_index("ix_coaches_display_name", table_name="coaches")
    op.drop_table("coaches")
