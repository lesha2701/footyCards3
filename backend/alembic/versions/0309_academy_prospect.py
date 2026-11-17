"""«Воспитанник Академии»: the user's own child footballer raised from 6 years
old (academy_prospects), its purchase journal (prospect_ledger),
GameConfig.prospect (overrides of prospect_service.DEFAULTS) and «Менеджер»:
a contract's subject («Мой игрок», the prospect or his graduate) and the
club's «the prospect always starts» switch.

A user raises one prospect at a time (status "growing") and keeps one
active graduate ("graduate"); older graduates retire to the hall
("retired") — partial unique indexes. prospect_duels: async «Ответка» duels
between friends' prospects. Notification type prospect_event.

Revision ID: 0309
Revises: 0308
Create Date: 2026-11-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0309"
down_revision: Union[str, None] = "0308"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'prospect_purchase'")
        op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'prospect_event'")
    op.add_column("game_config", sa.Column("prospect", sa.JSON(), nullable=False, server_default="{}"))
    position = postgresql.ENUM(name="position_enum", create_type=False)
    op.create_table(
        "academy_prospects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="growing"),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("graduated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("final_rating", sa.Integer(), nullable=True),
        sa.Column("specs", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("week_key", sa.String(10), nullable=True),
        sa.Column("week_xp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_week_key", sa.String(10), nullable=True),
        sa.Column("last_week_xp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("value_history", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("name", sa.String(24), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("position", position, nullable=False),
        sa.Column("foot", sa.String(8), nullable=False, server_default="right"),
        sa.Column("appearance", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("potential", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("potential_revealed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position_set", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("academy_peak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("xp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("xp_day", sa.Date(), nullable=True),
        sa.Column("xp_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("training_day", sa.Date(), nullable=True),
        sa.Column("training_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extra_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extra_bought", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extra_day", sa.Date(), nullable=True),
        sa.Column("story_day", sa.Date(), nullable=True),
        sa.Column("coach_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mentor_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cosmetics", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("memories", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("stats", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("rival_seed", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("market_open", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_academy_prospects_user_id", "academy_prospects", ["user_id"])
    op.create_index("uq_academy_prospects_growing", "academy_prospects", ["user_id"], unique=True,
                    postgresql_where=sa.text("status = 'growing'"), sqlite_where=sa.text("status = 'growing'"))
    op.create_index("uq_academy_prospects_graduate", "academy_prospects", ["user_id"], unique=True,
                    postgresql_where=sa.text("status = 'graduate'"), sqlite_where=sa.text("status = 'graduate'"))
    op.create_table(
        "prospect_duels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("challenger_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opponent_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        sa.Column("challenger_session_id", sa.Integer(), nullable=True),
        sa.Column("opponent_session_id", sa.Integer(), nullable=True),
        sa.Column("challenger_result", sa.JSON(), nullable=True),
        sa.Column("opponent_result", sa.JSON(), nullable=True),
        sa.Column("winner_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_prospect_duels_challenger_id", "prospect_duels", ["challenger_id"])
    op.create_index("ix_prospect_duels_opponent_id", "prospect_duels", ["opponent_id"])
    op.create_table(
        "prospect_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("code", sa.String(32), nullable=True),
        sa.Column("coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(96), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_prospect_ledger_key"),
    )
    op.create_index("ix_prospect_ledger_user_id", "prospect_ledger", ["user_id"])
    op.add_column("manager_contracts", sa.Column("subject", sa.String(8), nullable=False, server_default="player"))
    op.add_column("manager_clubs", sa.Column("prospect_starts", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("manager_clubs", "prospect_starts")
    op.drop_column("manager_contracts", "subject")
    op.drop_index("ix_prospect_ledger_user_id", table_name="prospect_ledger")
    op.drop_table("prospect_ledger")
    op.drop_index("ix_prospect_duels_opponent_id", table_name="prospect_duels")
    op.drop_index("ix_prospect_duels_challenger_id", table_name="prospect_duels")
    op.drop_table("prospect_duels")
    op.drop_index("uq_academy_prospects_graduate", table_name="academy_prospects")
    op.drop_index("uq_academy_prospects_growing", table_name="academy_prospects")
    op.drop_index("ix_academy_prospects_user_id", table_name="academy_prospects")
    op.drop_table("academy_prospects")
    op.drop_column("game_config", "prospect")
