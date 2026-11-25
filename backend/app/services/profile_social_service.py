"""Profile social layer: «👍 Респект» (one per visitor and day) and the
event feed of a profile — rare prints, trophies, completed collections,
read from the rows that already record them (no feed table)."""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.card import UserCard
from app.models.card_collection import CardCollection, UserCollectionReward
from app.models.player import Player
from app.models.profile_respect import ProfileRespect
from app.models.trophy import UserTrophy
from app.models.user import User
from app.core.timeutil import local_today

FEED_SIZE = 8
TODAY_GIVERS = 8


async def _target(db: AsyncSession, user_id: int) -> User:
    target = await db.get(User, user_id)
    if target is None or target.is_banned:
        raise NotFoundError("Игрок не найден")
    return target


async def social(db: AsyncSession, viewer: User, user_id: int) -> dict:
    await _target(db, user_id)
    total = (await db.execute(
        select(func.count()).select_from(ProfileRespect).where(ProfileRespect.target_id == user_id)
    )).scalar_one()
    today = (await db.execute(
        select(ProfileRespect.id).where(
            ProfileRespect.giver_id == viewer.id, ProfileRespect.target_id == user_id, ProfileRespect.day == local_today(),
        )
    )).first() is not None
    givers: list[dict] = []
    if viewer.id == user_id:
        # Only the owner sees who came by today.
        givers = [
            {"id": u.id, "first_name": u.first_name, "avatar_url": u.avatar_url}
            for u in (await db.execute(
                select(User).join(ProfileRespect, ProfileRespect.giver_id == User.id)
                .where(ProfileRespect.target_id == user_id, ProfileRespect.day == local_today())
                .order_by(ProfileRespect.created_at.desc()).limit(TODAY_GIVERS)
            )).scalars()
        ]
    return {
        "respects": total, "respected_today": today, "can_respect": viewer.id != user_id,
        "today_givers": givers, "feed": await feed(db, user_id),
    }


async def give_respect(db: AsyncSession, viewer: User, user_id: int) -> dict:
    if viewer.id == user_id:
        raise ConflictError("Себе респект не ставят 🙂")
    await _target(db, user_id)
    db.add(ProfileRespect(giver_id=viewer.id, target_id=user_id, day=local_today()))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("Сегодня ты уже ставил респект этому игроку")
    return await social(db, viewer, user_id)


async def feed(db: AsyncSession, user_id: int) -> list[dict]:
    from app.services.card_finish_service import FINISH_ICONS, FINISH_LABELS

    events: list[dict] = []
    for card, player in (await db.execute(
        select(UserCard, Player).join(Player, Player.id == UserCard.player_id)
        .where(UserCard.owner_id == user_id, UserCard.finish.is_not(None))
        .order_by(UserCard.acquired_at.desc()).limit(FEED_SIZE)
    )).all():
        events.append({
            "kind": "finish", "at": card.acquired_at, "icon": FINISH_ICONS.get(card.finish, "✨"),
            "text": f"Редкая версия: {player.display_name} — {FINISH_LABELS.get(card.finish, card.finish)}",
            "image_path": player.image_path,
        })
    for trophy in (await db.execute(
        select(UserTrophy).where(UserTrophy.user_id == user_id).order_by(UserTrophy.granted_at.desc()).limit(FEED_SIZE)
    )).scalars().all():
        events.append({
            "kind": "trophy", "at": trophy.granted_at, "icon": trophy.trophy.icon or "🏆",
            "text": f"Трофей «{trophy.trophy.name}»", "image_path": trophy.trophy.image_path,
        })
    for reward, collection in (await db.execute(
        select(UserCollectionReward, CardCollection).join(CardCollection, CardCollection.id == UserCollectionReward.collection_id)
        .where(UserCollectionReward.user_id == user_id).order_by(UserCollectionReward.granted_at.desc()).limit(FEED_SIZE)
    )).all():
        events.append({
            "kind": "collection", "at": reward.granted_at, "icon": "📖",
            "text": f"Собрал коллекцию «{collection.name}»", "image_path": collection.image_path,
        })

    def when(e):
        at = e["at"]
        return at if at.tzinfo else at.replace(tzinfo=timezone.utc)

    events.sort(key=when, reverse=True)
    return events[:FEED_SIZE]


HALL_CABINET = 6
HALL_PEDESTALS = 6  # the whole gift shelf (gift_service.SHELF_SIZE)


async def hall(db: AsyncSession, user_id: int) -> dict:
    """«Зал славы» — built only from what the profile already shows: the
    «Витрина» copies, trophies (newest first) then completed collections,
    and the gift shelf (pinned first, then the rarest serials)."""
    from app.services import gift_service, hall_decor_service, profile_service

    target = await _target(db, user_id)
    trophies = (await db.execute(
        select(UserTrophy).where(UserTrophy.user_id == user_id).order_by(UserTrophy.granted_at.desc())
    )).scalars().all()
    collections = (await db.execute(
        select(UserCollectionReward, CardCollection).join(CardCollection, CardCollection.id == UserCollectionReward.collection_id)
        .where(UserCollectionReward.user_id == user_id).order_by(UserCollectionReward.granted_at.desc())
    )).all()
    cabinet = [
        {"kind": "trophy", "code": t.trophy.code, "name": t.trophy.name, "description": t.message or t.trophy.description or "",
         "icon": t.trophy.icon or "🏆", "image_path": t.trophy.image_path, "at": t.granted_at}
        for t in trophies
    ] + [
        {"kind": "collection", "name": c.name, "description": "Коллекция собрана целиком", "icon": "📖",
         "image_path": c.image_path, "at": r.granted_at}
        for r, c in collections
    ]
    shelf = await gift_service.gift_shelf(db, user_id)
    rare = (await db.execute(
        select(func.count()).select_from(UserCard).where(UserCard.owner_id == user_id, UserCard.finish.is_not(None))
    )).scalar_one()
    respects = (await db.execute(
        select(func.count()).select_from(ProfileRespect).where(ProfileRespect.target_id == user_id)
    )).scalar_one()
    return {
        "frames": await profile_service.showcase_cards(db, target),
        "cabinet": cabinet[:HALL_CABINET],
        "pedestals": shelf.items[:HALL_PEDESTALS],
        "totals": {"trophies": len(trophies), "collections": len(collections), "gifts": shelf.copies,
                   "rare_prints": rare, "respects": respects},
        "decor": await hall_decor_service.view(db, target),
    }
