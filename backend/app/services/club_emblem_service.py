"""Club emblem constructor: shape + colour stay free; the layers on top
(second colour, patterns, letters for club-budget coins; symbols, outlines
and animated effects for Telegram Stars) are unlocked per club from the
`club_emblem_items` catalog, then the captain puts them on.

Coin items are paid from the club budget by the captain or an assistant
(the club spends its own treasury, see club_treasury_service for topping it
up with Stars). Stars items may be bought by any member as a gift to the
club — "club_emblem:<club_id>:<item_id>" through shop_product_service."""
import logging
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.club import Club, ClubMember
from app.models.club_emblem import ClubEmblemItem, ClubEmblemUnlock
from app.models.enums import ClubBudgetTransactionType, ClubRole
from app.models.user import User
from app.schemas.club_emblem import (
    ClubEmblemCatalogItemOut,
    ClubEmblemItemIn,
    ClubEmblemItemOut,
    ClubEmblemOut,
    ClubEmblemStateOut,
    ClubEmblemUpdateIn,
)
from app.services.club_budget_service import debit_club_budget
from app.services.game_config_service import get_config

logger = logging.getLogger(__name__)

# (kind, style_key, name, coins_price, stars_price) — the frontend draws each
# style_key (lib/clubEmblem.ts). Inserted on first use; after that the admin
# panel owns name/prices/active. A new style needs a row here and its drawing.
DEFAULT_CATALOG: list[tuple[str, str, str, int, int]] = [
    ("color2", "second_color", "Второй цвет", 2000, 0),
    ("pattern", "stripes", "Полосы", 2500, 0),
    ("pattern", "halves", "Половины", 2500, 0),
    ("pattern", "sash", "Лента", 2500, 0),
    ("pattern", "checker", "Клетка", 3000, 0),
    ("pattern", "chevron", "Шеврон", 3000, 0),
    ("pattern", "diamonds", "Ромбы", 3000, 0),
    ("letters", "letters", "Буквы клуба", 3000, 0),
    ("symbol", "ball", "Мяч", 0, 75),
    ("symbol", "crown", "Корона", 0, 75),
    ("symbol", "lion", "Лев", 0, 75),
    ("symbol", "eagle", "Орёл", 0, 75),
    ("symbol", "lightning", "Молния", 0, 75),
    ("symbol", "castle", "Замок", 0, 75),
    ("outline", "bronze", "Бронзовая обводка", 0, 50),
    ("outline", "silver", "Серебряная обводка", 0, 75),
    ("outline", "gold", "Золотая обводка", 0, 100),
    ("outline", "neon", "Неоновая обводка", 0, 100),
    ("effect", "shine", "Блеск", 0, 150),
    ("effect", "flame", "Пламя", 0, 150),
    ("effect", "sparkle", "Звёздное мерцание", 0, 150),
]

# Club column per kind (color2 / letters hold a free value; the unlock is the item itself).
_COLUMN_BY_KIND = {
    "pattern": "logo_pattern", "symbol": "logo_symbol", "outline": "logo_outline", "effect": "logo_effect",
}
_LETTERS_RE = re.compile(r"^[A-ZА-ЯЁ0-9]{1,3}$")


def emblem_out(club: Club) -> ClubEmblemOut:
    return ClubEmblemOut(
        color2=club.logo_color2, pattern=club.logo_pattern, symbol=club.logo_symbol, letters=club.logo_letters,
        outline=club.logo_outline, outline_thin=bool(club.logo_outline_thin), effect=club.logo_effect,
    )


async def ensure_catalog(db: AsyncSession) -> None:
    """Adds the DEFAULT_CATALOG rows that don't exist yet (never touches
    existing ones — those belong to the admin). Flushes, doesn't commit."""
    existing = {
        (k, s) for k, s in (await db.execute(select(ClubEmblemItem.kind, ClubEmblemItem.style_key))).all()
    }
    for order, (kind, style, name, coins, stars) in enumerate(DEFAULT_CATALOG):
        if (kind, style) in existing:
            continue
        try:
            async with db.begin_nested():
                db.add(ClubEmblemItem(
                    kind=kind, style_key=style, name=name, coins_price=coins, stars_price=stars, sort_order=order,
                ))
                await db.flush()
        except IntegrityError:
            pass  # a concurrent request inserted it first


