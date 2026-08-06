import logging
from datetime import datetime, timezone

import aiohttp
from aiogram import F, Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Message

from config import get_bot_settings

router = Router(name="chat_pack")
settings = get_bot_settings()
logger = logging.getLogger("footycards.bot.chat_pack")

# "Chat mode": this is the only thing the bot responds to in group chats
# (handlers/user.py restricts its commands to private chats). "вкарта" is
# plain text, not a slash command, so it only reaches the bot in groups
# where Group Privacy is disabled for this bot in @BotFather.
router.message.filter(F.chat.type.in_({"group", "supergroup"}))

_HEADERS = {"X-Internal-Secret": settings.internal_api_secret}
_TIMEOUT = aiohttp.ClientTimeout(total=8)

TRIGGER = "вкарта"

RARITY_LABELS = {"common": "Обычная", "rare": "Редкая", "epic": "Эпическая", "legendary": "Легендарная"}
RARITY_EMOJI = {"common": "⚪️", "rare": "🔵", "epic": "🟣", "legendary": "🟡"}
POSITION_LABELS = {
    "GK": "Вратарь", "LB": "Левый защитник", "CB": "Центральный защитник", "RB": "Правый защитник",
    "CDM": "Опорный полузащитник", "CM": "Центральный полузащитник", "CAM": "Атакующий полузащитник",
    "LM": "Левый полузащитник", "RM": "Правый полузащитник", "LW": "Левый нападающий",
    "RW": "Правый нападающий", "ST": "Нападающий",
}


def _static_url(image_path: str) -> str:
    # /static/ is proxied on the same public host as mini_app_url (see
    # nginx/nginx.conf), so Telegram's servers can fetch it from there.
    return f"{settings.mini_app_url.rstrip('/')}/static/{image_path}"


def _open_bot_keyboard() -> InlineKeyboardMarkup:
    # web_app buttons are only allowed in private chats — Telegram rejects
    # them on messages sent to groups — so this links into a private chat
    # with the bot instead, where the real "Открыть VICTOR FC" web_app
    # button is shown (see the "chatpack" start payload in handlers/user.py).
    url = f"https://t.me/{settings.telegram_bot_username}?start=chatpack"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚽ Перейти в VICTOR FC", url=url)]])


def _format_card(item: dict) -> str:
    card = item["card"]
    player = card["player"]
    rarity = player["rarity"]
    position_label = POSITION_LABELS.get(player["position"], player["position"])
    return (
        f"{RARITY_EMOJI.get(rarity, '⚪️')} <b>{player['display_name']}</b> ({RARITY_LABELS.get(rarity, rarity)})\n"
        f"⚽ {position_label} · {player['club']}, {player['country']}\n"
        f"📊 Рейтинг {player['rating']} (АТК {player['attack_rating']} / ЗАЩ {player['defense_rating']}) · #{card['serial_number']}"
    )


def _format_cooldown_left(available_at_iso: str) -> str:
    available_at = datetime.fromisoformat(available_at_iso)
    if available_at.tzinfo is None:
        available_at = available_at.replace(tzinfo=timezone.utc)
    total_minutes = max(int((available_at - datetime.now(timezone.utc)).total_seconds() // 60), 0)
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours} ч {minutes} мин"
    if hours:
        return f"{hours} ч"
    return f"{minutes} мин"


async def _send_result(message: Message, first_name: str, cards: list[dict]) -> None:
    intro = f"🎉 {first_name} открыл карту в VICTOR FC!"
    outro = "Заходи попозже за новой картой!"
    cards_text = "\n\n".join(_format_card(item) for item in cards)
    image_paths = [item["card"]["player"].get("image_path") for item in cards]

    try:
        if len(cards) == 1 and image_paths[0]:
            await message.reply_photo(
                photo=_static_url(image_paths[0]),
                caption=f"{intro}\n\n{cards_text}\n\n{outro}",
                reply_markup=_open_bot_keyboard(),
            )
            return
        if all(image_paths):
            media = [
                InputMediaPhoto(media=_static_url(path), caption=_format_card(item), parse_mode="HTML")
                for item, path in zip(cards, image_paths)
            ]
            await message.reply_media_group(media=media)
            await message.answer(f"{intro}\n\n{outro}", reply_markup=_open_bot_keyboard())
            return
    except Exception:
        # e.g. mini_app_url isn't publicly reachable from Telegram's servers
        # (local/dev setups) — fall back to a text-only card instead of
        # leaving the player without a response.
        logger.warning("chat-pack photo send failed, falling back to text", exc_info=True)

    await message.reply(f"{intro}\n\n{cards_text}\n\n{outro}", reply_markup=_open_bot_keyboard())


@router.message(F.text.func(lambda text: bool(text) and text.strip().casefold() == TRIGGER))
async def cmd_chat_pack(message: Message) -> None:
    user = message.from_user
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(
                f"{settings.internal_backend_url}/internal/chat-pack/open",
                json={"telegram_user_id": user.id},
                headers=_HEADERS,
            ) as resp:
                status = resp.status
                data = await resp.json()
    except Exception:
        logger.exception("chat-pack open call failed")
        await message.reply("Что-то пошло не так, попробуй ещё раз чуть позже.")
        return

    if status == 200:
        await _send_result(message, user.first_name, data["cards"])
        return

    error = data.get("error", {})

    if status == 404:
        await message.reply(
            f"{user.first_name}, ты ещё не зарегистрирован в VICTOR FC. Жми на кнопку, открой приложение "
            "и возвращайся за картой 👇",
            reply_markup=_open_bot_keyboard(),
        )
        return

    if status == 429:
        available_at = (error.get("details") or {}).get("available_at")
        left = _format_cooldown_left(available_at) if available_at else "позже"
        await message.reply(f"{user.first_name}, следующая карта будет доступна через {left}.")
        return

    logger.error("chat-pack open failed: status=%s body=%s", status, data)
    await message.reply("Не получилось открыть карту, попробуй ещё раз чуть позже.")
