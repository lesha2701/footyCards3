"""«Рабочие места» in the town: employer buildings bought and levelled for
coins (user_town_jobs), their numbers (GameConfig.town_jobs), the extra tax
an employed resident pays (town_job_tax_pct) and the club fans the town's
population brings to «Менеджер» (town_fans_k, town_fans_cap).

Revision ID: 0321
Revises: 0320
Create Date: 2026-11-19
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0321"
down_revision: Union[str, None] = "0320"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The same values as app.models.game_config.DEFAULT_TOWN_JOBS.
_JOBS = {
    "factory": {"price": 380, "jobs": 10, "levels": 5, "growth_pct": 20},
    "plant": {"price": 750, "jobs": 20, "levels": 5, "growth_pct": 20},
    "port": {"price": 1500, "jobs": 40, "levels": 5, "growth_pct": 20},
    "office": {"price": 2250, "jobs": 60, "levels": 5, "growth_pct": 20},
    "mall": {"price": 3750, "jobs": 100, "levels": 5, "growth_pct": 20},
}


def upgrade() -> None:
    op.add_column("game_config", sa.Column("town_jobs", sa.JSON(), nullable=False, server_default=json.dumps(_JOBS)))
    op.add_column("game_config", sa.Column("town_job_tax_pct", sa.Integer(), nullable=False, server_default="50"))
    op.add_column("game_config", sa.Column("town_fans_k", sa.Integer(), nullable=False, server_default="30"))
    op.add_column("game_config", sa.Column("town_fans_cap", sa.Integer(), nullable=False, server_default="1500"))
    op.create_table(
        "user_town_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("coins_paid", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bought_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "code", name="uq_user_town_jobs_code"),
    )
    op.create_index("ix_user_town_jobs_user_id", "user_town_jobs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_town_jobs_user_id", table_name="user_town_jobs")
    op.drop_table("user_town_jobs")
    for name in ("town_fans_cap", "town_fans_k", "town_job_tax_pct", "town_jobs"):
        op.drop_column("game_config", name)
