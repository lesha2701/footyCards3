from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

import db
from config import get_bot_settings
from keyboards import invite_keyboard, open_app_keyboard

router = Router(name="user")
settings = get_bot_settings()

HELP_TEXT = (
    "⚽ <b>FootyCards</b> — коллекционируй футболистов, открывай паки и играй!\n\n"
    "<b>Команды:</b>\n"
    "/start — открыть игру\n"
    "/profile — показать свой профиль\n"
    "/help — это сообщение\n\n"
    "Нажми кнопку ниже, чтобы открыть приложение."
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    payload = message.text.split(maxsplit=1)[1] if message.text and " " in message.text else None

    text = (
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Добро пожаловать в <b>FootyCards</b> — собирай карточки футболистов, "
        "открывай паки, играй в мини-игры и обменивайся карточками с друзьями.\n\n"
        "Нажми кнопку ниже, чтобы начать 👇"
    )

    keyboard = open_app_keyboard()
    if payload and payload.startswith("ref_"):
        text += "\n\n🎉 Ты пришёл по приглашению друга!"
        referrer_id = payload[len("ref_"):]
        if referrer_id.isdigit():
            keyboard = open_app_keyboard(query=f"?ref={referrer_id}")

    await message.answer(text, reply_markup=keyboard)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=open_app_keyboard())


@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    user = await db.get_user_by_telegram_id(message.from_user.id)
    if user is None:
        await message.answer(
            "Ты ещё не зарегистрирован. Открой приложение, чтобы создать профиль 👇",
            reply_markup=open_app_keyboard(),
        )
        return

    text = (
        f"👤 <b>{user['first_name'] or user['username'] or 'Игрок'}</b>\n\n"
        f"💰 Баланс: {user['balance']} монет\n"
        f"⭐ Уровень: {user['level']}\n"
        f"🏆 Рейтинг Card Arena: {user['arena_rating']}\n"
        f"⚔️ Матчи: {user['matches_won']}П / {user['matches_drawn']}Н / {user['matches_lost']}П\n"
        f"🧠 Рекорд Memory Sequence: {user['memory_best_score']}\n"
    )
    await message.answer(text, reply_markup=open_app_keyboard("/profile"))


@router.message(Command("invite"))
async def cmd_invite(message: Message) -> None:
    deep_link = f"https://t.me/{settings.telegram_bot_username}?start=ref_{message.from_user.id}"
    await message.answer(
        f"Пригласи друзей в FootyCards!\n\n🔗 {deep_link}", reply_markup=invite_keyboard(deep_link)
    )
