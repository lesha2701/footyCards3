import httpx

from app.config import get_settings

settings = get_settings()

_MEMBER_STATUSES = {"member", "administrator", "creator"}


async def check_channel_membership(telegram_user_id: int, channel_username: str) -> bool:
    """Checks whether a Telegram user is a member of a channel via the Bot API.

    Requires the bot to be an admin of the channel. Fails closed (returns
    False) on any non-ok response, e.g. the bot isn't an admin there or the
    channel doesn't exist.
    """
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getChatMember"
    async with httpx.AsyncClient(timeout=10, proxy=settings.telegram_proxy_url or None) as client:
        resp = await client.get(url, params={"chat_id": channel_username, "user_id": telegram_user_id})
    data = resp.json()
    if not data.get("ok"):
        return False
    return data["result"]["status"] in _MEMBER_STATUSES
