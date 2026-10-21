"""«Неделя мини-игры»: one solo mini-game a week (GameConfig.weekly_cup_games,
by rotation) with a leaderboard of the sum of each player's
`weekly_cup_best_of` best games finished that week (local Monday–Sunday).

Points come from the finished GameSession rows — nothing new is written
while playing: Memory counts its score, Пенальти its goals (+ a win bonus),
the others the coins the game earned (before the daily reward cap). Players
whose rewards are blocked or who are banned are left out.

No scheduler: the first read after a week ends writes that week's results
once (the WeeklyCupWeek row is locked and `settled_at` set) and notifies the
prize winners; each claims the prize (unique result row, user lock)."""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models.enums import GameSessionStatus, GameType, NotificationType, TransactionType
from app.models.game import GameSession
from app.models.user import User
from app.models.weekly_event import WeeklyCupResult, WeeklyCupWeek
from app.services.club_league_service import week_bounds, week_start_for
from app.services.game_config_service import get_config
from app.services.notification_service import notify
from app.services.wallet_service import credit_coins, lock_user_for_update

TOP_SHOWN = 20

# key -> (game type, title, page, what one point is)
GAMES: dict[str, tuple[GameType, str, str, str]] = {
    "penalty": (GameType.penalty, "Пенальти", "/play/penalty", "10 за гол, +30 за победу"),
    "free_kick": (GameType.free_kick, "Штрафной удар", "/play/free-kick", "монеты за удары"),
    "memory": (GameType.memory_sequence, "Memory", "/play/memory", "очки игры"),
    "saboteur": (GameType.saboteur, "Футбольный фанат", "/play/saboteur", "монеты за пройденный путь"),
    "pairs": (GameType.card_pairs, "Найди пару", "/play/pairs", "монеты за игру"),
}
FINISHED = (GameSessionStatus.won, GameSessionStatus.lost, GameSessionStatus.rewarded)


def _points(game: str):
    if game == "memory":
        return GameSession.score
    if game == "penalty":
        mine = GameSession.server_state["player_score"].as_integer()
        theirs = GameSession.server_state["bot_score"].as_integer()
        return func.coalesce(mine, 0) * 10 + case((mine > theirs, 30), else_=0)
    return GameSession.reward_coins


