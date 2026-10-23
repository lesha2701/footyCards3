"""«Клубный рейд»: every club gets a boss each league week (local Monday to
Sunday). A member attacks up to `club_raid_attacks_per_day` times a day —
the limit counts across clubs, so hopping clubs gives nothing: a series of
`club_raid_shots` shots, each a goal with a chance from the strength of the
member's 11 best cards. Damage = goals x damage_per_goal + that strength.

The boss's HP is fixed when the raid opens (hp_per_member x members, at
least 3). The attack that brings the damage to the HP defeats it — under the
club and raid row locks, so exactly once: the club budget gets
`club_raid_reward_budget` and every member claims the reward bundle through
the club rewards (club_reward_service)."""
import random
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import local_today
from app.models.card import UserCard
from app.models.club import Club, ClubMember
from app.models.enums import ClubBudgetTransactionType
from app.models.player import Player
from app.models.user import User
from app.models.weekly_event import ClubRaid, ClubRaidAttack
from app.services import reward_bundle_service
from app.services.club_budget_service import credit_club_budget
from app.services.club_league_service import week_bounds, week_start_for
from app.services.club_reward_service import create_grant
from app.services.game_config_service import get_config
from app.services.reward_bundle_service import Bundle

BOSSES: list[tuple[str, str, str, str]] = [
    ("wall", "Бетонная стена", "🧱", "Девять защитников в штрафной и ни одного желания атаковать"),
    ("keeper", "Железный вратарь", "🧤", "Говорят, он не пропускал с прошлого сезона"),
    ("bus", "Автобус у ворот", "🚌", "Припаркован прямо на линии ворот"),
    ("titan", "Титан обороны", "🗿", "Два метра роста и ни одного проигранного стыка"),
    ("storm", "Штормовой ветер", "🌪️", "Мяч летит куда угодно, только не в ворота"),
]
MIN_MEMBERS = 3
RECENT = 8


def boss_of(code: str) -> dict:
    for c, name, emoji, line in BOSSES:
        if c == code:
            return {"code": c, "name": name, "emoji": emoji, "line": line}
    return {"code": code, "name": code, "emoji": "👹", "line": ""}


def _reward(config) -> Bundle:
    return Bundle(coins=config.club_raid_reward_coins, pack_id=config.club_raid_reward_pack_id or None)


def goal_chance(strength: int) -> float:
    """A 60-rated eleven scores a quarter of its shots, a 90-rated one 70%."""
    return max(0.15, min(0.8, 0.25 + (strength - 60) * 0.015))


async def strength_of(db: AsyncSession, user_id: int) -> int:
    ratings = (await db.execute(
        select(Player.rating).join(UserCard, UserCard.player_id == Player.id)
        .where(UserCard.owner_id == user_id).group_by(Player.id, Player.rating)  # copies of one player count once
        .order_by(Player.rating.desc()).limit(11)
    )).scalars().all()
    if not ratings:
        return 50
    # Missing slots count as 50 — a full eleven is stronger than three stars.
    return round((sum(ratings) + 50 * (11 - len(ratings))) / 11)


async def _membership(db: AsyncSession, user_id: int) -> ClubMember:
    m = (await db.execute(select(ClubMember).where(ClubMember.user_id == user_id))).scalar_one_or_none()
    if m is None:
        raise NotFoundError("Ты не состоишь в клубе")
    return m


