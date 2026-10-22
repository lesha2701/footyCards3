"""«Матч дня»: an admin enters a real match (teams, kickoff); players guess
the score until kickoff; once the admin enters the result every guesser is
notified and claims coins: the exact score, else the right goal difference,
else the right outcome (GameConfig.match_day_*_coins).

The reward is fixed at claim time under the user and prediction row locks
(`claimed_at` set once). A result can be corrected only while nobody has
claimed."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import NotificationType, TransactionType
from app.models.user import User
from app.models.weekly_event import MatchDayFixture, MatchDayPrediction
from app.services.game_config_service import get_config
from app.services.notification_service import notify
from app.services.wallet_service import credit_coins, lock_user_for_update

RECENT = 5
MAX_GOALS = 20


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(at: datetime) -> datetime:
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def _sign(a: int, b: int) -> int:
    return (a > b) - (a < b)


def reward_for(pred_home: int, pred_away: int, home: int, away: int, config) -> tuple[int, str]:
    if (pred_home, pred_away) == (home, away):
        return config.match_day_exact_coins, "exact"
    if pred_home - pred_away == home - away:
        return config.match_day_diff_coins, "diff"
    if _sign(pred_home, pred_away) == _sign(home, away):
        return config.match_day_outcome_coins, "outcome"
    return 0, "miss"


def _has_result(f: MatchDayFixture) -> bool:
    return f.home_score is not None and f.away_score is not None


async def _split(db: AsyncSession, fixture_id: int) -> dict:
    rows = (await db.execute(
        select(MatchDayPrediction.home, MatchDayPrediction.away).where(MatchDayPrediction.fixture_id == fixture_id)
    )).all()
    out = {"home": 0, "draw": 0, "away": 0, "total": len(rows)}
    for h, a in rows:
        out["home" if h > a else "away" if a > h else "draw"] += 1
    return out


def _fixture_out(f: MatchDayFixture, pred: Optional[MatchDayPrediction], split: Optional[dict], config, now: datetime) -> dict:
    result = _has_result(f)
    reward = kind = None
    if pred is not None and result:
        reward, kind = reward_for(pred.home, pred.away, f.home_score, f.away_score, config)
        if pred.claimed_at is not None and pred.reward_coins is not None:
            reward = pred.reward_coins
    return {
        "id": f.id, "home": f.home, "away": f.away, "league": f.league, "kickoff_at": _aware(f.kickoff_at),
        "open": _aware(f.kickoff_at) > now and not result,
        "home_score": f.home_score, "away_score": f.away_score,
        "prediction": {"home": pred.home, "away": pred.away} if pred else None,
        "reward": reward, "reward_kind": kind, "claimed": bool(pred and pred.claimed_at),
        "split": split,
    }


async def get_view(db: AsyncSession, user: User) -> dict:
    config = await get_config(db)
    now = _now()
    # The match of the day: the nearest not started; else the latest still waiting for its result.
    current = (await db.execute(
        select(MatchDayFixture).where(MatchDayFixture.kickoff_at > now, MatchDayFixture.home_score.is_(None))
        .order_by(MatchDayFixture.kickoff_at).limit(1)
    )).scalar_one_or_none() or (await db.execute(
        select(MatchDayFixture).where(MatchDayFixture.home_score.is_(None)).order_by(MatchDayFixture.kickoff_at.desc()).limit(1)
    )).scalar_one_or_none()
    recent = list((await db.execute(
        select(MatchDayFixture).where(MatchDayFixture.home_score.is_not(None))
        .order_by(MatchDayFixture.kickoff_at.desc()).limit(RECENT)
    )).scalars())
    ids = [f.id for f in ([current] if current else []) + recent]
    preds = {p.fixture_id: p for p in (await db.execute(
        select(MatchDayPrediction).where(MatchDayPrediction.user_id == user.id, MatchDayPrediction.fixture_id.in_(ids or [0]))
    )).scalars()}
    unclaimed = sum(
        1 for f in recent
        if (p := preds.get(f.id)) is not None and p.claimed_at is None
        and reward_for(p.home, p.away, f.home_score, f.away_score, config)[0] > 0
    )
    return {
        "enabled": bool(config.match_day_enabled),
        "rewards": {"exact": config.match_day_exact_coins, "diff": config.match_day_diff_coins, "outcome": config.match_day_outcome_coins},
        "current": _fixture_out(current, preds.get(current.id), await _split(db, current.id), config, now) if current else None,
        "recent": [_fixture_out(f, preds.get(f.id), None, config, now) for f in recent],
        "unclaimed": unclaimed,
    }


async def predict(db: AsyncSession, user: User, fixture_id: int, home: int, away: int) -> dict:
    config = await get_config(db)
    if not config.match_day_enabled:
        raise ConflictError("«Матч дня» сейчас выключен")
    if not (0 <= home <= MAX_GOALS and 0 <= away <= MAX_GOALS):
        raise ConflictError(f"Счёт — от 0 до {MAX_GOALS}")
    fixture = await db.get(MatchDayFixture, fixture_id)
    if fixture is None:
        raise NotFoundError("Матч не найден")
    if _aware(fixture.kickoff_at) <= _now() or _has_result(fixture):
        raise ConflictError("Матч уже начался — прогнозы закрыты")
    pred = (await db.execute(
        select(MatchDayPrediction).where(MatchDayPrediction.fixture_id == fixture_id, MatchDayPrediction.user_id == user.id)
    )).scalar_one_or_none()
    if pred is None:
        db.add(MatchDayPrediction(fixture_id=fixture_id, user_id=user.id, home=home, away=away))
    else:
        pred.home, pred.away = home, away
    await db.commit()
    return await get_view(db, user)


async def claim(db: AsyncSession, user: User, fixture_id: int) -> dict:
    config = await get_config(db)
    locked = await lock_user_for_update(db, user.id)
    pred = (await db.execute(
        select(MatchDayPrediction).where(MatchDayPrediction.fixture_id == fixture_id, MatchDayPrediction.user_id == locked.id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    fixture = await db.get(MatchDayFixture, fixture_id)
    if pred is None or fixture is None:
        raise NotFoundError("Прогноз не найден")
    if not _has_result(fixture):
        raise ConflictError("Результата ещё нет")
    if pred.claimed_at is not None:
        raise ConflictError("Награда уже получена")
    coins, _kind = reward_for(pred.home, pred.away, fixture.home_score, fixture.away_score, config)
    pred.reward_coins = coins
    pred.claimed_at = _now()
    if coins > 0:
        await credit_coins(db, locked, coins, TransactionType.match_day_reward, f"Матч дня: {fixture.home} — {fixture.away}",
                           related_object_type="match_day_fixture", related_object_id=fixture.id)
    await db.commit()
    await db.refresh(locked)
    return {"coins": coins, "new_balance": locked.balance}


# --- admin ---------------------------------------------------------------------------------------

async def admin_list(db: AsyncSession) -> list[dict]:
    counts = dict((await db.execute(
        select(MatchDayPrediction.fixture_id, func.count()).group_by(MatchDayPrediction.fixture_id)
    )).all())
    claimed = dict((await db.execute(
        select(MatchDayPrediction.fixture_id, func.count()).where(MatchDayPrediction.claimed_at.is_not(None))
        .group_by(MatchDayPrediction.fixture_id)
    )).all())
    rows = (await db.execute(select(MatchDayFixture).order_by(MatchDayFixture.kickoff_at.desc()).limit(60))).scalars()
    return [
        {"id": f.id, "home": f.home, "away": f.away, "league": f.league, "kickoff_at": _aware(f.kickoff_at),
         "home_score": f.home_score, "away_score": f.away_score, "predictions": counts.get(f.id, 0), "auto": f.external_id is not None,
         "claimed": claimed.get(f.id, 0)}
        for f in rows
    ]


def _clean(name: str) -> str:
    name = " ".join((name or "").split())[:64]
    if not name:
        raise ConflictError("Укажи обе команды")
    return name


async def admin_create(db: AsyncSession, home: str, away: str, league: Optional[str], kickoff_at: datetime) -> dict:
    db.add(MatchDayFixture(home=_clean(home), away=_clean(away), league=(league or "").strip()[:64] or None,
                           kickoff_at=_aware(kickoff_at)))
    await db.commit()
    return {"ok": True}


async def admin_update(
    db: AsyncSession, fixture_id: int, home: Optional[str], away: Optional[str], league: Optional[str],
    kickoff_at: Optional[datetime], home_score: Optional[int], away_score: Optional[int], clear_result: bool = False,
) -> dict:
    fixture = (await db.execute(
        select(MatchDayFixture).where(MatchDayFixture.id == fixture_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if fixture is None:
        raise NotFoundError("Матч не найден")
    claimed = (await db.execute(select(func.count()).select_from(MatchDayPrediction).where(
        MatchDayPrediction.fixture_id == fixture_id, MatchDayPrediction.claimed_at.is_not(None),
    ))).scalar_one()
    if home is not None:
        fixture.home = _clean(home)
    if away is not None:
        fixture.away = _clean(away)
    if league is not None:
        fixture.league = league.strip()[:64] or None
    if kickoff_at is not None:
        fixture.kickoff_at = _aware(kickoff_at)
    if clear_result or (home_score is not None and away_score is not None):
        if claimed:
            raise ConflictError("Награды по этому матчу уже забирают — результат менять нельзя")
        first = not _has_result(fixture)
        if clear_result:
            fixture.home_score = fixture.away_score = fixture.result_at = None
        else:
            if not (0 <= home_score <= MAX_GOALS and 0 <= away_score <= MAX_GOALS):
                raise ConflictError(f"Счёт — от 0 до {MAX_GOALS}")
            await set_result(db, fixture, home_score, away_score, notify_players=first)
    await db.commit()
    return {"ok": True}


async def set_result(db: AsyncSession, fixture: MatchDayFixture, home: int, away: int, notify_players: bool = True) -> None:
    """Writes the score (the fixture row is locked by the caller) and tells
    every guesser; the caller commits."""
    fixture.home_score, fixture.away_score, fixture.result_at = home, away, _now()
    if not notify_players:
        return
    for uid in (await db.execute(
        select(MatchDayPrediction.user_id).where(MatchDayPrediction.fixture_id == fixture.id)
    )).scalars():
        await notify(db, uid, NotificationType.match_day_result, f"⚽ {fixture.home} {home}:{away} {fixture.away}",
                     "Матч дня закончился — проверь свой прогноз и забери награду")


async def drop_fixture(db: AsyncSession, fixture: MatchDayFixture) -> None:
    """A postponed / cancelled match: gone with its guesses; the caller commits."""
    await db.execute(delete(MatchDayPrediction).where(MatchDayPrediction.fixture_id == fixture.id))
    await db.delete(fixture)


async def admin_delete(db: AsyncSession, fixture_id: int) -> dict:
    fixture = await db.get(MatchDayFixture, fixture_id)
    if fixture is None:
        raise NotFoundError("Матч не найден")
    claimed = (await db.execute(select(func.count()).select_from(MatchDayPrediction).where(
        MatchDayPrediction.fixture_id == fixture_id, MatchDayPrediction.claimed_at.is_not(None),
    ))).scalar_one()
    if claimed:
        raise ConflictError("По матчу уже выданы награды — удалить нельзя")
    await db.execute(delete(MatchDayPrediction).where(MatchDayPrediction.fixture_id == fixture_id))
    await db.delete(fixture)
    await db.commit()
    return {"ok": True}
