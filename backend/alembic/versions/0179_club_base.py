"""«Клубная база»: the player's own campus around the «Академия» — buildings
with timed upgrades (one queue with the «Академия» wings), the stadium look,
sponsor/merchandise income, the journal, GameConfig tuning and the career
season's frozen base effects. Additive only; seasons already running get
base_effects = {} (no effects until their next season).

Revision ID: 0179
Revises: 0178
Create Date: 2026-10-19

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0179"
down_revision: Union[str, None] = "0178"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Same as app.models.game_config.DEFAULT_CLUB_BASE_BUILDINGS / _CAPS (kept
# literal here so the migration never changes with the model).
_COSTS = [1500, 4000, 9000, 18000, 35000]
_HOURS = [8, 24, 48, 72, 96]
_BUILDINGS = {
    "hq": {"costs": [1000, 3000, 7000, 15000, 30000], "hours": [2, 12, 24, 48, 72], "cap": [1, 2, 3, 4, 5]},
    "stadium": {"costs": [3000, 8000, 16000, 32000, 60000], "hours": [12, 24, 48, 72, 120],
                "matchday": [20, 35, 55, 80, 110], "capacity": [8000, 20000, 35000, 55000, 80000]},
    "hotel": {"costs": _COSTS, "hours": _HOURS, "matchday_pct": [10, 20, 30, 40, 50]},
    "training": {"costs": _COSTS, "hours": _HOURS, "familiarity_pct": [10, 20, 30, 40, 50],
                 "my_player_xp_pct": [5, 10, 15, 20, 25]},
    "medical": {"costs": _COSTS, "hours": _HOURS, "injury_pct": [10, 15, 20, 30, 40], "recovery": [3, 5, 7, 9, 12]},
    "analytics": {"costs": _COSTS, "hours": _HOURS, "prep_pct": [4, 8, 12, 16, 20]},
    "media": {"costs": _COSTS, "hours": _HOURS, "rep_pct": [5, 10, 15, 20, 25]},
    "marketing": {"costs": _COSTS, "hours": _HOURS, "daily": [50, 90, 140, 200, 260],
                  "matchday_pct": [5, 10, 15, 20, 25]},
    "shop": {"costs": _COSTS, "hours": _HOURS, "daily": [30, 60, 90, 130, 170], "sell_pct": [2, 4, 6, 8, 10]},
    "accounting": {"costs": _COSTS, "hours": _HOURS, "discount_pct": [3, 6, 9, 12, 15]},
}
_CAPS = {
    "matchday_pct": 100, "injury_pct": 50, "recovery": 15, "familiarity_pct": 60, "my_player_xp_pct": 30,
    "prep_pct": 25, "rep_pct": 30, "sell_pct": 15, "discount_pct": 25, "daily": 600,
}


def upgrade() -> None:
    for value in ("club_base_upgrade", "club_base_income", "club_base_matchday"):
        op.execute(f"ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS '{value}'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'club_base_built'")

    op.create_table(
        "user_club_bases",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("levels", sa.JSON(), nullable=False),
        sa.Column("total_level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("building_code", sa.String(16), nullable=True),
        sa.Column("building_to_level", sa.Integer(), nullable=True),
        sa.Column("build_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("build_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("appearance", sa.JSON(), nullable=False),
        sa.Column("income_accrued", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("income_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_user_club_bases_total_level", "user_club_bases", ["total_level"])
    op.create_index("ix_user_club_bases_build_ends_at", "user_club_bases", ["build_ends_at"])
    op.create_table(
        "club_base_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("building_code", sa.String(16), nullable=True),
        sa.Column("to_level", sa.Integer(), nullable=True),
        sa.Column("coins_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coins_earned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stars_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_club_base_ledger_user_key"),
    )
    op.create_index("ix_club_base_ledger_user_id", "club_base_ledger", ["user_id"])
    op.create_index("ix_club_base_ledger_created_at", "club_base_ledger", ["created_at"])

    op.add_column("career_participants", sa.Column("base_effects", sa.JSON(), nullable=True))
    # Seasons already under way keep playing without the base.
    op.execute("UPDATE career_participants SET base_effects = '{}'")

    op.add_column("game_config", sa.Column("club_base_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("game_config", sa.Column("club_base_buildings", sa.JSON(), nullable=False,
                                           server_default=json.dumps(_BUILDINGS)))
    op.add_column("game_config", sa.Column("club_base_caps", sa.JSON(), nullable=False, server_default=json.dumps(_CAPS)))
    op.add_column("game_config", sa.Column("club_base_stars_per_hour", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("game_config", sa.Column("club_base_income_max_days", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("game_config", sa.Column("club_base_art", sa.JSON(), nullable=False, server_default="{}"))


def downgrade() -> None:
    for name in ("club_base_art", "club_base_income_max_days", "club_base_stars_per_hour", "club_base_caps",
                 "club_base_buildings", "club_base_enabled"):
        op.drop_column("game_config", name)
    op.drop_column("career_participants", "base_effects")
    op.drop_index("ix_club_base_ledger_created_at", table_name="club_base_ledger")
    op.drop_index("ix_club_base_ledger_user_id", table_name="club_base_ledger")
    op.drop_table("club_base_ledger")
    op.drop_index("ix_user_club_bases_build_ends_at", table_name="user_club_bases")
    op.drop_index("ix_user_club_bases_total_level", table_name="user_club_bases")
    op.drop_table("user_club_bases")
    # Enum values stay (Postgres cannot drop a single enum value).
