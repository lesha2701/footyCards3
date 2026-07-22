import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import db
from config import get_bot_settings
from handlers import admin as admin_handlers
from handlers import user as user_handlers
from services.daily_reminder import run_daily_reward_reminder
from services.notifier import run_notification_dispatcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("footycards.bot")

settings = get_bot_settings()


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(admin_handlers.router)
    dp.include_router(user_handlers.router)
    return dp


async def run_polling() -> None:
    bot = Bot(token=settings.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()

    await db.get_pool()
    background_tasks = [
        asyncio.create_task(run_notification_dispatcher(bot)),
        asyncio.create_task(run_daily_reward_reminder(bot)),
    ]

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Starting bot in polling mode")
        await dp.start_polling(bot)
    finally:
        for task in background_tasks:
            task.cancel()
        await db.close_pool()
        await bot.session.close()


async def run_webhook() -> None:
    from aiohttp import web
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

    bot = Bot(token=settings.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()

    await db.get_pool()
    asyncio.create_task(run_notification_dispatcher(bot))
    asyncio.create_task(run_daily_reward_reminder(bot))

    await bot.set_webhook(settings.bot_webhook_url, secret_token=settings.bot_webhook_secret, drop_pending_updates=True)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=settings.bot_webhook_secret).register(app, path="/bot/webhook")
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.bot_webhook_port)
    logger.info("Starting bot in webhook mode on port %s", settings.bot_webhook_port)
    await site.start()

    try:
        await asyncio.Event().wait()
    finally:
        await db.close_pool()
        await bot.session.close()


def main() -> None:
    if settings.bot_mode == "webhook":
        asyncio.run(run_webhook())
    else:
        asyncio.run(run_polling())


if __name__ == "__main__":
    main()