def game_of_week(week: date, config) -> str:
    games = [g for g in (config.weekly_cup_games or []) if g in GAMES] or ["penalty"]
    return games[(week.toordinal() // 7) % len(games)]


async def _week_row(db: AsyncSession, week: date, config) -> WeeklyCupWeek:
    row = await db.get(WeeklyCupWeek, week)
    if row is not None:
        return row
    try:
        async with db.begin_nested():
            db.add(WeeklyCupWeek(week_start=week, game=game_of_week(week, config)))
    except IntegrityError:
        pass
    await db.commit()
    return await db.get(WeeklyCupWeek, week)


async def standings(db: AsyncSession, week: date, game: str, best_of: int, limit: Optional[int] = None) -> list[dict]:
    """[{user_id, points, games}] best first (ties: fewer games, then who got there first)."""
    start, end = week_bounds(week)
    game_type = GAMES[game][0]
    pts = _points(game).label("pts")
    ranked = (
        select(
            GameSession.user_id.label("uid"), pts, GameSession.finished_at.label("at"),
            func.row_number().over(partition_by=GameSession.user_id, order_by=(_points(game).desc(), GameSession.id)).label("rn"),
        )
        .join(User, User.id == GameSession.user_id)
        .where(
            GameSession.game_type == game_type, GameSession.status.in_(FINISHED),
            GameSession.finished_at >= start, GameSession.finished_at < end,
            User.is_banned.is_(False), User.game_rewards_blocked.is_(False),
        )
    ).subquery()
    stmt = (
        select(ranked.c.uid, func.sum(ranked.c.pts).label("points"), func.count().label("games"), func.max(ranked.c.at).label("last"))
        .where(ranked.c.rn <= max(1, best_of))
        .group_by(ranked.c.uid)
        .order_by(func.sum(ranked.c.pts).desc(), func.count(), func.max(ranked.c.at), ranked.c.uid)
    )
    if limit:
        stmt = stmt.limit(limit)
    return [{"user_id": uid, "points": int(points or 0), "games": int(games)} for uid, points, games, _ in (await db.execute(stmt)).all()]


async def settle(db: AsyncSession, week: date) -> bool:
    """Writes a finished week's results once. True if it did now."""
    config = await get_config(db)
    if week_bounds(week)[1] > datetime.now(timezone.utc):
        return False
    row = await db.get(WeeklyCupWeek, week)
    if row is None or row.settled_at is not None:
        return False  # nobody looked at the cup that week — nothing to settle
    row = (await db.execute(
        select(WeeklyCupWeek).where(WeeklyCupWeek.week_start == week).with_for_update().execution_options(populate_existing=True)
    )).scalar_one()
    if row.settled_at is not None:
        return False
    prizes = [int(p) for p in (config.weekly_cup_prizes or [])]
    title = GAMES[row.game][1] if row.game in GAMES else row.game
    for place, entry in enumerate(await standings(db, week, row.game, config.weekly_cup_best_of), start=1):
        if entry["points"] <= 0:
            break
        prize = prizes[place - 1] if place <= len(prizes) else 0
        db.add(WeeklyCupResult(week_start=week, user_id=entry["user_id"], place=place, points=entry["points"],
                               games=entry["games"], prize_coins=prize))
        if prize > 0:
            await notify(db, entry["user_id"], NotificationType.weekly_cup_result, f"🏆 Неделя: {title} — {place} место",
                         f"Твой приз — {prize} монет. Забери его на странице недели")
    row.settled_at = datetime.now(timezone.utc)
    await db.commit()
    return True


async def get_view(db: AsyncSession, user: User) -> dict:
    config = await get_config(db)
    week = week_start_for()
    last_week = week - timedelta(days=7)
    await settle(db, last_week)
    row = await _week_row(db, week, config) if config.weekly_cup_enabled else None
    game = row.game if row else game_of_week(week, config)
    gtype, title, path, unit = GAMES.get(game, GAMES["penalty"])
    table = await standings(db, week, game, config.weekly_cup_best_of) if row else []
    names = {u.id: u for u in (await db.execute(
        select(User).where(User.id.in_([e["user_id"] for e in table[:TOP_SHOWN]] or [0]))
    )).scalars()}
    me = next(((i + 1, e) for i, e in enumerate(table) if e["user_id"] == user.id), None)
    prizes = [int(p) for p in (config.weekly_cup_prizes or [])]
    last = (await db.execute(
        select(WeeklyCupResult).where(WeeklyCupResult.user_id == user.id, WeeklyCupResult.week_start == last_week)
    )).scalar_one_or_none()
    last_row = await db.get(WeeklyCupWeek, last_week)
    unclaimed = (await db.execute(
        select(func.coalesce(func.sum(WeeklyCupResult.prize_coins), 0)).where(
            WeeklyCupResult.user_id == user.id, WeeklyCupResult.claimed_at.is_(None), WeeklyCupResult.prize_coins > 0,
        )
    )).scalar_one()
    return {
        "enabled": bool(config.weekly_cup_enabled),
        "week_start": week, "ends_at": week_bounds(week)[1],
        "game": game, "title": title, "path": path, "unit": unit,
        "best_of": config.weekly_cup_best_of, "prizes": prizes, "participants": len(table),
        "me": {"place": me[0], "points": me[1]["points"], "games": me[1]["games"]} if me else None,
        "top": [
            {"place": i + 1, "user_id": e["user_id"], "name": _name(names.get(e["user_id"])), "points": e["points"],
             "games": e["games"], "prize": prizes[i] if i < len(prizes) else 0, "is_me": e["user_id"] == user.id}
            for i, e in enumerate(table[:TOP_SHOWN])
        ],
        "last_week": {
            "title": GAMES[last_row.game][1] if last_row and last_row.game in GAMES else "",
            "place": last.place, "points": last.points, "prize": last.prize_coins, "claimed": last.claimed_at is not None,
        } if last else None,
        "unclaimed_coins": int(unclaimed),
    }


async def claim(db: AsyncSession, user: User) -> dict:
    """Every unclaimed prize at once."""
    locked = await lock_user_for_update(db, user.id)
    rows = (await db.execute(
        select(WeeklyCupResult).where(
            WeeklyCupResult.user_id == locked.id, WeeklyCupResult.claimed_at.is_(None), WeeklyCupResult.prize_coins > 0,
        ).with_for_update().execution_options(populate_existing=True)
    )).scalars().all()
    if not rows:
        raise ConflictError("Призов пока нет")
    now = datetime.now(timezone.utc)
    total = 0
    for r in rows:
        r.claimed_at = now
        total += r.prize_coins
        await credit_coins(db, locked, r.prize_coins, TransactionType.weekly_cup_prize, f"Неделя мини-игры: {r.place} место",
                           related_object_type="weekly_cup_result", related_object_id=r.id)
    await db.commit()
    await db.refresh(locked)
    return {"coins": total, "new_balance": locked.balance}


def _name(user: Optional[User]) -> str:
    return (user.first_name or user.username or "Игрок") if user else "Игрок"
