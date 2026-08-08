"""Trophy system: admin-defined trophies granted to players

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trophy_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("icon", sa.String(length=16), nullable=False, server_default="🏆"),
        sa.Column("image_path", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "user_trophies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "trophy_definition_id", sa.Integer(),
            sa.ForeignKey("trophy_definitions.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("granted_by_admin_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("message", sa.String(length=500), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_user_trophies_user_id", "user_trophies", ["user_id"])
    op.create_index("ix_user_trophies_trophy_definition_id", "user_trophies", ["trophy_definition_id"])


def downgrade() -> None:
    op.drop_index("ix_user_trophies_trophy_definition_id", table_name="user_trophies")
    op.drop_index("ix_user_trophies_user_id", table_name="user_trophies")
    op.drop_table("user_trophies")
    op.drop_table("trophy_definitions")
