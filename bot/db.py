from datetime import date
from typing import Optional

import asyncpg

from config import get_bot_settings

settings = get_bot_settings()

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(settings.asyncpg_dsn, min_size=1, max_size=5)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def get_user_by_telegram_id(telegram_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)


async def get_user_by_username(username: str) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow("SELECT * FROM users WHERE username = $1", username)


async def set_ban_status(telegram_id: int, is_banned: bool) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow(
        "UPDATE users SET is_banned = $2, updated_at = now() WHERE telegram_id = $1 RETURNING *",
        telegram_id, is_banned,
    )


async def give_coins(telegram_id: int, amount: int, description: str) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1 FOR UPDATE", telegram_id)
            if user is None:
                return None
            new_balance = user["balance"] + amount
            await conn.execute(
                "UPDATE users SET balance = $2, updated_at = now() WHERE id = $1", user["id"], new_balance
            )
            await conn.execute(
                """INSERT INTO coin_transactions
                   (user_id, amount, balance_before, balance_after, type, description, created_at)
                   VALUES ($1, $2, $3, $4, 'admin_adjustment', $5, now())""",
                user["id"], amount, user["balance"], new_balance, description,
            )
            return await conn.fetchrow("SELECT * FROM users WHERE id = $1", user["id"])


async def find_player_by_name(name: str) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow(
        "SELECT * FROM players WHERE is_active = true AND display_name ILIKE $1 ORDER BY id LIMIT 1", f"%{name}%"
    )


async def give_card(telegram_id: int, player_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
            if user is None:
                return None
            player = await conn.fetchrow(
                "SELECT next_serial_number FROM players WHERE id = $1 FOR UPDATE", player_id
            )
            if player is None:
                return None
            serial_number = player["next_serial_number"]
            await conn.execute(
                "UPDATE players SET next_serial_number = $2 WHERE id = $1", player_id, serial_number + 1
            )
            row = await conn.fetchrow(
                """INSERT INTO user_cards (owner_id, player_id, serial_number, acquired_at, source, is_locked_by_admin, is_locked_in_trade, is_in_lineup)
                   VALUES ($1, $2, $3, now(), 'admin_grant', false, false, false) RETURNING id""",
                user["id"], player_id, serial_number,
            )
            return row


async def get_stats() -> dict:
    pool = await get_pool()
    total_users = await pool.fetchval("SELECT count(*) FROM users")
    total_cards = await pool.fetchval("SELECT count(*) FROM user_cards")
    total_packs = await pool.fetchval("SELECT count(*) FROM pack_openings")
    total_trades = await pool.fetchval("SELECT count(*) FROM trade_offers")
    coins_in_circulation = await pool.fetchval("SELECT coalesce(sum(balance), 0) FROM users")
    return {
        "total_users": total_users,
        "total_cards": total_cards,
        "total_packs": total_packs,
        "total_trades": total_trades,
        "coins_in_circulation": coins_in_circulation,
    }


async def fetch_unsent_notifications(limit: int = 50) -> list[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetch(
        """SELECT n.id, n.title, n.body, u.telegram_id
           FROM notifications n JOIN users u ON u.id = n.user_id
           WHERE n.telegram_sent = false
           ORDER BY n.id ASC LIMIT $1""",
        limit,
    )


async def mark_notification_sent(notification_id: int) -> None:
    pool = await get_pool()
    await pool.execute("UPDATE notifications SET telegram_sent = true WHERE id = $1", notification_id)


async def fetch_users_missing_daily_reward(today: date) -> list[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetch(
        """SELECT u.id, u.telegram_id FROM users u
           WHERE u.is_banned = false AND NOT EXISTS (
               SELECT 1 FROM daily_rewards dr WHERE dr.user_id = u.id AND dr.reward_date = $1
           )""",
        today,
    )


async def create_notification(user_id: int, type_: str, title: str, body: str) -> None:
    pool = await get_pool()
    await pool.execute(
        """INSERT INTO notifications (user_id, type, title, body, is_read, telegram_sent, created_at)
           VALUES ($1, $2, $3, $4, false, false, now())""",
        user_id, type_, title, body,
    )


async def fetch_users_with_available_unnotified_free_pack() -> list[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetch(
        """SELECT id, telegram_id FROM users
           WHERE free_pack_available_at IS NOT NULL AND free_pack_available_at <= now()
             AND free_pack_notified = false"""
    )


async def mark_free_pack_notified(user_id: int) -> None:
    pool = await get_pool()
    await pool.execute("UPDATE users SET free_pack_notified = true WHERE id = $1", user_id)


async def get_active_packs() -> list[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetch("SELECT * FROM packs WHERE is_active = true ORDER BY sort_order")


async def get_all_user_telegram_ids() -> list[int]:
    pool = await get_pool()
    rows = await pool.fetch("SELECT telegram_id FROM users WHERE is_banned = false")
    return [r["telegram_id"] for r in rows]
