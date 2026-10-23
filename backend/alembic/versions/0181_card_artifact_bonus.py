"""«Артефакты»: the card rating bonus (e.g. Maldini's armband: +3 to the
owner's Maldini cards) is stored on the card row, like stars, so every mode
and the collection see it — before it only applied in «Карьера тренера».

artifact_bonus_owner_id = who the bonus was computed for: after a trade the
new owner's card ignores the old owner's bonus until it is recomputed.

Revision ID: 0181
Revises: 0180
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0181"
down_revision: Union[str, None] = "0180"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_cards", sa.Column("artifact_rating_bonus", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user_cards", sa.Column("artifact_bonus_owner_id", sa.Integer(), nullable=True))
    # Backfill from the artifacts active right now (one copy per artifact
    # counts; summed per player and capped like artifact_service.card_bonuses).
    op.execute(
        """
        UPDATE user_cards uc
        SET artifact_rating_bonus = LEAST(b.total, gc.artifact_max_stat), artifact_bonus_owner_id = uc.owner_id
        FROM (
            SELECT d.user_id, d.card_player_id, sum(d.card_rating_bonus) AS total
            FROM (
                SELECT DISTINCT ua.user_id, a.id, a.card_player_id, a.card_rating_bonus
                FROM user_artifacts ua JOIN artifacts a ON a.id = ua.artifact_id
                WHERE ua.equipped AND a.card_player_id IS NOT NULL AND a.card_rating_bonus > 0
            ) d
            GROUP BY d.user_id, d.card_player_id
        ) b, game_config gc
        WHERE gc.id = 1 AND gc.artifacts_enabled
          AND uc.owner_id = b.user_id AND uc.player_id = b.card_player_id
        """
    )


def downgrade() -> None:
    op.drop_column("user_cards", "artifact_bonus_owner_id")
    op.drop_column("user_cards", "artifact_rating_bonus")
