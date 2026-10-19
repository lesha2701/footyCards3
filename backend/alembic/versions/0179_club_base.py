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
# here, not imported, so the migration never changes with the model).
# 25 levels like the whole «Академия»: costs and build hours grow smoothly,
# effects go linearly from level 1 to level 25 (the caps below still apply).
_LEVELS = 25


def _nice(v: float) -> int:
    step = 100 if v < 10000 else 500 if v < 100000 else 1000
    return int(round(v / step) * step)


def _costs(base: int, k: float) -> list[int]:
    return [_nice(base + k * lv ** 1.9) for lv in range(1, _LEVELS + 1)]


def _hours(base: float, k: float) -> list[int]:
    return [int(round(base + k * lv ** 2)) for lv in range(1, _LEVELS + 1)]


def _line(first: int, last: int, step: int = 1) -> list[int]:
    return [int(round((first + (last - first) * (lv - 1) / (_LEVELS - 1)) / step) * step) for lv in range(1, _LEVELS + 1)]


_BASE_COSTS, _BASE_HOURS = _costs(600, 220), _hours(3, 0.3)
_BUILDINGS = {
    "hq": {"costs": _costs(500, 165), "hours": _hours(2, 0.25), "cap": list(range(1, _LEVELS + 1))},
    "stadium": {"costs": _costs(1500, 350), "hours": _hours(6, 0.45), "matchday": _line(10, 150),
                "capacity": _line(3000, 90000, 500)},
    "hotel": {"costs": _BASE_COSTS, "hours": _BASE_HOURS, "matchday_pct": _line(2, 55)},
    "training": {"costs": _BASE_COSTS, "hours": _BASE_HOURS, "familiarity_pct": _line(2, 55),
                 "my_player_xp_pct": _line(1, 25)},
    "medical": {"costs": _BASE_COSTS, "hours": _BASE_HOURS, "injury_pct": _line(2, 42), "recovery": _line(1, 14)},
    "analytics": {"costs": _BASE_COSTS, "hours": _BASE_HOURS, "prep_pct": _line(1, 20)},
    "media": {"costs": _BASE_COSTS, "hours": _BASE_HOURS, "rep_pct": _line(1, 25)},
    "marketing": {"costs": _BASE_COSTS, "hours": _BASE_HOURS, "daily": _line(20, 300), "matchday_pct": _line(1, 25)},
    "shop": {"costs": _BASE_COSTS, "hours": _BASE_HOURS, "daily": _line(15, 210), "sell_pct": _line(1, 10)},
    "accounting": {"costs": _BASE_COSTS, "hours": _BASE_HOURS, "discount_pct": _line(1, 15)},
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
    op.add_column("game_config", sa.Column("club_base_stars_per_hour", sa.Integer(), nullable=False, server_default="2"))
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
