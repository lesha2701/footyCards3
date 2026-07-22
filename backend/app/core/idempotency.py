from typing import Optional

from fastapi import Header


async def idempotency_key(x_idempotency_key: Optional[str] = Header(default=None)) -> Optional[str]:
    """Extracts the client-supplied Idempotency-Key header.

    Actual deduplication is enforced per-domain via DB unique constraints
    (e.g. pack_openings.(user_id, idempotency_key), daily_rewards.(user_id, reward_date)),
    which is safe even under concurrent requests, unlike an in-memory cache.
    """
    return x_idempotency_key
