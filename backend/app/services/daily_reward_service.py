"""«Календарь наград»: the monthly login calendar (replaced the old 7-day
streak). Every day of the current month has a reward from one admin-edited
template (login_calendar_days, day 1..31; day 0 = the bonus for claiming
every day of a month). Today's reward is claimed once; a missed day of the
current month stays missed unless it is caught up for coins or Stars (a
limited number per month, GameConfig.calendar_catchup_*).

Claims are still `daily_rewards` rows (reward_date = the calendar day,
streak_day = its day of the month, claim_method = login/coins/stars), so the
unique (user_id, reward_date) constraint keeps every day claimable once and
the bot's reminder / club activity queries keep working unchanged."""
import calendar as pycalendar
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.timeutil import local_today
from app.models.daily_reward import DailyReward
from app.models.enums import CardSource, TransactionType
from app.models.monetization import LoginCalendarBonusClaim, LoginCalendarDay
from app.models.pack import Pack
from app.models.user import User
from app.schemas.monetization import (
    CalendarClaimOut,
    CalendarDayOut,
    CalendarOut,
    CalendarTemplateDayOut,
    CalendarTemplateIn,
    GrantedRewardsOut,
)
from app.services import reward_bundle_service
from app.services.game_config_service import get_config
from app.services.reward_bundle_service import Bundle
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update

BIG_DAYS = (7, 14, 21, 28)


def _default_template(basic_pack_id: Optional[int], premium_pack_id: Optional[int]) -> dict[int, dict]:
    """Seeded the first time the template is read and found empty (same lazy
    pattern as GameConfig): growing coins every day, something bigger every
    7th day and a legendary card for the full month. Admins edit it freely."""
    days: dict[int, dict] = {d: {"coins": 50 + 5 * (d - 1)} for d in range(1, 32)}
    days[7] = {"coins": 300, "pack_id": basic_pack_id}
    days[14] = {"coins": 500, "card_rarity": "rare"}
    days[21] = {"coins": 700, "pack_id": premium_pack_id or basic_pack_id}
    days[28] = {"coins": 1000, "card_rarity": "epic"}
    days[0] = {"coins": 2000, "card_rarity": "legendary"}
    return days


async def get_template(db: AsyncSession) -> dict[int, LoginCalendarDay]:
    rows = (await db.execute(select(LoginCalendarDay))).scalars().all()
    if not rows:
        packs = {p.slug: p.id for p in (await db.execute(select(Pack).where(Pack.slug.in_(("basic", "premium"))))).scalars()}
        try:
            # A savepoint, not a full rollback on conflict: the caller's
            # objects (the current user) must stay loaded.
            async with db.begin_nested():
                for day, cfg in _default_template(packs.get("basic"), packs.get("premium")).items():
                    db.add(LoginCalendarDay(day=day, **{"coins": 0, **cfg}))
                await db.flush()
            await db.commit()
        except IntegrityError:
            pass  # a concurrent request seeded it first
        rows = (await db.execute(select(LoginCalendarDay))).scalars().all()
    return {r.day: r for r in rows}


def _month_bounds(day: date) -> tuple[date, date, int]:
    first = day.replace(day=1)
    days_in_month = pycalendar.monthrange(day.year, day.month)[1]
    return first, first + timedelta(days=days_in_month), days_in_month


def _bundle(template: dict[int, LoginCalendarDay], day: int) -> Bundle:
    row = template.get(day)
    return Bundle.of(row) if row else Bundle()


async def _claims(db: AsyncSession, user_id: int, first: date, end: date) -> dict[date, str]:
    rows = await db.execute(
        select(DailyReward.reward_date, DailyReward.claim_method)
        .where(DailyReward.user_id == user_id, DailyReward.reward_date >= first, DailyReward.reward_date < end)
    )
    return {d: m for d, m in rows.all()}


async def _bonus_claimed(db: AsyncSession, user_id: int, first: date) -> bool:
    return (await db.execute(select(LoginCalendarBonusClaim.id).where(
        LoginCalendarBonusClaim.user_id == user_id, LoginCalendarBonusClaim.month == first,
    ))).first() is not None


def _catchups_used(claims: dict[date, str]) -> int:
    """Paid catch-ups (coins/Stars); the club pass's free ones ("pass") count separately."""
    return sum(1 for m in claims.values() if m in ("coins", "stars"))


async def _free_catchups_left(db: AsyncSession, user_id: int, claims: dict[date, str], config) -> int:
    from app.services import club_pass_service

    if not config.club_pass_free_catchups or not await club_pass_service.is_subscriber(db, user_id):
        return 0
    return max(0, config.club_pass_free_catchups - sum(1 for m in claims.values() if m == "pass"))


