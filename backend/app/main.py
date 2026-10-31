import asyncio
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.core.exceptions import register_exception_handlers
from app.core.slow_log import SlowRequestMiddleware, StallSampler, watch_event_loop
from app.routers import (
    admin_badges,
    admin_bingo,
    admin_card_collections,
    admin_card_skills,
    admin_path,
    admin_transactions,
    admin_card_upgrades,
    admin_club_packs,
    admin_clubs,
    admin_coaches,
    admin_coin_packages,
    admin_daily_rewards,
    admin_dashboard,
    admin_diamond_upgrades,
    admin_career,
    admin_games,
    admin_gifts,
    admin_leagues,
    admin_lifestyle,
    admin_club_base,
    admin_log,
    admin_equipment,
    admin_muses,
    admin_monetization,
    admin_packs,
    admin_players,
    admin_stadiums,
    admin_stars_purchases,
    admin_antifraud,
    admin_tasks,
    admin_tournaments,
    admin_trades,
    admin_auction,
    auction,
    admin_trophies,
    admin_users,
    admin_wheel,
    announcement,
    auth,
    bingo,
    blackjack,
    broadcasts,
    card_collections,
    card_skills,
    path,
    academy,
    club_base,
    career,
    club_features,
    clubs,
    player_tournaments,
    collection,
    daily_rewards,
    feature_flags,
    free_pack,
    newbie,
    streak_rewards,
    friends,
    games,
    gifts,
    internal,
    leaderboard,
    equipment,
    muses,
    events,
    monetization,
    leagues,
    lineups,
    maintenance,
    lifestyle,
    magnate,
    matches,
    manager,
    my_player,
    player_career,
    notifications,
    packs,
    penalty_matches,
    players,
    profile,
    share,
    stratego,
    mordoboi,
    kontra,
    weekly_top,
    card_offers,
    tactico,
    tasks,
    trades,
    users,
    wallet,
    wheel,
)

settings = get_settings()

if settings.environment == "production" and settings.dev_mode:
    raise RuntimeError(
        "DEV_MODE must be disabled (DEV_MODE=false) when ENVIRONMENT=production — "
        "it lets any request authenticate via the X-Dev-Mode header, bypassing Telegram auth."
    )

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
for rarity in ("common", "rare", "epic", "legendary", "placeholder", "packs"):
    (STATIC_DIR / "players" / rarity if rarity != "packs" else STATIC_DIR / "packs").mkdir(
        parents=True, exist_ok=True
    )

_docs_enabled = settings.environment != "production"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    sampler = StallSampler(threading.get_ident()).start()
    watcher = asyncio.create_task(watch_event_loop(sampler=sampler))
    try:
        yield
    finally:
        watcher.cancel()
        sampler.stop()


app = FastAPI(
    title="VICTOR FC API",
    version="1.0.0",
    description="Telegram Mini App backend for collecting football cards.",
    docs_url="/api/docs" if _docs_enabled else None,
    redoc_url="/api/redoc" if _docs_enabled else None,
    openapi_url="/api/openapi.json" if _docs_enabled else None,
    lifespan=lifespan,
)

