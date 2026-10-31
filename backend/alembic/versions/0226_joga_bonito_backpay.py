"""«Joga Bonito»: two players completed it while its reward was still 0. Pay
them the collection's current reward (coins + notification); each paid
user_collection_rewards row is bumped to it, so a re-run never pays twice.

Revision ID: 0226
Revises: 0225
Create Date: 2026-10-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0226"
down_revision: Union[str, None] = "0225"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLLECTION = "Joga Bonito"


def upgrade() -> None:
    conn = op.get_bind()
    collections = conn.execute(sa.text(
        "SELECT id, name, reward_coins FROM card_collections WHERE lower(name) = lower(:name) AND reward_coins > 0"
    ), {"name": COLLECTION}).all()
    for collection_id, name, reward in collections:
        owed = conn.execute(sa.text(
            "SELECT id, user_id FROM user_collection_rewards "
            "WHERE collection_id = :c AND reward_coins = 0 ORDER BY id FOR UPDATE"
        ), {"c": collection_id}).all()
        for reward_id, user_id in owed:
            after = conn.execute(sa.text(
                "UPDATE users SET balance = balance + :r WHERE id = :u RETURNING balance"
            ), {"r": reward, "u": user_id}).scalar_one()
            conn.execute(sa.text(
                "INSERT INTO coin_transactions (user_id, amount, balance_before, balance_after, type, description, "
                "related_object_type, related_object_id, created_at) "
                "VALUES (:u, :r, :before, :after, 'collection_reward', :descr, 'card_collection', :c, now())"
            ), {"u": user_id, "r": reward, "before": after - reward, "after": after, "c": collection_id,
                "descr": f"Коллекция «{name}» собрана полностью (награда начислена позже)"})
            conn.execute(sa.text("UPDATE user_collection_rewards SET reward_coins = :r WHERE id = :id"),
                         {"r": reward, "id": reward_id})
            conn.execute(sa.text(
                "INSERT INTO notifications (user_id, type, title, body, related_object_type, related_object_id, "
                "is_read, telegram_sent, created_at) "
                "VALUES (:u, 'collection_completed', :title, :body, 'card_collection', :c, false, false, now())"
            ), {"u": user_id, "c": collection_id, "title": "🎉 Награда за коллекцию!",
                "body": f"Ты собрал(а) коллекцию «{name}» — держи {reward} монет! Прости, что с опозданием."})


def downgrade() -> None:
    pass  # paid coins stay paid
