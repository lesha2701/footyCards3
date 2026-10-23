"""«Академия» building: per-user wings (scout, training, dorm, staff, hall)
with timed upgrades (coins; Stars finish them now), the free scouting
report, their journal and GameConfig tuning. Additive only.

Revision ID: 0147
Revises: 0146
Create Date: 2026-10-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0147"
down_revision: Union[str, None] = "0146"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BUILDINGS = (
    '{"scout": {"costs": [2000, 5000, 10000, 20000, 40000], "hours": [1, 4, 8, 16, 24], "effect": [1, 2, 3, 4, 5]}, '
    '"training": {"costs": [2000, 5000, 10000, 20000, 40000], "hours": [1, 4, 8, 16, 24], "effect": [4, 8, 12, 16, 20]}, '
    '"dorm": {"costs": [3000, 6000, 12000, 24000, 48000], "hours": [2, 6, 12, 18, 24], "effect": [1, 1, 2, 2, 3]}, '
    '"staff": {"costs": [2500, 6000, 12000, 24000, 45000], "hours": [2, 6, 10, 16, 24], "effect": [5, 10, 15, 20, 25]}, '
    '"hall": {"costs": [1000, 3000, 6000, 12000, 25000], "hours": [1, 2, 4, 8, 12], "effect": [1, 2, 3, 4, 5]}}'
)
_SCOUT = '{"chance_pct": [15, 20, 25, 30, 40], "cooldown_days": [7, 6, 5, 4, 3], "consolation_coins": [200, 300, 400, 500, 700]}'


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'academy_upgrade'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'academy_scout_reward'")

    op.create_table(
        "user_academies",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("levels", sa.JSON(), nullable=False),
        sa.Column("total_level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("building_code", sa.String(16), nullable=True),
        sa.Column("building_to_level", sa.Integer(), nullable=True),
        sa.Column("build_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("build_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scout_report_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_user_academies_total_level", "user_academies", ["total_level"])
    op.create_table(
        "academy_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("building_code", sa.String(16), nullable=True),
        sa.Column("to_level", sa.Integer(), nullable=True),
        sa.Column("coins_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stars_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_academy_ledger_user_key"),
    )
    op.create_index("ix_academy_ledger_user_id", "academy_ledger", ["user_id"])
    op.add_column("stars_invoices", sa.Column("academy_speedup", sa.String(32), nullable=True))
    op.add_column("game_config", sa.Column("academy_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("game_config", sa.Column("academy_buildings", sa.JSON(), nullable=False, server_default=_BUILDINGS))
    op.add_column("game_config", sa.Column("academy_stars_per_hour", sa.Integer(), nullable=False, server_default="2"))
    op.add_column("game_config", sa.Column("academy_scout_report", sa.JSON(), nullable=False, server_default=_SCOUT))


def downgrade() -> None:
    for name in ("academy_scout_report", "academy_stars_per_hour", "academy_buildings", "academy_enabled"):
        op.drop_column("game_config", name)
    op.drop_column("stars_invoices", "academy_speedup")
    op.drop_index("ix_academy_ledger_user_id", table_name="academy_ledger")
    op.drop_table("academy_ledger")
    op.drop_index("ix_user_academies_total_level", table_name="user_academies")
    op.drop_table("user_academies")
