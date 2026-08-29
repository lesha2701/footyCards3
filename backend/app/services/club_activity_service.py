from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.club import ClubMember
from app.models.club_daily_claim import ClubDailyClaim
from app.models.enums import GameType, NotificationType
from app.models.game import GameSession
from app.models.user import User
from app.schemas.club_activity import ClubMemberActivityOut
from app.services.club_service import _get_membership, _require_manager, _require_membership
from app.services.notification_service import notify

ACTIVITY_WINDOW_DAYS = 7


async def get_club_activity(db: AsyncSession, user: User) -> list[ClubMemberActivityOut]:
    """Club-scoped activity only: the club's own mini-game (GameType.club_sequence, played
    via /clubs/game — not the seven general-purpose mini-games elsewhere in the app) and the
    club's own daily reward (ClubDailyClaim, the "Ежедневная награда" button on the club home
    screen — not the player's personal, club-unrelated DailyReward). Mixing in app-wide
    activity produced nonsense numbers for clubs that were created only yesterday."""
    membership = await _require_membership(db, user.id)
    club_id = membership.club_id

    rows = (
        await db.execute(
            select(ClubMember, User)
            .join(User, User.id == ClubMember.user_id)
            .where(ClubMember.club_id == club_id)
            .order_by(ClubMember.joined_at)
        )
    ).all()
    member_ids = [u.id for _, u in rows]
    if not member_ids:
        return []

    now = datetime.now(timezone.utc)
    since = now - timedelta(days=ACTIVITY_WINDOW_DAYS)

    games_played: dict[int, int] = {uid: 0 for uid in member_ids}
    game_rows = (
        await db.execute(
            select(GameSession.user_id, func.count(GameSession.id))
            .where(
                GameSession.user_id.in_(member_ids),
                GameSession.game_type == GameType.club_sequence,
                GameSession.created_at >= since,
            )
            .group_by(GameSession.user_id)
        )
    ).all()
    for uid, count in game_rows:
        games_played[uid] += count

    daily_rewards_claimed: dict[int, int] = {uid: 0 for uid in member_ids}
    reward_rows = (
        await db.execute(
            select(ClubDailyClaim.user_id, func.count(ClubDailyClaim.id))
            .where(
                ClubDailyClaim.club_id == club_id,
                ClubDailyClaim.user_id.in_(member_ids),
                ClubDailyClaim.claim_date >= since.date(),
            )
            .group_by(ClubDailyClaim.user_id)
        )
    ).all()
    for uid, count in reward_rows:
        daily_rewards_claimed[uid] += count

    return [
        ClubMemberActivityOut(
            user_id=member_user.id, username=member_user.username, first_name=member_user.first_name,
            role=member.role, games_played=games_played[member_user.id],
            daily_rewards_claimed=daily_rewards_claimed[member_user.id],
        )
        for member, member_user in rows
    ]


async def remind_member(db: AsyncSession, actor: User, target_user_id: int) -> None:
    membership = await _require_membership(db, actor.id)
    _require_manager(membership)
    if target_user_id == actor.id:
        raise ConflictError("Нельзя напомнить самому себе")

    target = await _get_membership(db, target_user_id)
    if target is None or target.club_id != membership.club_id:
        raise NotFoundError("Игрок не в этом клубе")

    await notify(
        db, target_user_id, NotificationType.club_activity_reminder, "Клуб ждёт тебя!",
        "Капитан или ассистент клуба заметил, что ты давно не играл в клубную мини-игру и не забирал "
        "ежедневную награду клуба — загляни в приложение!",
    )
    await db.commit()