async def get_calendar(db: AsyncSession, user: User) -> CalendarOut:
    today = local_today()
    first, end, days_in_month = _month_bounds(today)
    template = await get_template(db)
    claims = await _claims(db, user.id, first, end)
    config = await get_config(db)

    days = []
    for n in range(1, days_in_month + 1):
        d = first.replace(day=n)
        bundle = _bundle(template, n)
        status = "claimed" if d in claims else "today" if d == today else "missed" if d < today else "future"
        days.append(CalendarDayOut(
            day=n, date=d, reward=await reward_bundle_service.describe(db, bundle), status=status,
            claim_method=claims.get(d), is_big=n in BIG_DAYS or bool(bundle.pack_id or bundle.card_rarity
                                                                     or bundle.badge_id or bundle.cosmetic_id),
        ))
    return CalendarOut(
        month=first, today=today, days=days, claimed_count=len(claims), days_in_month=days_in_month,
        already_claimed_today=today in claims,
        month_bonus=await reward_bundle_service.describe(db, _bundle(template, 0)),
        month_bonus_claimed=await _bonus_claimed(db, user.id, first),
        catchup_coins=config.calendar_catchup_coins, catchup_stars=config.calendar_catchup_stars,
        catchups_left=max(0, config.calendar_catchup_max_per_month - _catchups_used(claims)),
        free_catchups_left=await _free_catchups_left(db, user.id, claims, config),
    )


async def _grant_day(
    db: AsyncSession, user: User, day: date, method: str, template: dict[int, LoginCalendarDay],
) -> GrantedRewardsOut:
    """Records the claim (the unique constraint refuses a second one) and
    grants that day's reward. `user` is row-locked; the caller commits."""
    bundle = _bundle(template, day.day)
    row = DailyReward(
        user_id=user.id, reward_date=day, streak_day=day.day, coins_awarded=bundle.coins, claim_method=method,
    )
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError:
        raise ConflictError("Награда за этот день уже получена") from None
    granted = await reward_bundle_service.grant(
        db, user, bundle, tx_type=TransactionType.daily_reward,
        description=f"Календарь наград: {day.day} число", card_source=CardSource.daily_reward,
        idempotency_prefix=f"calendar-{user.id}-{day.isoformat()}", cosmetic_source="calendar",
        related_object_type="daily_reward", related_object_id=row.id,
    )
    if granted.cards:
        row.random_card_id = granted.cards[-1].id
    from app.services import season_pass_service

    await season_pass_service.add_xp_for_daily_claim(db, user)
    return granted


async def _maybe_month_bonus(
    db: AsyncSession, user: User, month_day: date, template: dict[int, LoginCalendarDay],
) -> Optional[GrantedRewardsOut]:
    """Grants the full-month bonus once every day of that month is claimed."""
    first, end, days_in_month = _month_bounds(month_day)
    if len(await _claims(db, user.id, first, end)) < days_in_month or await _bonus_claimed(db, user.id, first):
        return None
    bundle = _bundle(template, 0)
    try:
        async with db.begin_nested():
            db.add(LoginCalendarBonusClaim(user_id=user.id, month=first))
            await db.flush()
    except IntegrityError:
        return None
    if bundle.is_empty():
        return None
    return await reward_bundle_service.grant(
        db, user, bundle, tx_type=TransactionType.daily_reward, description="Календарь наград: весь месяц",
        card_source=CardSource.daily_reward, idempotency_prefix=f"calendar-bonus-{user.id}-{first.isoformat()}",
        cosmetic_source="calendar",
    )


async def claim_daily_reward(db: AsyncSession, user: User) -> CalendarClaimOut:
    today = local_today()
    template = await get_template(db)
    locked = await lock_user_for_update(db, user.id)
    granted = await _grant_day(db, locked, today, "login", template)
    bonus = await _maybe_month_bonus(db, locked, today, template)
    await db.commit()
    await db.refresh(locked)
    return CalendarClaimOut(day=today.day, granted=granted, month_bonus=bonus, new_balance=locked.balance)


def _check_catchup_date(day: date, today: date) -> None:
    first, _end, _n = _month_bounds(today)
    if not (first <= day < today):
        raise ConflictError("Догнать можно только пропущенный день этого месяца")


async def _check_catchup(db: AsyncSession, user_id: int, day: date, free: bool = False) -> None:
    today = local_today()
    _check_catchup_date(day, today)
    first, end, _n = _month_bounds(today)
    claims = await _claims(db, user_id, first, end)
    if day in claims:
        raise ConflictError("Награда за этот день уже получена")
    config = await get_config(db)
    if free:
        if await _free_catchups_left(db, user_id, claims, config) <= 0:
            raise ConflictError("Бесплатные догоны абонемента в этом месяце закончились")
    elif _catchups_used(claims) >= config.calendar_catchup_max_per_month:
        raise ConflictError("В этом месяце догонять пропуски больше нельзя")


