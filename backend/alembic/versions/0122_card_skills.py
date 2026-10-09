"""Card skills: per-copy skill on user_cards, skill catalog state, per-skill
token balances, operation/grant ledger, GameConfig economy, task and player-
tournament token rewards, and a per-match skill snapshot.

Existing cards get NULL/NULL (no skill) — no rows are created or duplicated.
Existing matches keep working: Match.server_state without a "skills" key and
player_tournament_matches.skill_snapshot = NULL both mean "no skill effects".

Rollback policy: downgrade() intentionally removes NOTHING. Skills and tokens
are player-owned data, so a code rollback must not destroy them; the old code
simply ignores the extra nullable columns/tables (nothing reads them), and
to switch the mechanic off without a rollback use
game_config.card_skills_enabled = false. Because the schema may therefore
already exist when this revision is applied again after a downgrade, every
step below is guarded and the catalog seed is ON CONFLICT DO NOTHING.

Revision ID: 0122
Revises: 0121
Create Date: 2026-10-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0122"
down_revision: Union[str, None] = "0121"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (code, is_enabled, sort_order) — mirrors app/services/card_skill_catalog.py.
# aerial_master starts closed: the match engine has no aerial duel yet.
SKILLS = [
    ("sniper", True, 0),
    ("dribbler", True, 1),
    ("playmaker", True, 2),
    ("interceptor", True, 3),
    ("aerial_master", False, 4),
    ("reflexes", True, 5),
]

GAME_CONFIG_COLUMNS = [
    ("card_skills_enabled", sa.Boolean(), sa.true()),
    ("card_skill_level_1_bonus_pp", sa.Integer(), "2"),
    ("card_skill_level_2_bonus_pp", sa.Integer(), "4"),
    ("card_skill_level_3_bonus_pp", sa.Integer(), "6"),
    ("card_skill_event_bonus_cap_pp", sa.Integer(), "8"),
    ("card_skill_probability_floor_pct", sa.Integer(), "2"),
    ("card_skill_probability_ceiling_pct", sa.Integer(), "95"),
    ("card_skill_assign_token_cost", sa.Integer(), "1"),
    ("card_skill_assign_coin_cost", sa.Integer(), "0"),
    ("card_skill_upgrade_2_token_cost", sa.Integer(), "2"),
    ("card_skill_upgrade_2_coin_cost", sa.Integer(), "400"),
    ("card_skill_upgrade_3_token_cost", sa.Integer(), "4"),
    ("card_skill_upgrade_3_coin_cost", sa.Integer(), "1200"),
    ("card_skill_replace_token_cost", sa.Integer(), "1"),
    ("card_skill_replace_coin_cost", sa.Integer(), "300"),
]


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_column(table: str, column: str) -> bool:
    return any(c["name"] == column for c in sa.inspect(op.get_bind()).get_columns(table))


def _has_index(table: str, name: str) -> bool:
    return any(i["name"] == name for i in sa.inspect(op.get_bind()).get_indexes(table))


def _has_check(table: str, name: str) -> bool:
    return any(c["name"] == name for c in sa.inspect(op.get_bind()).get_check_constraints(table))


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'card_skill_purchase'")

    if not _has_table("card_skills"):
        op.create_table(
            "card_skills",
            sa.Column("code", sa.String(length=32), primary_key=True),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("allowed_positions", sa.JSON(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    for code, is_enabled, sort_order in SKILLS:
        op.execute(
            sa.text(
                "INSERT INTO card_skills (code, is_enabled, sort_order) VALUES (:code, :enabled, :sort) "
                "ON CONFLICT (code) DO NOTHING"
            ).bindparams(code=code, enabled=is_enabled, sort=sort_order)
        )

    if not _has_column("user_cards", "skill_code"):
        op.add_column(
            "user_cards",
            sa.Column("skill_code", sa.String(length=32), sa.ForeignKey("card_skills.code", ondelete="RESTRICT"), nullable=True),
        )
    if not _has_column("user_cards", "skill_level"):
        op.add_column("user_cards", sa.Column("skill_level", sa.Integer(), nullable=True))
    if not _has_index("user_cards", "ix_user_cards_skill_code"):
        op.create_index("ix_user_cards_skill_code", "user_cards", ["skill_code"])
    if not _has_check("user_cards", "ck_user_cards_skill_level"):
        op.create_check_constraint(
            "ck_user_cards_skill_level", "user_cards",
            "(skill_code IS NULL AND skill_level IS NULL) OR "
            "(skill_code IS NOT NULL AND skill_level IS NOT NULL AND skill_level BETWEEN 1 AND 3)",
        )

    if not _has_table("user_skill_tokens"):
        op.create_table(
            "user_skill_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("skill_code", sa.String(length=32), sa.ForeignKey("card_skills.code", ondelete="RESTRICT"), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", "skill_code", name="uq_user_skill_tokens_user_skill"),
            sa.CheckConstraint("quantity >= 0", name="ck_user_skill_tokens_quantity_non_negative"),
        )
        op.create_index("ix_user_skill_tokens_user_id", "user_skill_tokens", ["user_id"])

    if not _has_table("card_skill_ledger"):
        op.create_table(
            "card_skill_ledger",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("skill_code", sa.String(length=32), nullable=False),
            sa.Column("token_delta", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("token_balance_after", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("coins_spent", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True),
            sa.Column("from_skill_code", sa.String(length=32), nullable=True),
            sa.Column("from_level", sa.Integer(), nullable=True),
            sa.Column("to_skill_code", sa.String(length=32), nullable=True),
            sa.Column("to_level", sa.Integer(), nullable=True),
            sa.Column("admin_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("related_object_type", sa.String(length=64), nullable=True),
            sa.Column("related_object_id", sa.Integer(), nullable=True),
            sa.Column("reason", sa.String(length=255), nullable=True),
            sa.Column("idempotency_key", sa.String(length=128), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_card_skill_ledger_user_id", "card_skill_ledger", ["user_id"])
        op.create_index("ix_card_skill_ledger_user_card_id", "card_skill_ledger", ["user_card_id"])
        op.create_index("ix_card_skill_ledger_created_at", "card_skill_ledger", ["created_at"])
        op.create_index(
            "uq_card_skill_ledger_user_idem", "card_skill_ledger", ["user_id", "idempotency_key"], unique=True,
            postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        )

    for name, type_, default in GAME_CONFIG_COLUMNS:
        if not _has_column("game_config", name):
            op.add_column("game_config", sa.Column(name, type_, nullable=False, server_default=default))
    if not _has_column("game_config", "ptour_place_skill_tokens"):
        op.add_column(
            "game_config", sa.Column("ptour_place_skill_tokens", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        )

    if not _has_column("task_definitions", "reward_skill_code"):
        op.add_column(
            "task_definitions",
            sa.Column("reward_skill_code", sa.String(length=32), sa.ForeignKey("card_skills.code", ondelete="SET NULL"), nullable=True),
        )
    if not _has_column("task_definitions", "reward_skill_tokens"):
        op.add_column("task_definitions", sa.Column("reward_skill_tokens", sa.Integer(), nullable=False, server_default="0"))

    if not _has_column("player_tournament_matches", "skill_snapshot"):
        op.add_column("player_tournament_matches", sa.Column("skill_snapshot", sa.JSON(), nullable=True))


def downgrade() -> None:
    # Deliberately non-destructive — see module docstring. Postgres also
    # cannot drop the 'card_skill_purchase' enum value.
    pass