async def _catalog(db: AsyncSession) -> list[ClubEmblemItem]:
    await ensure_catalog(db)
    return list((await db.execute(
        select(ClubEmblemItem).order_by(ClubEmblemItem.sort_order, ClubEmblemItem.id)
    )).scalars())


async def unlocked_item_ids(db: AsyncSession, club_id: int) -> set[int]:
    rows = await db.execute(select(ClubEmblemUnlock.item_id).where(ClubEmblemUnlock.club_id == club_id))
    return {r[0] for r in rows.all()}


async def _membership(db: AsyncSession, user_id: int) -> ClubMember:
    membership = (await db.execute(select(ClubMember).where(ClubMember.user_id == user_id))).scalar_one_or_none()
    if membership is None:
        raise NotFoundError("Ты не состоишь в клубе")
    return membership


def _can_spend_budget(membership: ClubMember) -> bool:
    return membership.role in (ClubRole.captain, ClubRole.assistant)


async def get_state(db: AsyncSession, user: User) -> ClubEmblemStateOut:
    membership = await _membership(db, user.id)
    club = await db.get(Club, membership.club_id)
    config = await get_config(db)
    items = await _catalog(db)
    unlocked = await unlocked_item_ids(db, club.id)
    await db.commit()  # persists a freshly ensured catalog
    return ClubEmblemStateOut(
        enabled=config.club_emblems_enabled, club_id=club.id, logo_shape=club.logo_shape, logo_color=club.logo_color,
        emblem=emblem_out(club),
        items=[
            ClubEmblemCatalogItemOut(**ClubEmblemItemOut.model_validate(i).model_dump(), unlocked=i.id in unlocked)
            for i in items
            # Switched-off items only stay visible to a club that already owns them.
            if i.is_active or i.id in unlocked
        ],
        budget=club.budget, can_edit=membership.role == ClubRole.captain,
        can_spend_budget=_can_spend_budget(membership),
    )