async def _raid(db: AsyncSession, club_id: int, config, lock: bool = False) -> ClubRaid:
    week = week_start_for()
    stmt = select(ClubRaid).where(ClubRaid.club_id == club_id, ClubRaid.week_start == week)
    raid = (await db.execute(stmt)).scalar_one_or_none()
    if raid is None:
        members = (await db.execute(select(func.count(ClubMember.id)).where(ClubMember.club_id == club_id))).scalar_one()
        boss = BOSSES[(week.toordinal() // 7) % len(BOSSES)][0]
        try:
            async with db.begin_nested():
                db.add(ClubRaid(club_id=club_id, week_start=week, boss=boss,
                                hp=config.club_raid_hp_per_member * max(MIN_MEMBERS, members)))
        except IntegrityError:
            pass  # a member opened it at the same moment
        await db.flush()
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalar_one()


async def _used_today(db: AsyncSession, user_id: int) -> int:
    return (await db.execute(select(func.count(ClubRaidAttack.id)).where(
        ClubRaidAttack.user_id == user_id, ClubRaidAttack.day == local_today(),
    ))).scalar_one()


async def get_view(db: AsyncSession, user: User, last: Optional[dict] = None) -> dict:
    config = await get_config(db)
    membership = await _membership(db, user.id)
    raid = await _raid(db, membership.club_id, config)
    await db.commit()
    rows = (await db.execute(
        select(ClubRaidAttack.user_id, func.sum(ClubRaidAttack.damage), func.count(ClubRaidAttack.id), func.sum(ClubRaidAttack.goals))
        .where(ClubRaidAttack.raid_id == raid.id).group_by(ClubRaidAttack.user_id)
    )).all()
    by_user = {uid: (int(dmg or 0), int(n), int(goals or 0)) for uid, dmg, n, goals in rows}
    members = (await db.execute(
        select(User).join(ClubMember, ClubMember.user_id == User.id).where(ClubMember.club_id == membership.club_id)
    )).scalars().all()
    recent = (await db.execute(
        select(ClubRaidAttack, User).join(User, User.id == ClubRaidAttack.user_id)
        .where(ClubRaidAttack.raid_id == raid.id).order_by(ClubRaidAttack.id.desc()).limit(RECENT)
    )).all()
    used = await _used_today(db, user.id)
    strength = await strength_of(db, user.id)
    _start, end = week_bounds(raid.week_start)
    return {
        "enabled": bool(config.club_raid_enabled),
        "boss": boss_of(raid.boss), "hp": raid.hp, "damage": min(raid.damage, raid.hp), "defeated": raid.defeated_at is not None,
        "ends_at": end,
        "attacks_left": max(0, config.club_raid_attacks_per_day - used), "attacks_per_day": config.club_raid_attacks_per_day,
        "shots": config.club_raid_shots, "strength": strength, "chance_pct": round(goal_chance(strength) * 100),
        "reward": await reward_bundle_service.describe(db, _reward(config)), "reward_budget": config.club_raid_reward_budget,
        "members": sorted(
            ({"user_id": m.id, "name": _name(m), "damage": by_user.get(m.id, (0, 0, 0))[0],
              "attacks": by_user.get(m.id, (0, 0, 0))[1], "goals": by_user.get(m.id, (0, 0, 0))[2], "is_me": m.id == user.id}
             for m in members),
            key=lambda r: (-r["damage"], r["name"]),
        ),
        "recent": [{"name": _name(u), "goals": a.goals, "shots": a.shots, "damage": a.damage, "at": a.created_at} for a, u in recent],
        "last": last,
    }


async def attack(db: AsyncSession, user: User) -> dict:
    config = await get_config(db)
    if not config.club_raid_enabled:
        raise ConflictError("Рейды сейчас выключены")
    membership = await _membership(db, user.id)
    club = (await db.execute(
        select(Club).where(Club.id == membership.club_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one()
    raid = await _raid(db, club.id, config, lock=True)
    if raid.defeated_at is not None:
        raise ConflictError("Босс этой недели уже повержен — новый придёт в понедельник")
    if await _used_today(db, user.id) >= config.club_raid_attacks_per_day:
        raise ConflictError("Атаки на сегодня закончились — завтра будут новые")
    strength = await strength_of(db, user.id)
    chance = goal_chance(strength)
    shots = [random.random() < chance for _ in range(max(1, config.club_raid_shots))]
    goals = sum(shots)
    damage = goals * config.club_raid_damage_per_goal + strength
    db.add(ClubRaidAttack(raid_id=raid.id, user_id=user.id, day=local_today(), shots=len(shots), goals=goals, damage=damage))
    raid.damage += damage
    defeated_now = raid.damage >= raid.hp
    if defeated_now:
        raid.defeated_at = datetime.now(timezone.utc)
        boss = boss_of(raid.boss)
        if config.club_raid_reward_budget > 0:
            await credit_club_budget(
                db, club, config.club_raid_reward_budget, ClubBudgetTransactionType.raid_reward, f"Рейд: {boss['name']}",
                related_object_type="club_raid", related_object_id=raid.id,
            )
        await create_grant(
            db, club.id, "raid", f"Рейд: {boss['name']}", _reward(config), source_ref_id=raid.id,
            notify_text=f"{boss['emoji']} Клуб победил босса «{boss['name']}» — забери награду",
        )
    await db.commit()
    return await get_view(db, user, last={"shots": shots, "goals": goals, "damage": damage, "defeated_now": defeated_now})


def _name(user: User) -> str:
    return user.first_name or user.username or "Игрок"
