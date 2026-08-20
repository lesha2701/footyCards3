from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import NotFoundError
from app.models.badge import Badge, UserBadge
from app.models.card import UserCard
from app.models.enums import RARITY_ORDER, GameSessionStatus, GameType, MatchResult, PenaltyMatchStatus, TacticoMatchStatus
from app.models.game import GameSession
from app.models.pack import PackOpening
from app.models.penalty import PenaltyMatch
from app.models.player import Player
from app.models.tactico import TacticoMatch
from app.models.trophy import UserTrophy
from app.models.user import User
from app.schemas.badge import BadgeOut, OwnedBadgeOut
from app.schemas.player import PlayerOut
from app.schemas.profile import ProfilePrivateOut, ProfilePublicOut, ProfileSettingsUpdate
from app.schemas.trophy import UserTrophyOut
from app.schemas.user import UserPublicOut
from app.services.game_config_service import get_config

# result is always stored from the match's own user_id's perspective — for
# the opponent side of a PvP row, their own outcome is the flip of it. Same
# constant tactico_service.py/penalty_match_service.py each define locally.
_FLIP_RESULT = {MatchResult.win: MatchResult.loss, MatchResult.loss: MatchResult.win, MatchResult.draw: MatchResult.draw}


async def _collection_summary(db: AsyncSession, user_id: int) -> tuple[int, int, Player | None]:
    total = (await db.execute(select(func.count(UserCard.id)).where(UserCard.owner_id == user_id))).scalar_one()
    unique = (
        await db.execute(select(func.count(func.distinct(UserCard.player_id))).where(UserCard.owner_id == user_id))
    ).scalar_one()

    rows = (
        await db.execute(
            select(Player).join(UserCard, UserCard.player_id == Player.id).where(UserCard.owner_id == user_id)
        )
    ).scalars().all()
    rarest = None
    for player in rows:
        if rarest is None or (RARITY_ORDER[player.rarity], player.rating) > (RARITY_ORDER[rarest.rarity], rarest.rating):
            rarest = player

    return total, unique, rarest


async def _arena_rank(db: AsyncSession, user: User) -> int:
    higher = (
        await db.execute(select(func.count(User.id)).where(User.arena_rating > user.arena_rating))
    ).scalar_one()
    return higher + 1


async def _league_rank(db: AsyncSession, user: User) -> int:
    league_total = user.arena_rating + user.tactics_rating + user.penalty_rating
    higher = (
        await db.execute(
            select(func.count(User.id)).where(
                (User.arena_rating + User.tactics_rating + User.penalty_rating) > league_total
            )
        )
    ).scalar_one()
    return higher + 1


async def _tactico_record(db: AsyncSession, user_id: int) -> tuple[int, int, int]:
    """Won/drawn/lost across every finished Тактико match (bot, friend, and
    online alike — all live in the one TacticoMatch table). result is
    stored from the row's own user_id's perspective, so a match where this
    player was the opponent side needs its result flipped."""
    rows = (
        await db.execute(
            select(TacticoMatch.user_id, TacticoMatch.result).where(
                TacticoMatch.status == TacticoMatchStatus.finished,
                TacticoMatch.result.is_not(None),
                or_(TacticoMatch.user_id == user_id, TacticoMatch.opponent_user_id == user_id),
            )
        )
    ).all()
    won = drawn = lost = 0
    for row_user_id, result in rows:
        mine = result if row_user_id == user_id else _FLIP_RESULT[result]
        if mine == MatchResult.win:
            won += 1
        elif mine == MatchResult.draw:
            drawn += 1
        else:
            lost += 1
    return won, drawn, lost


async def _penalty_record(db: AsyncSession, user_id: int) -> tuple[int, int, int]:
    """Won/drawn/lost across Пенальти's two independent systems: PvP
    (PenaltyMatch — friend/online, same flip logic as Тактико) and the
    standalone bot mode (GameSession, game_type=penalty — win/lose only,
    no draw concept in a shootout; "rewarded" is a won session whose reward
    was already claimed, still a win)."""
    pvp_rows = (
        await db.execute(
            select(PenaltyMatch.user_id, PenaltyMatch.result).where(
                PenaltyMatch.status == PenaltyMatchStatus.finished,
                PenaltyMatch.result.is_not(None),
                or_(PenaltyMatch.user_id == user_id, PenaltyMatch.opponent_user_id == user_id),
            )
        )
    ).all()
    won = drawn = lost = 0
    for row_user_id, result in pvp_rows:
        mine = result if row_user_id == user_id else _FLIP_RESULT[result]
        if mine == MatchResult.win:
            won += 1
        elif mine == MatchResult.draw:
            drawn += 1
        else:
            lost += 1

    bot_statuses = (
        await db.execute(
            select(GameSession.status).where(
                GameSession.user_id == user_id,
                GameSession.game_type == GameType.penalty,
                GameSession.status.in_([GameSessionStatus.won, GameSessionStatus.lost, GameSessionStatus.rewarded]),
            )
        )
    ).scalars().all()
    for status in bot_statuses:
        if status == GameSessionStatus.lost:
            lost += 1
        else:
            won += 1

    return won, drawn, lost


