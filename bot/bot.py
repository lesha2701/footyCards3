import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

import db
from config import get_bot_settings
from handlers import admin as admin_handlers
from handlers import chat_pack as chat_pack_handlers
from handlers import payments as payments_handlers
from handlers import support as support_handlers
from handlers import user as user_handlers
from services.career_scheduler import (
    run_career_digest_loop,
    run_career_live_loop,
    run_career_reminder_loop,
    run_career_round_loop,
    run_club_league_loop,
    run_club_war_loop,
)
from services.daily_reminder import run_daily_reward_reminder
from services.free_pack_notifier import run_free_pack_notifier
from services.auction_scheduler import run_auction_sweep_loop
from services.magnate_scheduler import run_magnate_sweep_loop
from services.match_day_scheduler import run_match_day_sync_loop
from services.manager_scheduler import run_manager_sweep_loop
from services.weekly_top_scheduler import run_weekly_top_loop
from services.watchdog import run_watchdog_loop
from services.comeback import run_comeback_loop
from services.newbie_reminder import run_newbie_reminder_loop
from services.card_offer_scheduler import run_card_offer_reminder_loop
from services.club_base_scheduler import run_club_base_sweep_loop
from services.notifier import run_notification_dispatcher
from services.premium_subscription_check import run_premium_subscription_check
from services.stars_delivery import run_stars_payment_retry_loop
from services.player_tournament_scheduler import (
    run_player_tournament_reminder_loop,
    run_player_tournament_simulation_loop,
)
from services.tournament_scheduler import run_lineup_reminder_loop, run_simulation_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("footycards.bot")

settings = get_bot_settings()


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(admin_handlers.router)
    dp.include_router(payments_handlers.router)
    dp.include_router(support_handlers.router)
    dp.include_router(chat_pack_handlers.router)
    dp.include_router(user_handlers.router)
    return dp


def _make_bot() -> Bot:
    session = AiohttpSession(proxy=settings.telegram_proxy_url) if settings.telegram_proxy_url else None
    return Bot(token=settings.telegram_bot_token, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


async def run_polling() -> None:
    bot = _make_bot()
    dp = build_dispatcher()

    await db.get_pool()
    background_tasks = [
        asyncio.create_task(run_notification_dispatcher(bot)),
        # Daily digest is opt-in from the admin panel — see run_webhook() below.
        asyncio.create_task(run_free_pack_notifier(bot)),
        asyncio.create_task(run_daily_reward_reminder(bot)),
        asyncio.create_task(run_premium_subscription_check(bot)),
        asyncio.create_task(run_simulation_loop()),
        asyncio.create_task(run_lineup_reminder_loop()),
        asyncio.create_task(run_player_tournament_simulation_loop()),
        asyncio.create_task(run_player_tournament_reminder_loop()),
        asyncio.create_task(run_club_war_loop()),
        asyncio.create_task(run_career_round_loop()),
        asyncio.create_task(run_career_reminder_loop()),
        asyncio.create_task(run_career_live_loop()),
        asyncio.create_task(run_career_digest_loop()),
        asyncio.create_task(run_club_league_loop()),
        asyncio.create_task(run_magnate_sweep_loop()),
        asyncio.create_task(run_manager_sweep_loop()),
        asyncio.create_task(run_match_day_sync_loop()),
        asyncio.create_task(run_club_base_sweep_loop()),
        asyncio.create_task(run_weekly_top_loop()),
        asyncio.create_task(run_auction_sweep_loop()),
        asyncio.create_task(run_stars_payment_retry_loop(bot)),
        asyncio.create_task(run_watchdog_loop(bot)),
        asyncio.create_task(run_comeback_loop(bot)),
        asyncio.create_task(run_newbie_reminder_loop(bot)),
        asyncio.create_task(run_card_offer_reminder_loop()),
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

    bot = _make_bot()
    dp = build_dispatcher()

    await db.get_pool()
    asyncio.create_task(run_notification_dispatcher(bot))
    # Daily digest: off by default (the old reminder was disabled by request);
    # only runs once an admin enables it in Игры → Напоминание ботом.
    asyncio.create_task(run_free_pack_notifier(bot))
    asyncio.create_task(run_daily_reward_reminder(bot))
    asyncio.create_task(run_premium_subscription_check(bot))
    asyncio.create_task(run_simulation_loop())
    asyncio.create_task(run_lineup_reminder_loop())
    asyncio.create_task(run_player_tournament_simulation_loop())
    asyncio.create_task(run_player_tournament_reminder_loop())
    asyncio.create_task(run_career_round_loop())
    asyncio.create_task(run_career_reminder_loop())
    asyncio.create_task(run_career_live_loop())
    asyncio.create_task(run_career_digest_loop())
    asyncio.create_task(run_club_league_loop())
    asyncio.create_task(run_magnate_sweep_loop())
    asyncio.create_task(run_manager_sweep_loop())
    asyncio.create_task(run_match_day_sync_loop())
    asyncio.create_task(run_club_base_sweep_loop())
    asyncio.create_task(run_weekly_top_loop())
    asyncio.create_task(run_auction_sweep_loop())
    asyncio.create_task(run_stars_payment_retry_loop(bot))
    asyncio.create_task(run_watchdog_loop(bot))
    asyncio.create_task(run_comeback_loop(bot))
    asyncio.create_task(run_newbie_reminder_loop(bot))
    asyncio.create_task(run_card_offer_reminder_loop())

    await bot.set_webhook(settings.bot_webhook_url, secret_token=settings.bot_webhook_secret, drop_pending_updates=True)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=settings.bot_webhook_secret).register(app, path="/bot/webhook")
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    # Every address, IPv4 and IPv6: nginx reaches `bot` by either on the
    # prod network (0.0.0.0 refused the IPv6 one).
    site = web.TCPSite(runner, None, settings.bot_webhook_port)
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
