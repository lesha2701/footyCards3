"""Guest mode (Bot API 10.0): «@бот …» in any chat, without the bot being a
member. Telegram sends one `guest_message` per mention and the bot gets one
reply, as an inline result via answerGuestQuery — no chat history, no
web_app buttons (url buttons into the bot instead).

    @бот вкарта   — the chat card («вкарта»), same cooldown as in groups
    @бот вызов    — a challenge to the chat with the caller's referral link
    @бот <игрок>  — that player's card
    @бот          — what the bot can do here

Guest Mode is switched on for the bot in @BotFather (bot settings → Guest Mode).
"""
import logging
import re
import uuid
from typing import Optional

from aiogram import Bot, Router
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    LinkPreviewOptions,
    Message,
)

import db
from config import get_bot_settings
from handlers.chat_pack import (
    POSITION_LABELS,
    RARITY_EMOJI,
    RARITY_LABELS,
    format_card,
    format_cooldown_left,
    request_chat_pack,
    static_url,
)

router = Router(name="guest")
settings = get_bot_settings()
logger = logging.getLogger("footycards.bot.guest")

PACK_WORDS = {"вкарта", "карта", "пак", "в карта"}
CHALLENGE_WORDS = {"вызов", "дуэль", "challenge"}
HELP_WORDS = {"", "помощь", "help", "?", "что умеешь"}
MAX_QUERY = 40


def query_of(text: Optional[str], bot_username: str) -> str:
    """The mention text without «@бот» (any case) and extra spaces."""
    text = re.sub(rf"@{re.escape(bot_username)}\b", " ", text or "", flags=re.IGNORECASE)
    return " ".join(text.split())[:MAX_QUERY]


def _bot_link(payload: str) -> str:
    return f"https://t.me/{settings.telegram_bot_username}?start={payload}"


def _button(text: str, payload: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, url=_bot_link(payload))]])


def _article(title: str, text: str, keyboard: InlineKeyboardMarkup, image_path: Optional[str] = None) -> InlineQueryResultArticle:
    # The card art is .webp, which an inline photo result doesn't take (JPEG
    # only) — a large link preview of the picture above the text shows it.
    preview = (
        LinkPreviewOptions(url=static_url(image_path), prefer_large_media=True, show_above_text=True)
        if image_path else LinkPreviewOptions(is_disabled=True)
    )
    return InlineQueryResultArticle(
        id=uuid.uuid4().hex,
        title=title,
        input_message_content=InputTextMessageContent(message_text=text, link_preview_options=preview),
        reply_markup=keyboard,
    )


def help_text(name: str) -> str:
    return (
        "⚽ <b>VICTOR FC</b> — собирай карточки футболистов прямо в Telegram\n\n"
        "🃏 Открывай паки и лови легенд: Месси, Роналду, Холанд\n"
        "🎮 15+ мини-игр: пенальти, арена, менеджер клуба\n"
        "🔄 Меняйся картами с друзьями\n\n"
        "Попробуй прямо здесь:\n"
        f"• <code>@{name} вкарта</code> — открыть бесплатную карту\n"
        f"• <code>@{name} Месси</code> — найти карточку любого игрока\n"
        f"• <code>@{name} вызов</code> — позвать друзей в игру\n\n"
        "👇 Жми кнопку — первый пак в подарок"
    )


async def pack_result(message: Message) -> InlineQueryResultArticle:
    user = message.from_user
    keyboard = _button("⚽ Перейти в VICTOR FC", "chatpack")
    try:
        status, data = await request_chat_pack(user)
    except Exception:
        logger.exception("guest chat-pack open call failed")
        return _article("VICTOR FC", "Что-то пошло не так, попробуй ещё раз чуть позже.", keyboard)
    if status == 200:
        cards = data["cards"]
        text = (
            f"🎉 {user.first_name} открыл карту в VICTOR FC!\n\n"
            + "\n\n".join(format_card(item) for item in cards)
            + "\n\nЗаходи попозже за новой картой!"
        )
        return _article("Карта из чата", text, keyboard, cards[0]["card"]["player"].get("image_path"))
    if status == 429:
        available_at = ((data.get("error") or {}).get("details") or {}).get("available_at")
        left = format_cooldown_left(available_at) if available_at else "позже"
        return _article("VICTOR FC", f"{user.first_name}, следующая карта будет доступна через {left}.", keyboard)
    logger.error("guest chat-pack open failed: status=%s body=%s", status, data)
    return _article("VICTOR FC", "Не получилось открыть карту, попробуй ещё раз чуть позже.", keyboard)


def challenge_result(message: Message) -> InlineQueryResultArticle:
    user = message.from_user
    text = (
        f"⚔️ <b>{user.first_name}</b> бросает вызов этому чату в <b>VICTOR FC</b>!\n\n"
        "Собери состав из карточек футболистов и докажи, кто тут лучший тренер. "
        "Принимаешь?"
    )
    return _article("Вызов", text, _button("⚔️ Принять вызов", f"ref_{user.id}"))


async def player_result(query: str) -> InlineQueryResultArticle:
    players = await db.find_players(query)
    if not players:
        return _article(
            "Не найдено",
            f"🔎 Игрока «{query}» в VICTOR FC нет. Попробуй другое имя, например <code>Месси</code>.",
            _button("⚽ Открыть VICTOR FC", "guest"),
        )
    best = players[0]
    rarity = best["rarity"]
    item = {"card": {"serial_number": "—", "player": dict(best)}}
    lines = [format_card(item).replace(" · #—", "")]
    others = players[1:]
    if others:
        lines.append(
            "Ещё: " + ", ".join(
                f"{RARITY_EMOJI.get(p['rarity'], '⚪️')} {p['display_name']} {p['rating']}" for p in others
            )
        )
    lines.append(f"\nСобери {best['display_name']} в свою коллекцию 👇")
    title = f"{best['display_name']} · {RARITY_LABELS.get(rarity, rarity)} · "
    title += POSITION_LABELS.get(best["position"], best["position"])
    return _article(title, "\n".join(lines), _button("🃏 Собрать в VICTOR FC", "guest"), best["image_path"])


async def build_result(message: Message, bot_username: str) -> InlineQueryResultArticle:
    query = query_of(message.text or message.caption, bot_username)
    key = query.casefold()
    if key in PACK_WORDS:
        return await pack_result(message)
    if key in CHALLENGE_WORDS:
        return challenge_result(message)
    if key in HELP_WORDS:
        return _article("VICTOR FC", help_text(bot_username), _button("⚽ Открыть VICTOR FC", "guest"))
    return await player_result(query)


@router.guest_message()
async def on_guest_message(message: Message, bot: Bot) -> None:
    if not message.guest_query_id or message.from_user is None:
        return
    me = await bot.me()
    result = await build_result(message, me.username or settings.telegram_bot_username)
    try:
        await bot.answer_guest_query(guest_query_id=message.guest_query_id, result=result)
    except Exception:
        # A picture Telegram can't preview shouldn't cost the reply: retry as text only.
        logger.warning("guest answer failed, retrying without the preview", exc_info=True)
        content = result.input_message_content.model_copy(
            update={"link_preview_options": LinkPreviewOptions(is_disabled=True)}
        )
        result = result.model_copy(update={"id": uuid.uuid4().hex, "input_message_content": content})
        await bot.answer_guest_query(guest_query_id=message.guest_query_id, result=result)