async def _packs_opened(db: AsyncSession, user_id: int) -> int:
    return (await db.execute(select(func.count(PackOpening.id)).where(PackOpening.user_id == user_id))).scalar_one()


async def _build_public(db: AsyncSession, user: User) -> ProfilePublicOut:
    total, unique, rarest = await _collection_summary(db, user.id)
    rank = await _arena_rank(db, user)
    league_rank = await _league_rank(db, user)
    packs_opened = await _packs_opened(db, user.id)
    tactics_won, tactics_drawn, tactics_lost = await _tactico_record(db, user.id)
    penalty_won, penalty_drawn, penalty_lost = await _penalty_record(db, user.id)
    return ProfilePublicOut(
        id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
        level=user.level,
        arena_rating=user.arena_rating,
        arena_rank=rank,
        league_rank=league_rank,
        matches_won=user.matches_won,
        matches_drawn=user.matches_drawn,
        matches_lost=user.matches_lost,
        memory_best_score=user.memory_best_score,
        unique_cards=unique,
        total_cards=total,
        rarest_card=PlayerOut.model_validate(rarest) if rarest else None,
        packs_opened=packs_opened,
        referral_count=user.referral_count,
        active_badge=BadgeOut.model_validate(user.active_badge) if user.active_badge else None,
        tactics_rating=user.tactics_rating,
        tactics_matches_won=tactics_won,
        tactics_matches_drawn=tactics_drawn,
        tactics_matches_lost=tactics_lost,
        penalty_rating=user.penalty_rating,
        penalty_matches_won=penalty_won,
        penalty_matches_drawn=penalty_drawn,
        penalty_matches_lost=penalty_lost,
    )


async def get_public_profile(db: AsyncSession, user_id: int) -> ProfilePublicOut:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    return await _build_public(db, user)


async def get_private_profile(db: AsyncSession, user: User) -> ProfilePrivateOut:
    public = await _build_public(db, user)
    config = await get_config(db)
    return ProfilePrivateOut(
        **public.model_dump(),
        telegram_id=user.telegram_id,
        balance=user.balance,
        experience=user.experience,
        is_admin=user.is_admin,
        telegram_bot_username=get_settings().telegram_bot_username,
        accept_trades=user.accept_trades,
        referral_reward_pending=user.referred_by_id is not None and not user.referral_reward_granted,
        referral_referrer_reward=config.referral_referrer_reward,
        referral_referred_reward=config.referral_referred_reward,
        daily_login_streak=user.daily_login_streak,
    )


async def update_settings(db: AsyncSession, user: User, payload: ProfileSettingsUpdate) -> ProfilePrivateOut:
    updates = payload.model_dump(exclude_unset=True)

    if "active_badge_id" in updates:
        badge_id = updates.pop("active_badge_id")
        if badge_id is not None:
            owned = (
                await db.execute(
                    select(UserBadge).where(UserBadge.user_id == user.id, UserBadge.badge_id == badge_id)
                )
            ).scalar_one_or_none()
            if owned is None:
                raise NotFoundError("Badge not found")
        user.active_badge_id = badge_id

    for key, value in updates.items():
        setattr(user, key, value)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return await get_private_profile(db, user)


async def list_owned_badges(db: AsyncSession, user: User) -> list[OwnedBadgeOut]:
    result = await db.execute(
        select(UserBadge)
        .join(Badge, Badge.id == UserBadge.badge_id)
        .where(UserBadge.user_id == user.id)
        .order_by(Badge.sort_order)
    )
    owned = result.scalars().all()
    return [
        OwnedBadgeOut(badge=BadgeOut.model_validate(ub.badge), equipped=ub.badge_id == user.active_badge_id)
        for ub in owned
    ]


async def list_owned_trophies(db: AsyncSession, user: User) -> list[UserTrophyOut]:
    result = await db.execute(
        select(UserTrophy).where(UserTrophy.user_id == user.id).order_by(UserTrophy.granted_at.desc())
    )
    return [UserTrophyOut.model_validate(t) for t in result.scalars().all()]


async def search_users(db: AsyncSession, query: str, exclude_user_id: int, limit: int = 20) -> list[UserPublicOut]:
    stmt = select(User).where(User.id != exclude_user_id, User.accept_trades.is_(True))
    if query.isdigit():
        stmt = stmt.where((User.id == int(query)) | (User.username.ilike(f"%{query}%")))
    else:
        stmt = stmt.where(User.username.ilike(f"%{query}%"))
    stmt = stmt.limit(limit)
    users = (await db.execute(stmt)).scalars().all()
    return [UserPublicOut.model_validate(u) for u in users]