async def catch_up_with_coins(db: AsyncSession, user: User, day: date, free: bool = False) -> CalendarClaimOut:
    """Catches up a missed day for coins — or, with free=True, with one of
    the club pass's free catch-ups."""
    config = await get_config(db)
    if not free and config.calendar_catchup_coins <= 0:
        raise ConflictError("Догнать за монеты сейчас нельзя")
    template = await get_template(db)
    locked = await lock_user_for_update(db, user.id)
    await _check_catchup(db, locked.id, day, free=free)
    if not free:
        await debit_coins(
            db, locked, config.calendar_catchup_coins, TransactionType.calendar_catchup,
            f"Календарь наград: догнать {day.day} число",
        )
    granted = await _grant_day(db, locked, day, "pass" if free else "coins", template)
    bonus = await _maybe_month_bonus(db, locked, day, template)
    await db.commit()
    await db.refresh(locked)
    return CalendarClaimOut(day=day.day, granted=granted, month_bonus=bonus, new_balance=locked.balance)


# --- Stars catch-up ("calendar_catchup:<YYYY-MM-DD>", see shop_product_service) --------


async def stars_order(db: AsyncSession, user: User, day: date) -> tuple[str, int, str, str]:
    config = await get_config(db)
    if config.calendar_catchup_stars <= 0:
        raise ConflictError("Догнать за звёзды сейчас нельзя")
    await _check_catchup(db, user.id, day)
    bundle = await reward_bundle_service.describe(db, _bundle(await get_template(db), day.day))
    parts = [f"{bundle.coins} монет"] if bundle.coins else []
    if bundle.pack_name:
        parts.append(f"пак «{bundle.pack_name}»")
    if bundle.card_rarity:
        parts.append("случайная карточка")
    if bundle.badge:
        parts.append(f"значок «{bundle.badge.name}»")
    if bundle.cosmetic:
        parts.append(f"«{bundle.cosmetic.name}»")
    return (
        f"calendar_catchup:{day.isoformat()}", config.calendar_catchup_stars, f"Награда за {day.day} число",
        "Пропущенный день календаря наград: " + (", ".join(parts) or "награда дня"),
    )


async def validate_stars(db: AsyncSession, user_id: int, day: date, stars_amount: int) -> tuple[bool, str]:
    config = await get_config(db)
    if config.calendar_catchup_stars != stars_amount:
        return False, "Цена изменилась — открой покупку заново"
    try:
        await _check_catchup(db, user_id, day)
    except ConflictError as exc:
        return False, exc.message
    return True, ""


async def deliver_stars(db: AsyncSession, user: User, day: date) -> dict:
    """Already paid: never refuses. If the day got claimed meanwhile (e.g. a
    coins catch-up raced it), the player gets the coins price instead."""
    template = await get_template(db)
    locked = await lock_user_for_update(db, user.id)
    already = (await db.execute(select(DailyReward.id).where(
        DailyReward.user_id == locked.id, DailyReward.reward_date == day,
    ))).first()
    if already:
        config = await get_config(db)
        await credit_coins(
            db, locked, max(config.calendar_catchup_coins, _bundle(template, day.day).coins),
            TransactionType.calendar_catchup, f"Календарь наград: компенсация за {day.day} число",
        )
        return {"kind": "calendar_catchup", "day": day.day, "compensated": True}
    await _grant_day(db, locked, day, "stars", template)
    await _maybe_month_bonus(db, locked, day, template)
    return {"kind": "calendar_catchup", "day": day.day}


# --- admin ----------------------------------------------------------------------------


async def admin_template(db: AsyncSession) -> list[CalendarTemplateDayOut]:
    template = await get_template(db)
    return [
        CalendarTemplateDayOut(day=d, **Bundle.of(template[d]).to_in().model_dump())
        for d in sorted(template)
    ]


async def admin_update_template(db: AsyncSession, payload: CalendarTemplateIn) -> list[CalendarTemplateDayOut]:
    days = {d.day: d for d in payload.days}
    for d in days.values():
        await reward_bundle_service.validate(db, Bundle.from_in(d))
    template = await get_template(db)
    for n in range(0, 32):
        data = days.get(n)
        row = template.get(n)
        if data is None:
            continue
        if row is None:
            row = LoginCalendarDay(day=n)
            db.add(row)
        for key, value in data.model_dump(exclude={"day"}).items():
            setattr(row, key, value)
    await db.commit()
    return await admin_template(db)

