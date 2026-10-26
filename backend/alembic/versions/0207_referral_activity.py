"""Referrals by activity: a friend counts once he has played on
GameConfig.referral_active_days days (referral_service), rewards raised
(friend 2 000, referrer 3 000), milestones by friends count
(referral_milestones, users.referral_milestone_paid) with badges «Скаут» and
«Агент». Trading from fresh accounts: 3 → 7 days (coins from the
«Путь дебютанта» can't be bound).

Revision ID: 0207
Revises: 0206
Create Date: 2026-10-26
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0207"
down_revision: Union[str, None] = "0206"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    op.add_column("users", sa.Column("referral_milestone_paid", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("game_config", sa.Column("referral_active_days", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("game_config", sa.Column("referral_milestones", sa.JSON(), nullable=True))

    badges = {}
    for name, icon, sort in (("Скаут", "🔭", 951), ("Агент", "🕶️", 952)):
        badges[name] = conn.execute(sa.text(
            "INSERT INTO badges (name, icon, is_active, sort_order, created_at, updated_at) "
            "VALUES (:name, :icon, true, :sort, now(), now()) RETURNING id"
        ), {"name": name, "icon": icon, "sort": sort}).scalar_one()
    elite = conn.execute(sa.text(
        "SELECT id FROM packs WHERE slug = 'elite' OR name = 'Elite Pack' ORDER BY (slug = 'elite') DESC, id LIMIT 1"
    )).scalar()
    milestones = [
        {"count": 3, "coins": 0, "pack_id": None, "card_rarity": "epic", "badge_id": None, "cosmetic_id": None},
        {"count": 5, "coins": 0, "pack_id": None, "card_rarity": "legendary", "badge_id": None, "cosmetic_id": None},
        {"count": 10, "coins": 10000, "pack_id": None, "card_rarity": None, "badge_id": badges["Скаут"], "cosmetic_id": None},
        {"count": 25, "coins": 0, "pack_id": elite, "card_rarity": None, "badge_id": badges["Агент"], "cosmetic_id": None},
    ]
    conn.execute(sa.text(
        "UPDATE game_config SET referral_milestones = CAST(:m AS json), "
        "referral_referred_reward = GREATEST(referral_referred_reward, 2000), "
        "referral_referrer_reward = GREATEST(referral_referrer_reward, 3000), "
        "trade_send_min_account_age_days = GREATEST(trade_send_min_account_age_days, 7)"
    ), {"m": json.dumps(milestones)})
    op.alter_column("game_config", "referral_milestones", nullable=False)
    # Friends who already earned the old reward keep it; nobody is paid twice.
    # Referrers start their milestones from where they are now.
    conn.execute(sa.text("UPDATE users SET referral_milestone_paid = referral_count"))


def downgrade() -> None:
    op.drop_column("game_config", "referral_milestones")
    op.drop_column("game_config", "referral_active_days")
    op.drop_column("users", "referral_milestone_paid")
    op.execute("DELETE FROM badges WHERE name IN ('Скаут', 'Агент') AND NOT EXISTS "
               "(SELECT 1 FROM user_badges ub WHERE ub.badge_id = badges.id)")
