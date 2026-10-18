"""«Клубный магазин»: a short admin-made assortment the club buys with its
budget — every member then claims the item's reward bundle for themselves
(club_reward_service). Each item may be bought `weekly_limit` times per
club per league week. Only budget spenders buy (club_service.can_spend_budget)."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.club import Club, ClubMember
from app.models.club_reward import ClubShopItem, ClubShopPurchase
from app.models.enums import ClubBudgetTransactionType
from app.models.user import User
from app.schemas.club_reward import ClubShopItemAdminOut, ClubShopItemIn, ClubShopItemOut, ClubShopOut
from app.schemas.monetization import RewardBundleIn
from app.services import reward_bundle_service
from app.services.club_budget_service import debit_club_budget
from app.services.club_league_service import week_start_for
from app.services.club_reward_service import create_grant, unclaimed
from app.services.club_service import can_spend_budget, require_budget_spender
from app.services.reward_bundle_service import Bundle


def _bundle(item: ClubShopItem) -> Bundle:
    return Bundle.of(item, prefix="reward_")


async def _membership(db: AsyncSession, user_id: int) -> ClubMember:
    membership = (await db.execute(select(ClubMember).where(ClubMember.user_id == user_id))).scalar_one_or_none()
    if membership is None:
        raise NotFoundError("Ты не состоишь в клубе")
    return membership


async def _bought_this_week(db: AsyncSession, club_id: int) -> dict[int, int]:
    rows = await db.execute(
        select(ClubShopPurchase.item_id, func.count(ClubShopPurchase.id))
        .where(ClubShopPurchase.club_id == club_id, ClubShopPurchase.week_start == week_start_for())
        .group_by(ClubShopPurchase.item_id)
    )
    return dict(rows.all())


async def get_shop(db: AsyncSession, user: User) -> ClubShopOut:
    membership = await _membership(db, user.id)
    club = await db.get(Club, membership.club_id)
    bought = await _bought_this_week(db, club.id)
    items = (await db.execute(
        select(ClubShopItem).where(ClubShopItem.is_active.is_(True)).order_by(ClubShopItem.sort_order, ClubShopItem.id)
    )).scalars().all()
    member_count = (await db.execute(
        select(func.count(ClubMember.id)).where(ClubMember.club_id == club.id)
    )).scalar_one()
    return ClubShopOut(
        budget=club.budget, can_buy=can_spend_budget(membership, club), member_count=member_count,
        items=[
            ClubShopItemOut(
                id=i.id, name=i.name, description=i.description, price=i.price, weekly_limit=i.weekly_limit,
                bought_this_week=bought.get(i.id, 0), reward=await reward_bundle_service.describe(db, _bundle(i)),
            )
            for i in items
        ],
        rewards=await unclaimed(db, membership),
    )


async def buy(db: AsyncSession, user: User, item_id: int) -> ClubShopOut:
    membership = await _membership(db, user.id)
    item = await db.get(ClubShopItem, item_id)
    if item is None or not item.is_active:
        raise NotFoundError("Товар не найден")
    club = (await db.execute(
        select(Club).where(Club.id == membership.club_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one()
    require_budget_spender(membership, club)
    # Counted under the club row lock, so two managers can't both take the last one.
    if (await _bought_this_week(db, club.id)).get(item.id, 0) >= item.weekly_limit:
        raise ConflictError("На этой неделе этот товар уже куплен — лимит исчерпан")
    await debit_club_budget(
        db, club, item.price, ClubBudgetTransactionType.shop_purchase, f"Клубный магазин: {item.name}",
        related_object_type="club_shop_item", related_object_id=item.id, actor_user_id=user.id,
    )
    purchase = ClubShopPurchase(club_id=club.id, item_id=item.id, user_id=user.id, price=item.price, week_start=week_start_for())
    db.add(purchase)
    await db.flush()
    buyer = user.username or user.first_name or f"#{user.id}"
    await create_grant(
        db, club.id, "shop", item.name, _bundle(item), source_ref_id=purchase.id,
        notify_text=f"{buyer} купил в клубном магазине «{item.name}» — забери свою награду",
    )
    await db.commit()
    return await get_shop(db, user)


# --- admin ------------------------------------------------------------------------------


def _admin_out(item: ClubShopItem) -> ClubShopItemAdminOut:
    b = _bundle(item)
    return ClubShopItemAdminOut(
        id=item.id, name=item.name, description=item.description, price=item.price, weekly_limit=item.weekly_limit,
        reward=RewardBundleIn(coins=b.coins, pack_id=b.pack_id, card_rarity=b.card_rarity, badge_id=b.badge_id, cosmetic_id=b.cosmetic_id),
        is_active=item.is_active, sort_order=item.sort_order,
    )


async def admin_list(db: AsyncSession) -> list[ClubShopItemAdminOut]:
    items = (await db.execute(select(ClubShopItem).order_by(ClubShopItem.sort_order, ClubShopItem.id))).scalars().all()
    return [_admin_out(i) for i in items]


def _apply(item: ClubShopItem, data: ClubShopItemIn) -> None:
    item.name, item.description, item.price = data.name, data.description, data.price
    item.weekly_limit, item.is_active, item.sort_order = data.weekly_limit, data.is_active, data.sort_order
    item.reward_coins = data.reward.coins
    item.reward_pack_id = data.reward.pack_id
    item.reward_card_rarity = data.reward.card_rarity
    item.reward_badge_id = data.reward.badge_id
    item.reward_cosmetic_id = data.reward.cosmetic_id


async def admin_save(db: AsyncSession, item_id: int | None, data: ClubShopItemIn) -> ClubShopItemAdminOut:
    bundle = Bundle.from_in(data.reward)
    if bundle.is_empty():
        raise ConflictError("Награда товара пустая")
    await reward_bundle_service.validate(db, bundle)
    if item_id is None:
        item = ClubShopItem(name=data.name, price=data.price)
        db.add(item)
    else:
        item = await db.get(ClubShopItem, item_id)
        if item is None:
            raise NotFoundError("Товар не найден")
    _apply(item, data)
    await db.commit()
    await db.refresh(item)
    return _admin_out(item)
