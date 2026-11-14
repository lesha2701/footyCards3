"""Gift: last week's top chest for those the referral bug left short.

Until 0296 the weekly «Пригласи друга» gave the daily 20 activity points
instead of the weekly 30. Whoever claimed it in GIFT_WEEK and ended that week
MISSING points short of the top weekly chest (and didn't open it) gets that
chest now — its coins and card from GameConfig.task_weekly_chests — with a
notification. The task_chest_claims row (unique per user, week, chest) marks
it paid, so a rerun gives nothing twice. Banned players and players with
game rewards blocked get nothing.

Revision ID: 0297
Revises: 0296
Create Date: 2026-11-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0297"
down_revision: Union[str, None] = "0296"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GIFT_WEEK = "2026-W45"
MISSING = 10  # weekly 30 − daily 20


def _top_chest(bind) -> tuple[int, dict] | None:
    raw = bind.execute(sa.text("SELECT task_weekly_chests FROM game_config WHERE id = 1")).scalar()
    if isinstance(raw, str):
        import json

        raw = json.loads(raw)
    chests = sorted(
        (c for c in (raw or []) if isinstance(c, dict) and int(c.get("points") or 0) > 0),
        key=lambda c: int(c["points"]),
    )
    return (len(chests) - 1, chests[-1]) if chests else None


def _give_card(bind, user_id: int, rarity: str) -> str | None:
    """One random active, pack-droppable regular card of `rarity` (no
    «Академия», no collection, no numbered edition), serial number taken
    under the player's row lock like card_creation.create_user_card."""
    from sqlalchemy.orm import Session

    import app.models  # noqa: F401 — every mapper configured
    from app.models.card import UserCard
    from app.models.enums import CardSource

    player = bind.execute(sa.text(
        "SELECT id, display_name FROM players WHERE rarity = :r AND is_active AND is_pack_droppable "
        "AND path_talent_code IS NULL AND collection_id IS NULL AND edition_size IS NULL "
        "ORDER BY random() LIMIT 1"
    ), {"r": rarity}).first()
    if player is None:
        return None
    serial = bind.execute(sa.text(
        "UPDATE players SET next_serial_number = next_serial_number + 1 WHERE id = :p "
        "RETURNING next_serial_number - 1"
    ), {"p": player.id}).scalar()
    session = Session(bind=bind)
    session.add(UserCard(
        owner_id=user_id, player_id=player.id, source=CardSource.task,
        serial_number=serial, from_free_source=True,
    ))
    session.flush()
    session.close()
    return player.display_name


def upgrade() -> None:
    bind = op.get_bind()
    top = _top_chest(bind)
    if top is None:
        return
    index, chest = top
    need = int(chest["points"])
    coins = int(chest.get("coins") or 0)
    rarity = chest.get("card_rarity")
    users = bind.execute(sa.text(
        "SELECT DISTINCT u.id FROM user_tasks ut "
        "JOIN task_definitions td ON td.id = ut.task_definition_id "
        "JOIN task_activity ta ON ta.user_id = ut.user_id AND ta.period_key = ut.period_key "
        "JOIN users u ON u.id = ut.user_id "
        "WHERE td.metric = 'referrals_count' AND td.period = 'weekly' AND td.category = 'regular' "
        "AND ut.reward_claimed AND ut.period_key = :k "
        "AND ta.points < :need AND ta.points + :m >= :need "
        "AND NOT u.is_banned AND NOT u.game_rewards_blocked "
        "AND NOT EXISTS (SELECT 1 FROM task_chest_claims c WHERE c.user_id = u.id "
        "AND c.period_key = :k AND c.chest_index = :i) "
        "ORDER BY u.id"
    ), {"k": GIFT_WEEK, "need": need, "m": MISSING, "i": index}).scalars().all()

    for user_id in users:
        claim_id = bind.execute(sa.text(
            "INSERT INTO task_chest_claims (user_id, period_key, chest_index, created_at) "
            "VALUES (:u, :k, :i, now()) ON CONFLICT DO NOTHING RETURNING id"
        ), {"u": user_id, "k": GIFT_WEEK, "i": index}).scalar()
        if claim_id is None:
            continue
        parts = []
        if coins > 0:
            after = bind.execute(sa.text(
                "UPDATE users SET balance = balance + CAST(:a AS integer) WHERE id = :u RETURNING balance"
            ), {"a": coins, "u": user_id}).scalar()
            bind.execute(sa.text(
                "INSERT INTO coin_transactions (user_id, amount, balance_before, balance_after, type, description, "
                "related_object_type, related_object_id, created_at) "
                "VALUES (:u, :a, :b, :after, 'task_reward', :d, 'task_chest_claim', :c, now())"
            ), {"u": user_id, "a": coins, "b": after - coins, "after": after, "c": claim_id,
                "d": "Сундук активности (неделя) — подарок за «Пригласи друга»"})
            parts.append(f"{coins} монет")
        if rarity:
            name = _give_card(bind, user_id, rarity)
            if name:
                parts.append(f"карту {name}")
        bind.execute(sa.text(
            "INSERT INTO notifications (user_id, type, title, body, related_object_type, related_object_id, "
            "is_read, telegram_sent, created_at) "
            "VALUES (:u, 'admin_message', :t, :body, 'task_chest_claim', :c, false, false, now())"
        ), {"u": user_id, "c": claim_id, "t": "🎁 Сундук за прошлую неделю",
            "body": "Недельное задание «Пригласи друга» давало меньше очков, чем должно, и тебе не хватило "
                    f"до большого сундука. Исправили и дарим его: {', '.join(parts)}."})


def downgrade() -> None:
    pass  # a gift stays given
