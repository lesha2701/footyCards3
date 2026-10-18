"""«Задания недели» клуба: shared weekly goals («вместе сыграть 60 игр»,
«открыть 20 паков», «выполнить 30 заданий») over the same activity the
club league counts (club_league_service._activity, member activity after
they joined, current league week). The goal is target_per_member x the
club's member count.

There is no scheduler: `sync` runs when a member opens the club or the
quests page and completes every quest that reached its goal — under the
club row lock, with a unique (club, template, week) row, so a completion
is paid exactly once: `reward_budget` into the club budget plus a club
reward grant every member claims (club_reward_service)."""
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.club import Club, ClubMember
from app.models.club_quest import ClubQuestCompletion, ClubQuestTemplate
from app.models.enums import ClubBudgetTransactionType
from app.models.user import User
from app.schemas.club_quest import (
    ClubQuestAdminOut,
    ClubQuestIn,
    ClubQuestMemberOut,
    ClubQuestOut,
    ClubQuestsOut,
)
from app.schemas.monetization import RewardBundleIn
from app.services import reward_bundle_service
from app.services.club_budget_service import credit_club_budget
from app.services.club_league_service import _activity, week_bounds, week_start_for
from app.services.club_reward_service import create_grant
from app.services.game_config_service import get_config
from app.services.reward_bundle_service import Bundle

METRICS = ("games", "packs", "tasks")


def _bundle(t: ClubQuestTemplate) -> Bundle:
    return Bundle.of(t, prefix="reward_")


async def _templates(db: AsyncSession) -> list[ClubQuestTemplate]:
    return list((await db.execute(
        select(ClubQuestTemplate).where(ClubQuestTemplate.is_active.is_(True))
        .order_by(ClubQuestTemplate.sort_order, ClubQuestTemplate.id)
    )).scalars())


async def _progress(db: AsyncSession, club_id: int) -> tuple[dict[str, int], dict[int, dict[str, int]]]:
    start, end = week_bounds(week_start_for())
    per_member: dict[int, dict[str, int]] = {}
    totals = {m: 0 for m in METRICS}
    for (_cid, uid), tally in (await _activity(db, start, end, club_id=club_id)).items():
        row = per_member.setdefault(uid, {m: 0 for m in METRICS})
        for m in METRICS:
            row[m] += getattr(tally, m)
            totals[m] += getattr(tally, m)
    return totals, per_member


