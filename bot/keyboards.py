from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from config import get_bot_settings

settings = get_bot_settings()


def open_app_keyboard(path: str = "", query: str = "") -> InlineKeyboardMarkup:
    url = settings.mini_app_url.rstrip("/") + path + query
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⚽ Открыть FootyCards", web_app=WebAppInfo(url=url))]]
    )


def invite_keyboard(deep_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📨 Поделиться приглашением", url=f"https://t.me/share/url?url={deep_link}")]]
    )