async def _lock_club(db: AsyncSession, club_id: int) -> Club:
    club = (await db.execute(
        select(Club).where(Club.id == club_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if club is None or club.is_disbanded:
        raise NotFoundError("Клуб не найден")
    return club


async def buy_with_budget(db: AsyncSession, user: User, item_id: int) -> ClubEmblemStateOut:
    config = await get_config(db)
    if not config.club_emblems_enabled:
        raise ConflictError("Конструктор эмблем сейчас недоступен")
    membership = await _membership(db, user.id)
    if not _can_spend_budget(membership):
        raise ForbiddenError("Тратить бюджет клуба могут капитан и ассистенты")
    item = await db.get(ClubEmblemItem, item_id)
    if item is None:
        raise NotFoundError("Элемент не найден")
    if not item.is_active:
        raise ConflictError("Этот элемент не продаётся")
    if item.coins_price <= 0:
        raise ConflictError("Этот элемент продаётся только за звёзды")
    club = await _lock_club(db, membership.club_id)
    if item.id in await unlocked_item_ids(db, club.id):
        raise ConflictError("Уже открыто")
    await debit_club_budget(
        db, club, item.coins_price, ClubBudgetTransactionType.emblem_purchase, f"Эмблема: {item.name}",
        related_object_type="club_emblem_item", related_object_id=item.id, actor_user_id=user.id,
    )
    db.add(ClubEmblemUnlock(club_id=club.id, item_id=item.id, source="coins", user_id=user.id))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("Уже открыто")
    return await get_state(db, user)


async def update_emblem(db: AsyncSession, user: User, payload: ClubEmblemUpdateIn) -> ClubEmblemStateOut:
    membership = await _membership(db, user.id)
    if membership.role != ClubRole.captain:
        raise ForbiddenError("Эмблему меняет капитан")
    club = await _lock_club(db, membership.club_id)
    items = {(i.kind, i.style_key): i for i in await _catalog(db)}
    unlocked = await unlocked_item_ids(db, club.id)

    def require(kind: str, style: str, label: str) -> None:
        item = items.get((kind, style))
        if item is None:
            raise ConflictError(f"Неизвестный элемент эмблемы: {label}")
        if item.id not in unlocked:
            raise ConflictError(f"Сначала открой «{item.name}»")

    if payload.color2 is not None:
        require("color2", "second_color", "второй цвет")
    letters = None
    if payload.letters:
        letters = payload.letters.strip().upper()
        if not _LETTERS_RE.match(letters):
            raise ConflictError("Буквы эмблемы: от 1 до 3 букв или цифр")
        require("letters", "letters", "буквы")
    for kind, column in _COLUMN_BY_KIND.items():
        value = getattr(payload, kind)
        if value is not None:
            require(kind, value, value)
        setattr(club, column, value)

    club.logo_shape = payload.logo_shape
    club.logo_color = payload.logo_color
    club.logo_color2 = payload.color2
    club.logo_letters = letters
    club.logo_outline_thin = payload.outline_thin
    db.add(club)
    await db.commit()
    return await get_state(db, user)


# --- Stars ("club_emblem:<club_id>:<item_id>", see shop_product_service) -------------------


async def stars_order(db: AsyncSession, user: User, item_id: int) -> tuple[str, int, str, str]:
    config = await get_config(db)
    if not config.club_emblems_enabled:
        raise ConflictError("Конструктор эмблем сейчас недоступен")
    membership = await _membership(db, user.id)
    club = await db.get(Club, membership.club_id)
    item = await db.get(ClubEmblemItem, item_id)
    if item is None:
        raise NotFoundError("Элемент не найден")
    if not item.is_active or item.stars_price <= 0:
        raise ConflictError("Этот элемент не продаётся за звёзды")
    if item.id in await unlocked_item_ids(db, club.id):
        raise ConflictError("Уже открыто")
    return (
        f"club_emblem:{club.id}:{item.id}", item.stars_price, item.name,
        f"Элемент эмблемы «{item.name}» для клуба «{club.name}» — навсегда. Только внешний вид, на игру не влияет.",
    )


def _parse(arg: str) -> tuple[int, int]:
    club_id, _, item_id = arg.partition(":")
    return int(club_id), int(item_id)


async def validate_stars(db: AsyncSession, user_id: int, arg: str, stars_amount: int) -> tuple[bool, str]:
    club_id, item_id = _parse(arg)
    config = await get_config(db)
    item = await db.get(ClubEmblemItem, item_id)
    if not config.club_emblems_enabled or item is None or not item.is_active or item.stars_price != stars_amount:
        return False, "Этот элемент больше не продаётся"
    club = await db.get(Club, club_id)
    if club is None or club.is_disbanded:
        return False, "Клуб не найден"
    membership = (await db.execute(select(ClubMember).where(ClubMember.user_id == user_id))).scalar_one_or_none()
    if membership is None or membership.club_id != club_id:
        return False, "Ты больше не в этом клубе"
    if item_id in await unlocked_item_ids(db, club_id):
        return False, "Клуб уже открыл этот элемент"
    return True, ""


async def deliver_stars(db: AsyncSession, user: User, arg: str) -> dict:
    """Payment is already taken: unlock unconditionally (idempotent)."""
    club_id, item_id = _parse(arg)
    item = await db.get(ClubEmblemItem, item_id)
    if item_id in await unlocked_item_ids(db, club_id):
        # Two members paid for the same item at once — visible in admin «Платежи Stars».
        logger.warning("club_emblem: club %s already had item %s (paid by user %s)", club_id, item_id, user.id)
    else:
        try:
            async with db.begin_nested():
                db.add(ClubEmblemUnlock(club_id=club_id, item_id=item_id, source="stars", user_id=user.id))
                await db.flush()
        except IntegrityError:
            pass
    return {"kind": "club_emblem", "name": item.name if item else "Эмблема"}


# --- admin ------------------------------------------------------------------------------


async def admin_list(db: AsyncSession) -> list[ClubEmblemItemOut]:
    items = await _catalog(db)
    await db.commit()
    return [ClubEmblemItemOut.model_validate(i) for i in items]


async def admin_update(db: AsyncSession, item_id: int, data: ClubEmblemItemIn) -> ClubEmblemItemOut:
    item = await db.get(ClubEmblemItem, item_id)
    if item is None:
        raise NotFoundError("Элемент не найден")
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    await db.commit()
    await db.refresh(item)
    return ClubEmblemItemOut.model_validate(item)