async def sync(db: AsyncSession, club_id: int) -> None:
    """Completes and pays every quest of this week whose goal is reached.
    Commits only when something was completed."""
    config = await get_config(db)
    if not config.club_quests_enabled:
        return
    week = week_start_for()
    templates = await _templates(db)
    if not templates:
        return
    done = set((await db.execute(select(ClubQuestCompletion.template_id).where(
        ClubQuestCompletion.club_id == club_id, ClubQuestCompletion.week_start == week,
    ))).scalars())
    pending = [t for t in templates if t.id not in done]
    if not pending:
        return
    totals, _ = await _progress(db, club_id)
    members = (await db.execute(select(func.count(ClubMember.id)).where(ClubMember.club_id == club_id))).scalar_one()
    reached = [t for t in pending if totals.get(t.metric, 0) >= max(1, t.target_per_member * members)]
    if not reached:
        return

    club = (await db.execute(
        select(Club).where(Club.id == club_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one()
    for t in reached:
        try:
            async with db.begin_nested():
                db.add(ClubQuestCompletion(
                    club_id=club_id, template_id=t.id, week_start=week, target=max(1, t.target_per_member * members),
                ))
                await db.flush()
        except IntegrityError:
            continue  # a concurrent sync already completed it
        if t.reward_budget > 0:
            await credit_club_budget(
                db, club, t.reward_budget, ClubBudgetTransactionType.quest_reward, f"Задание недели: {t.title}",
                related_object_type="club_quest_template", related_object_id=t.id,
            )
        await create_grant(
            db, club_id, "quest", t.title, _bundle(t), source_ref_id=t.id,
            notify_text=f"Клуб выполнил задание недели «{t.title}» — забери свою награду",
        )
    await db.commit()


async def get_quests(db: AsyncSession, user: User) -> ClubQuestsOut:
    membership = (await db.execute(select(ClubMember).where(ClubMember.user_id == user.id))).scalar_one_or_none()
    if membership is None:
        raise NotFoundError("Ты не состоишь в клубе")
    club_id = membership.club_id
    await sync(db, club_id)
    config = await get_config(db)
    week = week_start_for()
    templates = await _templates(db) if config.club_quests_enabled else []
    completed = dict((await db.execute(select(ClubQuestCompletion.template_id, ClubQuestCompletion.target).where(
        ClubQuestCompletion.club_id == club_id, ClubQuestCompletion.week_start == week,
    ))).all())
    totals, per_member = await _progress(db, club_id)
    rows = (await db.execute(
        select(ClubMember.user_id, User.username, User.first_name)
        .join(User, User.id == ClubMember.user_id).where(ClubMember.club_id == club_id)
    )).all()
    members = len(rows)
    _start, end = week_bounds(week)
    return ClubQuestsOut(
        enabled=config.club_quests_enabled, week_start=week, ends_at=end,
        quests=[
            ClubQuestOut(
                id=t.id, title=t.title, metric=t.metric,
                target=completed.get(t.id) or max(1, t.target_per_member * members),
                progress=totals.get(t.metric, 0), completed=t.id in completed,
                reward_budget=t.reward_budget, reward=await reward_bundle_service.describe(db, _bundle(t)),
            )
            for t in templates
        ],
        members=sorted(
            (
                ClubQuestMemberOut(
                    user_id=uid, name=username or first_name or f"#{uid}", **per_member.get(uid, {m: 0 for m in METRICS}),
                )
                for uid, username, first_name in rows
            ),
            key=lambda m: -(m.games + m.packs + m.tasks),
        ),
    )


# --- admin ------------------------------------------------------------------------------


def _admin_out(t: ClubQuestTemplate) -> ClubQuestAdminOut:
    b = _bundle(t)
    return ClubQuestAdminOut(
        id=t.id, title=t.title, metric=t.metric, target_per_member=t.target_per_member, reward_budget=t.reward_budget,
        reward=RewardBundleIn(coins=b.coins, pack_id=b.pack_id, card_rarity=b.card_rarity, badge_id=b.badge_id, cosmetic_id=b.cosmetic_id),
        is_active=t.is_active, sort_order=t.sort_order,
    )


async def admin_list(db: AsyncSession) -> list[ClubQuestAdminOut]:
    rows = (await db.execute(select(ClubQuestTemplate).order_by(ClubQuestTemplate.sort_order, ClubQuestTemplate.id))).scalars()
    return [_admin_out(t) for t in rows]


async def admin_save(db: AsyncSession, template_id: int | None, data: ClubQuestIn) -> ClubQuestAdminOut:
    await reward_bundle_service.validate(db, Bundle.from_in(data.reward))
    if template_id is None:
        t = ClubQuestTemplate(title=data.title, metric=data.metric, target_per_member=data.target_per_member)
        db.add(t)
    else:
        t = await db.get(ClubQuestTemplate, template_id)
        if t is None:
            raise NotFoundError("Задание не найдено")
    t.title, t.metric, t.target_per_member = data.title, data.metric, data.target_per_member
    t.reward_budget, t.is_active, t.sort_order = data.reward_budget, data.is_active, data.sort_order
    t.reward_coins = data.reward.coins
    t.reward_pack_id = data.reward.pack_id
    t.reward_card_rarity = data.reward.card_rarity
    t.reward_badge_id = data.reward.badge_id
    t.reward_cosmetic_id = data.reward.cosmetic_id
    await db.commit()
    await db.refresh(t)
    return _admin_out(t)