register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SlowRequestMiddleware)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(tasks.router, prefix=API_PREFIX)
app.include_router(players.router, prefix=API_PREFIX)
app.include_router(card_collections.router, prefix=API_PREFIX)
app.include_router(collection.router, prefix=API_PREFIX)
app.include_router(card_skills.router, prefix=API_PREFIX)
app.include_router(path.router, prefix=API_PREFIX)
app.include_router(academy.router, prefix=API_PREFIX)
app.include_router(club_base.router, prefix=API_PREFIX)
app.include_router(bingo.router, prefix=API_PREFIX)
app.include_router(packs.router, prefix=API_PREFIX)
app.include_router(free_pack.router, prefix=API_PREFIX)
app.include_router(newbie.router, prefix=API_PREFIX)
app.include_router(streak_rewards.router, prefix=API_PREFIX)
app.include_router(games.router, prefix=API_PREFIX)
app.include_router(feature_flags.router, prefix=API_PREFIX)
app.include_router(gifts.router, prefix=API_PREFIX)
app.include_router(lineups.router, prefix=API_PREFIX)
app.include_router(career.router, prefix=API_PREFIX)
app.include_router(friends.router, prefix=API_PREFIX)
app.include_router(manager.router, prefix=API_PREFIX)
app.include_router(my_player.router, prefix=API_PREFIX)
app.include_router(lifestyle.router, prefix=API_PREFIX)
app.include_router(player_career.router, prefix=API_PREFIX)
app.include_router(maintenance.router, prefix=API_PREFIX)
app.include_router(broadcasts.router, prefix=API_PREFIX)
app.include_router(announcement.router, prefix=API_PREFIX)
app.include_router(matches.router, prefix=API_PREFIX)
app.include_router(penalty_matches.router, prefix=API_PREFIX)
app.include_router(tactico.router, prefix=API_PREFIX)
app.include_router(stratego.router, prefix=API_PREFIX)
app.include_router(mordoboi.router, prefix=API_PREFIX)
app.include_router(kontra.router, prefix=API_PREFIX)
app.include_router(weekly_top.router, prefix=API_PREFIX)
app.include_router(card_offers.router, prefix=API_PREFIX)
app.include_router(card_offers.admin_router, prefix=API_PREFIX)
app.include_router(magnate.router, prefix=API_PREFIX)
app.include_router(trades.router, prefix=API_PREFIX)
app.include_router(auction.router, prefix=API_PREFIX)
app.include_router(daily_rewards.router, prefix=API_PREFIX)
app.include_router(wheel.router, prefix=API_PREFIX)
app.include_router(blackjack.router, prefix=API_PREFIX)
app.include_router(profile.router, prefix=API_PREFIX)
app.include_router(share.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(leaderboard.router, prefix=API_PREFIX)
app.include_router(leagues.router, prefix=API_PREFIX)
app.include_router(club_features.router, prefix=API_PREFIX)
app.include_router(clubs.router, prefix=API_PREFIX)
app.include_router(player_tournaments.router, prefix=API_PREFIX)
app.include_router(notifications.router, prefix=API_PREFIX)
app.include_router(admin_dashboard.router, prefix=API_PREFIX)
app.include_router(admin_users.router, prefix=API_PREFIX)
app.include_router(admin_players.router, prefix=API_PREFIX)
app.include_router(admin_coaches.router, prefix=API_PREFIX)
app.include_router(admin_stadiums.router, prefix=API_PREFIX)
app.include_router(admin_packs.router, prefix=API_PREFIX)
app.include_router(admin_daily_rewards.router, prefix=API_PREFIX)
app.include_router(admin_badges.router, prefix=API_PREFIX)
app.include_router(admin_coin_packages.router, prefix=API_PREFIX)
app.include_router(admin_card_collections.router, prefix=API_PREFIX)
app.include_router(admin_card_upgrades.router, prefix=API_PREFIX)
app.include_router(admin_card_skills.router, prefix=API_PREFIX)
app.include_router(admin_path.router, prefix=API_PREFIX)
app.include_router(admin_transactions.router, prefix=API_PREFIX)
app.include_router(admin_diamond_upgrades.router, prefix=API_PREFIX)
app.include_router(admin_bingo.router, prefix=API_PREFIX)
app.include_router(admin_club_packs.router, prefix=API_PREFIX)
app.include_router(admin_clubs.router, prefix=API_PREFIX)
app.include_router(admin_tournaments.router, prefix=API_PREFIX)
app.include_router(admin_tasks.router, prefix=API_PREFIX)
app.include_router(admin_trades.router, prefix=API_PREFIX)
app.include_router(admin_auction.router, prefix=API_PREFIX)
app.include_router(admin_trophies.router, prefix=API_PREFIX)
app.include_router(admin_gifts.router, prefix=API_PREFIX)
app.include_router(admin_leagues.router, prefix=API_PREFIX)
app.include_router(admin_lifestyle.router, prefix=API_PREFIX)
app.include_router(admin_club_base.router, prefix=API_PREFIX)
app.include_router(admin_wheel.router, prefix=API_PREFIX)
app.include_router(admin_games.router, prefix=API_PREFIX)
app.include_router(admin_career.router, prefix=API_PREFIX)
app.include_router(admin_log.router, prefix=API_PREFIX)
app.include_router(admin_stars_purchases.router, prefix=API_PREFIX)
app.include_router(admin_antifraud.router, prefix=API_PREFIX)
app.include_router(internal.router, prefix=API_PREFIX)
app.include_router(wallet.router, prefix=API_PREFIX)
app.include_router(monetization.router, prefix=API_PREFIX)
app.include_router(equipment.router, prefix=API_PREFIX)
app.include_router(muses.router, prefix=API_PREFIX)
app.include_router(events.router, prefix=API_PREFIX)
app.include_router(events.admin_router, prefix=API_PREFIX)
app.include_router(admin_equipment.router, prefix=API_PREFIX)
app.include_router(admin_muses.router, prefix=API_PREFIX)
app.include_router(admin_monetization.router, prefix=API_PREFIX)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "environment": settings.environment}


@app.get("/api/health/deep")
async def deep_health_check(db: AsyncSession = Depends(get_db)):
    """For the bot's watchdog: the app answers *and* reaches the database."""
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}
