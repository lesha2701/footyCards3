"""«Герои Камбеков»: the collection went live with a 0-coin reward. Set it to
3000 and pay the players who already completed it (their
user_collection_rewards row says 0) — each such row is bumped to 3000 in
the same statement batch, so a re-run never pays twice.

Revision ID: 0223
Revises: 0222
Create Date: 2026-10-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0223"
down_revision: Union[str, None] = "0222"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLLECTION = "Герои Камбеков"
REWARD = 3000


def upgrade() -> None:
    conn = op.get_bind()
    collections = conn.execute(sa.text(
        "SELECT id, name FROM card_collections WHERE lower(replace(name, 'ё', 'е')) = lower(replace(:name, 'ё', 'е'))"
    ), {"name": COLLECTION}).all()
    for collection_id, name in collections:
        conn.execute(sa.text("UPDATE card_collections SET reward_coins = :r WHERE id = :id"),
                     {"r": REWARD, "id": collection_id})
        owed = conn.execute(sa.text(
            "SELECT id, user_id FROM user_collection_rewards "
            "WHERE collection_id = :c AND reward_coins = 0 ORDER BY id FOR UPDATE"
        ), {"c": collection_id}).all()
        for reward_id, user_id in owed:
            after = conn.execute(sa.text(
                "UPDATE users SET balance = balance + :r WHERE id = :u RETURNING balance"
            ), {"r": REWARD, "u": user_id}).scalar_one()
            conn.execute(sa.text(
                "INSERT INTO coin_transactions (user_id, amount, balance_before, balance_after, type, description, "
                "related_object_type, related_object_id, created_at) "
                "VALUES (:u, :r, :before, :after, 'collection_reward', :descr, 'card_collection', :c, now())"
            ), {"u": user_id, "r": REWARD, "before": after - REWARD, "after": after, "c": collection_id,
                "descr": f"Коллекция «{name}» собрана полностью (награда начислена позже)"})
            conn.execute(sa.text("UPDATE user_collection_rewards SET reward_coins = :r WHERE id = :id"),
                         {"r": REWARD, "id": reward_id})
            conn.execute(sa.text(
                "INSERT INTO notifications (user_id, type, title, body, related_object_type, related_object_id, "
                "is_read, telegram_sent, created_at) "
                "VALUES (:u, 'collection_completed', :title, :body, 'card_collection', :c, false, false, now())"
            ), {"u": user_id, "c": collection_id, "title": "🎉 Награда за коллекцию!",
                "body": f"Ты собрал(а) коллекцию «{name}» — держи {REWARD} монет! Прости, что с опозданием."})


def downgrade() -> None:
    # Paid coins stay paid; only the collection's reward goes back to 0.
    op.execute(sa.text(
        "UPDATE card_collections SET reward_coins = 0 "
        "WHERE lower(replace(name, 'ё', 'е')) = lower(replace('Герои Камбеков', 'ё', 'е'))"
    ))
