"""«Казна за Stars»: any member tops up their club's budget with Telegram
Stars ("club_donation:<club_id>:<coins>" through shop_product_service — the
coins are frozen into the product at invoice time, so an admin changing the
rate mid-payment can't change what was bought). Every donation is a
`ClubDonation` row; the «Доска меценатов» and the members' sponsor badges
(bronze for any donation, silver/gold from GameConfig thresholds) are sums
over those rows."""
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.club import Club, ClubMember
from app.models.club_emblem import ClubDonation
from app.models.enums import ClubBudgetTransactionType, ClubRole, NotificationType
from app.models.game_config import GameConfig
from app.models.pack import StarsInvoice
from app.models.user import User
from app.schemas.club_emblem import ClubDonationOut, ClubPatronOut, ClubTreasuryOut, SponsorTier
from app.services.club_budget_service import credit_club_budget
from app.services.game_config_service import get_config
from app.services.notification_service import notify

PATRONS_LIMIT = 20
RECENT_LIMIT = 10


def tier_for(stars: int, config: GameConfig) -> Optional[SponsorTier]:
    if stars <= 0:
        return None
    if stars >= config.club_sponsor_gold_stars:
        return "gold"
    if stars >= config.club_sponsor_silver_stars:
        return "silver"
    return "bronze"


def _star_options(config: GameConfig) -> list[int]:
    return sorted({int(s) for s in (config.club_donation_star_options or []) if int(s) > 0})


async def stars_by_user(db: AsyncSession, club_id: int) -> dict[int, int]:
    rows = await db.execute(
        select(ClubDonation.user_id, func.sum(ClubDonation.stars))
        .where(ClubDonation.club_id == club_id).group_by(ClubDonation.user_id)
    )
    return {uid: int(total or 0) for uid, total in rows.all()}


async def _membership(db: AsyncSession, user_id: int) -> ClubMember:
    membership = (await db.execute(select(ClubMember).where(ClubMember.user_id == user_id))).scalar_one_or_none()
    if membership is None:
        raise NotFoundError("Ты не состоишь в клубе")
    return membership


async def get_treasury(db: AsyncSession, user: User) -> ClubTreasuryOut:
    membership = await _membership(db, user.id)
    club = await db.get(Club, membership.club_id)
    config = await get_config(db)

    member_ids = set((await db.execute(
        select(ClubMember.user_id).where(ClubMember.club_id == club.id)
    )).scalars())
    # Aggregate first, then join: User eager-joins its badge, which a GROUP BY
    # over the users row would reject on Postgres.
    totals = (
        select(
            ClubDonation.user_id, func.sum(ClubDonation.stars).label("stars"),
            func.sum(ClubDonation.coins).label("coins"), func.min(ClubDonation.id).label("first_id"),
        )
        .where(ClubDonation.club_id == club.id).group_by(ClubDonation.user_id).subquery()
    )
    patron_rows = (await db.execute(
        select(User, totals.c.stars, totals.c.coins)
        .join(totals, totals.c.user_id == User.id)
        .order_by(totals.c.stars.desc(), totals.c.first_id)
        .limit(PATRONS_LIMIT)
    )).all()
    patrons = [
        ClubPatronOut(
            user_id=u.id, username=u.username, first_name=u.first_name, avatar_url=u.avatar_url,
            stars=int(stars), coins=int(coins), tier=tier_for(int(stars), config), is_member=u.id in member_ids,
        )
        for u, stars, coins in patron_rows
    ]
    recent_rows = (await db.execute(
        select(ClubDonation, User).join(User, User.id == ClubDonation.user_id)
        .where(ClubDonation.club_id == club.id).order_by(ClubDonation.id.desc()).limit(RECENT_LIMIT)
    )).all()
    my_stars = (await stars_by_user(db, club.id)).get(user.id, 0)
    return ClubTreasuryOut(
        enabled=config.club_donation_enabled, club_id=club.id, budget=club.budget,
        coins_per_star=config.club_donation_coins_per_star, star_options=_star_options(config),
        silver_stars=config.club_sponsor_silver_stars, gold_stars=config.club_sponsor_gold_stars,
        my_stars=my_stars, my_tier=tier_for(my_stars, config), patrons=patrons,
        recent=[
            ClubDonationOut(
                user_id=u.id, username=u.username, first_name=u.first_name,
                stars=d.stars, coins=d.coins, created_at=d.created_at,
            )
            for d, u in recent_rows
        ],
    )


# --- Stars ("club_donation:<club_id>:<coins>", see shop_product_service) -------------------


async def stars_order(db: AsyncSession, user: User, stars: int) -> tuple[str, int, str, str]:
    config = await get_config(db)
    if not config.club_donation_enabled:
        raise ConflictError("Пополнение казны сейчас недоступно")
    if stars not in _star_options(config):
        raise ConflictError("Такой суммы нет — выбери из предложенных")
    membership = await _membership(db, user.id)
    club = await db.get(Club, membership.club_id)
    coins = stars * config.club_donation_coins_per_star
    return (
        f"club_donation:{club.id}:{coins}", stars, "Казна клуба",
        f"Пополнение бюджета клуба «{club.name}» на {coins} монет. Ты попадёшь на «Доску меценатов» клуба.",
    )


def _parse(arg: str) -> tuple[int, int]:
    club_id, _, coins = arg.partition(":")
    return int(club_id), int(coins)


async def validate_stars(db: AsyncSession, user_id: int, arg: str, stars_amount: int) -> tuple[bool, str]:
    club_id, coins = _parse(arg)
    config = await get_config(db)
    if not config.club_donation_enabled:
        return False, "Пополнение казны сейчас недоступно"
    if coins != stars_amount * config.club_donation_coins_per_star:
        return False, "Курс пополнения изменился — открой казну заново"
    club = await db.get(Club, club_id)
    if club is None or club.is_disbanded:
        return False, "Клуб не найден"
    membership = (await db.execute(select(ClubMember).where(ClubMember.user_id == user_id))).scalar_one_or_none()
    if membership is None or membership.club_id != club_id:
        return False, "Ты больше не в этом клубе"
    return True, ""


async def deliver_stars(db: AsyncSession, user: User, invoice: StarsInvoice) -> dict:
    """Called under the invoice row lock; the payment is already taken, so
    the coins go to the club even if the donor left it meanwhile. The
    caller commits; ClubDonation.invoice_id is unique, so a duplicate
    delivery can never credit twice."""
    club_id, coins = _parse(invoice.shop_product.partition(":")[2])
    club = (await db.execute(
        select(Club).where(Club.id == club_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if club is None:
        raise NotFoundError("Клуб не найден")
    donor = user.username or user.first_name or f"#{user.id}"
    await credit_club_budget(
        db, club, coins, ClubBudgetTransactionType.stars_donation,
        f"Пополнение казны от {donor} ({invoice.stars_amount} ⭐)",
        related_object_type="stars_invoice", related_object_id=invoice.id, actor_user_id=user.id,
    )
    db.add(ClubDonation(club_id=club.id, user_id=user.id, stars=invoice.stars_amount, coins=coins, invoice_id=invoice.id))
    managers = (await db.execute(
        select(ClubMember.user_id).where(
            ClubMember.club_id == club.id, ClubMember.role == ClubRole.captain, ClubMember.user_id != user.id,
        )
    )).scalars().all()
    for manager_id in managers:
        await notify(
            db, manager_id, NotificationType.club_donation, "Казна клуба пополнена",
            f"{donor} пополнил бюджет «{club.name}» на {coins} монет",
        )
    return {"kind": "club_donation", "coins": coins, "club_name": club.name}
