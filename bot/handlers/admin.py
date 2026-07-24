from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message

import db
from config import get_bot_settings
from keyboards import open_app_keyboard

router = Router(name="admin")
settings = get_bot_settings()


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in settings.admin_ids


async def _resolve_target(arg: str):
    arg = arg.lstrip("@")
    if arg.isdigit():
        return await db.get_user_by_telegram_id(int(arg))
    return await db.get_user_by_username(arg)


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ У тебя нет доступа к административным командам.")
        return
    await message.answer(
        "🛠 <b>Панель администратора</b>\n\n"
        "/give_coins @user 100 [причина] — выдать монеты\n"
        "/give_card @user Имя Игрока — выдать карточку\n"
        "/ban @user — заблокировать\n"
        "/unban @user — разблокировать\n"
        "/stats — статистика проекта\n\n"
        "Полная административная панель доступна в приложении по кнопке ниже.",
        reply_markup=open_app_keyboard("/admin"),
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ У тебя нет доступа к административным командам.")
        return
    stats = await db.get_stats()
    text = (
        "📊 <b>Статистика FootyCards</b>\n\n"
        f"👥 Пользователей: {stats['total_users']}\n"
        f"🃏 Выдано карточек: {stats['total_cards']}\n"
        f"📦 Открыто паков: {stats['total_packs']}\n"
        f"🔄 Обменов: {stats['total_trades']}\n"
        f"💰 Монет в обороте: {stats['coins_in_circulation']}\n"
    )
    await message.answer(text)


@router.message(Command("give_coins"))
async def cmd_give_coins(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ У тебя нет доступа к административным командам.")
        return
    parts = (message.text or "").split(maxsplit=3)
    if len(parts) < 3 or not parts[2].lstrip("-").isdigit():
        await message.answer("Использование: /give_coins @username 100 [причина]")
        return

    target = await _resolve_target(parts[1])
    if target is None:
        await message.answer("Пользователь не найден.")
        return

    amount = int(parts[2])
    description = parts[3] if len(parts) > 3 else "Выдано администратором через бота"
    updated = await db.give_coins(target["telegram_id"], amount, description)
    await message.answer(f"✅ Баланс {target['username'] or target['telegram_id']} теперь: {updated['balance']} монет.")


@router.message(Command("give_card"))
async def cmd_give_card(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ У тебя нет доступа к административным командам.")
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Использование: /give_card @username Имя Игрока")
        return

    target = await _resolve_target(parts[1])
    if target is None:
        await message.answer("Пользователь не найден.")
        return

    player = await db.find_player_by_name(parts[2])
    if player is None:
        await message.answer("Футболист с таким именем не найден.")
        return

    await db.give_card(target["telegram_id"], player["id"])
    await message.answer(f"✅ Карточка «{player['display_name']}» выдана пользователю {target['username'] or target['telegram_id']}.")


@router.message(Command("ban"))
async def cmd_ban(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ У тебя нет доступа к административным командам.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /ban @username")
        return
    target = await _resolve_target(parts[1])
    if target is None:
        await message.answer("Пользователь не найден.")
        return
    await db.set_ban_status(target["telegram_id"], True)
    await message.answer(f"🚫 Пользователь {target['username'] or target['telegram_id']} заблокирован.")


@router.message(Command("unban"))
async def cmd_unban(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ У тебя нет доступа к административным командам.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /unban @username")
        return
    target = await _resolve_target(parts[1])
    if target is None:
        await message.answer("Пользователь не найден.")
        return
    await db.set_ban_status(target["telegram_id"], False)
    await message.answer(f"✅ Пользователь {target['username'] or target['telegram_id']} разблокирован.")


@router.message(Command("announce_pack"))
async def cmd_announce_pack(message: Message, bot: Bot) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ У тебя нет доступа к административным командам.")
        return
    parts = (message.text or "").split(maxsplit=1)
    packs = await db.get_active_packs()
    if len(parts) < 2:
        listing = "\n".join(f"#{p['id']} {p['name']}" for p in packs) or "Нет активных паков."
        await message.answer(f"Использование: /announce_pack <id>\n\nАктивные паки:\n{listing}")
        return

    try:
        pack_id = int(parts[1])
    except ValueError:
        await message.answer("ID пака должен быть числом.")
        return

    pack = next((p for p in packs if p["id"] == pack_id), None)
    if pack is None:
        await message.answer("Пак не найден среди активных.")
        return

    user_ids = await db.get_all_user_telegram_ids()
    sent = 0
    for telegram_id in user_ids:
        try:
            await bot.send_message(
                telegram_id,
                f"🎉 Специальный пак «{pack['name']}»!\n{pack['description']}\n\nЦена: {pack['price']} монет.",
                reply_markup=open_app_keyboard("/packs"),
            )
            sent += 1
        except Exception:  # noqa: BLE001 - user may have blocked the bot; skip and continue
            continue
    await message.answer(f"📣 Объявление отправлено {sent} пользователям.")
