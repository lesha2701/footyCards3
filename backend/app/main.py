from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.routers import (
    achievements,
    admin_dashboard,
    admin_games,
    admin_log,
    admin_packs,
    admin_players,
    admin_trades,
    admin_users,
    auth,
    collection,
    daily_rewards,
    games,
    leaderboard,
    lineups,
    matches,
    notifications,
    packs,
    players,
    profile,
    trades,
    users,
)

settings = get_settings()

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
for rarity in ("common", "rare", "epic", "legendary", "placeholder", "packs"):
    (STATIC_DIR / "players" / rarity if rarity != "packs" else STATIC_DIR / "packs").mkdir(
        parents=True, exist_ok=True
    )

app = FastAPI(
    title="Football Cards API",
    version="1.0.0",
    description="Telegram Mini App backend for collecting football cards.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(achievements.router, prefix=API_PREFIX)
app.include_router(players.router, prefix=API_PREFIX)
app.include_router(collection.router, prefix=API_PREFIX)
app.include_router(packs.router, prefix=API_PREFIX)
app.include_router(games.router, prefix=API_PREFIX)
app.include_router(lineups.router, prefix=API_PREFIX)
app.include_router(matches.router, prefix=API_PREFIX)
app.include_router(trades.router, prefix=API_PREFIX)
app.include_router(daily_rewards.router, prefix=API_PREFIX)
app.include_router(profile.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(leaderboard.router, prefix=API_PREFIX)
app.include_router(notifications.router, prefix=API_PREFIX)
app.include_router(admin_dashboard.router, prefix=API_PREFIX)
app.include_router(admin_users.router, prefix=API_PREFIX)
app.include_router(admin_players.router, prefix=API_PREFIX)
app.include_router(admin_packs.router, prefix=API_PREFIX)
app.include_router(admin_trades.router, prefix=API_PREFIX)
app.include_router(admin_games.router, prefix=API_PREFIX)
app.include_router(admin_log.router, prefix=API_PREFIX)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "environment": settings.environment}
