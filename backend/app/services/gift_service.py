from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models.enums import CardSource, GiftKind, NotificationType, TransactionType
from app.models.gift import Gift, GiftSet
from app.models.card import UserCard
from app.models.notification import Notification
from app.models.pack import StarsInvoice
from app.models.user import User
from app.schemas.gift import GiftClaimResult, GiftOut, GiftPurchaseResult, GiftSetOut
from app.services import collection_service
from app.services.pack_service import grant_bonus_pack_opening
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update


async def list_active_gift_sets(db: AsyncSession) -> list[GiftSetOut]:
    result = await db.execute(select(GiftSet).where(GiftSet.is_active.is_(True)).order_by(GiftSet.sort_order))
    return [GiftSetOut.model_validate(g) for g in result.scalars().all()]


async def list_my_gifts(db: AsyncSession, user: User) -> list[GiftOut]:
    result = await db.execute(
        select(Gift)
        .where(Gift.recipient_id == user.id)
        .order_by(Gift.claimed_at.is_not(None), Gift.created_at.desc())
    )
    return [GiftOut.model_validate(g) for g in result.scalars().all()]


async def reserve_gift_serial_numbers(db: AsyncSession, gift_set: GiftSet, count: int = 1) -> Optional[int]:
    """Atomically reserves `count` consecutive serial numbers on a
    collectible gift_set and returns the first one — None for a bundle,
    which is never numbered. Row-locks gift_set so concurrent mints (two
    purchases, or a purchase racing an admin broadcast) can't hand out the
    same number. Enforces max_supply; raises rather than partially
    fulfilling an over-capacity request."""
    if gift_set.kind != GiftKind.collectible:
        return None
    result = await db.execute(
        select(GiftSet)
        .where(GiftSet.id == gift_set.id)
        .with_for_update(of=GiftSet)
        .execution_options(populate_existing=True)
    )
    locked = result.scalar_one()
    start = locked.next_serial_number
    end = start + count - 1
    if locked.max_supply is not None and end > locked.max_supply:
        remaining = max(0, locked.max_supply - start + 1)
        raise ConflictError(f"Недостаточно тиража: осталось {remaining}, а нужно {count}")
    locked.next_serial_number = end + 1
    db.add(locked)
    return start


async def bought_with_stars(db: AsyncSession, gift_id: int) -> bool:
    """A player paid Stars for this gift (its invoice was delivered)."""
    return (await db.execute(
        select(StarsInvoice.id).where(StarsInvoice.gift_id == gift_id).limit(1)
    )).scalar_one_or_none() is not None


async def claim_gift(db: AsyncSession, user: User, gift_id: int) -> GiftClaimResult:
    """Opens a pending gift — reward is only granted once the recipient
    explicitly claims it (never on receipt), mirroring opening a pack. Row
    locks the gift before checking claimed_at so two concurrent claim taps
    (e.g. a double-tap) can't both pass the check and deliver twice.

    Both gift kinds share this exact reward logic: a collectible with no
    configured coins_amount/pack_id just claims with nothing granted (the
    common case — the row's existence is its own reward); one with a prize
    configured grants it exactly like a bundle does."""
    result = await db.execute(
        select(Gift).where(Gift.id == gift_id).with_for_update(of=Gift).execution_options(populate_existing=True)
    )
    gift = result.scalar_one_or_none()
    if gift is None or gift.recipient_id != user.id:
        raise NotFoundError("Gift not found")
    if gift.claimed_at is not None:
        raise ConflictError("This gift was already claimed")

    gift_set = gift.gift_set

    pack_result = None
    # Several packs (pack_count) show up as one result with every card.
    for n in range(max(1, gift_set.pack_count or 1) if gift_set.pack_id is not None else 0):
        granted = await grant_bonus_pack_opening(
            db, user, gift_set.pack_id, idempotency_prefix=f"gift-{gift.id}-{n}", source=CardSource.gift,
        )
        if granted is None:
            break
        granted.collection_rewards = await collection_service.grant_collection_rewards_for_new_cards(
            db, user, [item.card.player.id for item in granted.cards]
        )
        if pack_result is None:
            gift.pack_opening_id = granted.opening_id
            pack_result = granted
        else:
            for field in ("cards", "coach_cards", "stadium_cards", "skill_tokens", "muses", "collection_rewards"):
                getattr(pack_result, field).extend(getattr(granted, field))

    if pack_result is not None and pack_result.cards and await bought_with_stars(db, gift.id):
        # Someone paid real Stars for it: like a Stars pack, its cards are
        # free (tradeable once the owner is a «проверенный аккаунт»). Admin
        # gifts stay bound (CardSource.gift is in BOUND_SOURCES).
        card_ids = [item.card.id for item in pack_result.cards]
        await db.execute(update(UserCard).where(UserCard.id.in_(card_ids)).values(from_free_source=False))
        for item in pack_result.cards:
            item.card.from_free_source = False

    if gift_set.coins_amount:
        user = await lock_user_for_update(db, user.id)
        await credit_coins(
            db, user, gift_set.coins_amount, TransactionType.gift_coins,
            f"Подарок «{gift_set.name}»", related_object_type="gift", related_object_id=gift.id,
        )

    gift.claimed_at = datetime.now(timezone.utc)
    db.add(gift)
    await db.commit()
    await db.refresh(user)
    await db.refresh(gift)

    if pack_result is not None:
        pack_result.new_balance = user.balance

    return GiftClaimResult(
        gift=GiftOut.model_validate(gift), pack_result=pack_result,
        coins_credited=gift_set.coins_amount, new_balance=user.balance,
    )


async def admin_send_gift_to_user(db: AsyncSession, gift_set_id: int, user_id: int, message: Optional[str]) -> GiftOut:
    gift_set = await db.get(GiftSet, gift_set_id)
    if gift_set is None:
        raise NotFoundError("Gift set not found")
    recipient = await db.get(User, user_id)
    if recipient is None:
        raise NotFoundError("User not found")

    serial_number = await reserve_gift_serial_numbers(db, gift_set)

    gift = Gift(
        gift_set_id=gift_set.id, sender_id=None, recipient_id=recipient.id, message=message,
        is_admin_gift=True, serial_number=serial_number,
    )
    db.add(gift)
    db.add(
        Notification(
            user_id=recipient.id, type=NotificationType.admin_message,
            title="🎁 Подарок!", body=message or "Тебе подарок в приложении — открой и забери!",
        )
    )
    await db.commit()
    await db.refresh(gift)
    return GiftOut.model_validate(gift)


async def admin_broadcast_gift(db: AsyncSession, gift_set_id: int, message: Optional[str]) -> int:
    """Grants gift_set_id free to every registered user (a holiday-style
    giveaway) via a single bulk INSERT rather than one ORM object per user.

    Also queues a real Telegram notification per recipient (same
    Notification table + notifier.py delivery path as
    broadcast_service.send_update_broadcast), so the bulk grant doesn't sit
    silently in-app — recipients are paced at notifier.py's rate limit
    rather than pinged all at once. The gift itself still goes to every
    user regardless of bot_blocked (it's a real in-app grant, unaffected
    by whether Telegram can reach them) — only the Telegram notification
    is skipped for users who've blocked the bot, since it would never
    be delivered."""
    gift_set = await db.get(GiftSet, gift_set_id)
    if gift_set is None:
        raise NotFoundError("Gift set not found")

    user_rows = (await db.execute(select(User.id, User.bot_blocked))).all()
    if not user_rows:
        return 0
    user_ids = [row[0] for row in user_rows]
    notifiable_user_ids = [row[0] for row in user_rows if not row[1]]

    start_serial = await reserve_gift_serial_numbers(db, gift_set, count=len(user_ids))

    now = datetime.now(timezone.utc)
    await db.execute(
        insert(Gift),
        [
            {
                "gift_set_id": gift_set.id, "sender_id": None, "recipient_id": uid,
                "message": message, "is_admin_gift": True, "claimed_at": None,
                "serial_number": (start_serial + i) if start_serial is not None else None,
                "created_at": now, "updated_at": now,
            }
            for i, uid in enumerate(user_ids)
        ],
    )
    if notifiable_user_ids:
        await db.execute(
            insert(Notification),
            [
                {
                    "user_id": uid, "type": NotificationType.admin_message,
                    "title": "🎁 Подарок!", "body": message or "Тебе подарок в приложении — открой и забери!",
                    "is_read": False, "telegram_sent": False, "created_at": now,
                }
                for uid in notifiable_user_ids
            ],
        )
    await db.commit()
    return len(user_ids)


async def buy_collectible_with_coins(
    db: AsyncSession, buyer: User, gift_set_id: int, recipient_id: int, message: Optional[str],
) -> GiftPurchaseResult:
    gift_set = await db.get(GiftSet, gift_set_id)
    if gift_set is None:
        raise NotFoundError("Gift set not found")
    if not gift_set.is_active:
        raise ConflictError("This gift is not currently available")
    if gift_set.kind != GiftKind.collectible:
        raise ConflictError("This gift can only be bought with Stars")
    if gift_set.coins_price <= 0:
        raise ConflictError("This gift cannot be bought with coins")

    recipient = await db.get(User, recipient_id)
    if recipient is None:
        raise NotFoundError("Recipient not found")

    buyer = await lock_user_for_update(db, buyer.id)
    serial_number = await reserve_gift_serial_numbers(db, gift_set)
    await debit_coins(
        db, buyer, gift_set.coins_price, TransactionType.gift_purchase_coins,
        f"Подарок «{gift_set.name}»", related_object_type="gift_set", related_object_id=gift_set.id,
    )

    gift = Gift(
        gift_set_id=gift_set.id, sender_id=buyer.id, recipient_id=recipient.id, message=message,
        is_admin_gift=False, serial_number=serial_number,
    )
    db.add(gift)
    await db.commit()
    await db.refresh(buyer)
    await db.refresh(gift)

    return GiftPurchaseResult(gift=GiftOut.model_validate(gift), new_balance=buyer.balance)


async def set_gift_pinned(db: AsyncSession, user: User, gift_id: int, pinned: bool) -> GiftOut:
    result = await db.execute(
        select(Gift).where(Gift.id == gift_id).with_for_update(of=Gift).execution_options(populate_existing=True)
    )
    gift = result.scalar_one_or_none()
    if gift is None or gift.recipient_id != user.id:
        raise NotFoundError("Gift not found")
    if gift.gift_set.kind != GiftKind.collectible:
        raise ConflictError("Only collectible gifts can be pinned")
    if gift.claimed_at is None:
        raise ConflictError("This gift hasn't been claimed yet")

    if pinned and not gift.is_pinned:
        pinned_count = (
            await db.execute(
                select(func.count()).select_from(Gift).where(Gift.recipient_id == user.id, Gift.is_pinned.is_(True))
            )
        ).scalar_one()
        if pinned_count >= 3:
            raise ConflictError("You can only pin up to 3 gifts — unpin one first")
        gift.is_pinned = True
        gift.pinned_at = datetime.now(timezone.utc)
    elif not pinned:
        gift.is_pinned = False
        gift.pinned_at = None

    db.add(gift)
    await db.commit()
    await db.refresh(gift)
    return GiftOut.model_validate(gift)


# --- passing owned copies on: Telegram Stars only -----------------------------------
# Keys: "gift_batch:<batch>" (rows in gift_transfers, one or many copies, an
# optional note) and the first version's "gift_transfer:<gift id>:<recipient id>"
# (still delivered for invoices created before the batches).

MAX_BATCH = 50


def special_serial(n: Optional[int]) -> Optional[str]:
    """A serial worth showing off; the TS twin is lib/giftSerial.ts (same cases
    in both tests). Codes in rarity order — see SPECIAL_ORDER."""
    if n is None or n < 1:
        return None
    s = str(n)
    if n == 1:
        return "first"
    if set(s) == {"7"}:
        return "lucky"
    if n >= 10 and s == "1" + "0" * (len(s) - 1):
        return "jubilee"
    if len(s) >= 2 and len(set(s)) == 1:
        return "twins"
    if n % 100 == 0:
        return "round"
    if len(s) >= 3 and s == s[::-1]:
        return "mirror"
    return None


SPECIAL_ORDER = ["first", "lucky", "jubilee", "twins", "round", "mirror"]


async def _transferable_gift(db: AsyncSession, owner_id: int, gift_id: int, lock: bool = False) -> Gift:
    query = select(Gift).where(Gift.id == gift_id)
    if lock:
        query = query.with_for_update(of=Gift).execution_options(populate_existing=True)
    gift = (await db.execute(query)).scalar_one_or_none()
    if gift is None or gift.recipient_id != owner_id:
        raise NotFoundError("Подарок не найден")
    if gift.gift_set.kind != GiftKind.collectible or gift.claimed_at is None:
        raise ConflictError("Передать можно только открытый коллекционный подарок")
    return gift


async def _transfer_recipient(db: AsyncSession, owner_id: int, recipient_id: int) -> User:
    if recipient_id == owner_id:
        raise ConflictError("Нельзя передать подарок самому себе")
    recipient = await db.get(User, recipient_id)
    if recipient is None or recipient.is_banned:
        raise NotFoundError("Игрок не найден")
    return recipient


async def transfer_price(db: AsyncSession) -> int:
    from app.services.game_config_service import get_config

    return max(1, int((await get_config(db)).gift_transfer_stars))


def _gifts_word(n: int) -> str:
    d10, d100 = n % 10, n % 100
    word = "подарок" if d10 == 1 and d100 != 11 else "подарка" if 2 <= d10 <= 4 and not 12 <= d100 <= 14 else "подарков"
    return f"{n} {word}"


def _serials(gifts: list[Gift]) -> str:
    nums = [f"№{g.serial_number}" for g in gifts if g.serial_number is not None]
    if len(nums) > 6:
        return ", ".join(nums[:6]) + f" и ещё {len(nums) - 6}"
    return ", ".join(nums)


async def create_batch_transfer_invoice(
    db: AsyncSession, user: User, gift_ids: list[int], recipient_id: int, message: Optional[str] = None,
):
    """Copies the user owns go to another player — paid with Stars only
    (price × copies), never coins. Nothing moves until the payment is
    delivered; the copies wait in pending gift_transfers rows of one batch."""
    import secrets

    from app.models.gift import GiftTransfer
    from app.services import shop_product_service

    ids = list(dict.fromkeys(gift_ids))
    if not ids or len(ids) > MAX_BATCH:
        raise ConflictError(f"За раз можно передать от 1 до {MAX_BATCH} подарков")
    gifts = [await _transferable_gift(db, user.id, gid) for gid in ids]
    recipient = await _transfer_recipient(db, user.id, recipient_id)
    note = (message or "").strip()[:200] or None
    stars = await transfer_price(db) * len(gifts)
    batch = secrets.token_hex(8)
    for g in gifts:
        db.add(GiftTransfer(batch=batch, gift_id=g.id, from_user_id=user.id, to_user_id=recipient.id, message=note))
    await db.flush()
    names = sorted({g.gift_set.name for g in gifts})
    what = f"«{names[0]}»" if len(names) == 1 else f"{len(names)} видов"
    title = f"Передача подарка {what}" if len(gifts) == 1 else f"Передача: {_gifts_word(len(gifts))}"
    return await shop_product_service.create_invoice(
        db, user, f"gift_batch:{batch}", stars, title[:32],
        f"Подарки {what} ({_serials(gifts)}) перейдут к игроку {recipient.full_display_name()}.",
    )


async def create_transfer_invoice(db: AsyncSession, user: User, gift_id: int, recipient_id: int):
    return await create_batch_transfer_invoice(db, user, [gift_id], recipient_id)


async def _batch_rows(db: AsyncSession, batch: str):
    from app.models.gift import GiftTransfer

    return list((await db.execute(
        select(GiftTransfer).where(GiftTransfer.batch == batch).order_by(GiftTransfer.id)
    )).scalars().all())


async def _check_batch(db: AsyncSession, user_id: int, rows) -> None:
    if not rows or any(r.status != "pending" for r in rows):
        raise ConflictError("Эта передача уже не действует")
    for r in rows:
        await _transferable_gift(db, user_id, r.gift_id)
    await _transfer_recipient(db, user_id, rows[0].to_user_id)


async def validate_batch_stars(db: AsyncSession, user_id: int, batch: str, stars_amount: int) -> tuple[bool, str]:
    rows = await _batch_rows(db, batch)
    try:
        await _check_batch(db, user_id, rows)
    except AppError as exc:
        return False, exc.message
    if stars_amount < await transfer_price(db) * len(rows):
        return False, "Цена передачи изменилась — попробуй ещё раз"
    return True, ""


def _transfer_args(arg: str) -> tuple[int, int]:
    gift_id, _, recipient_id = arg.partition(":")
    return int(gift_id), int(recipient_id)


async def validate_transfer_stars(db: AsyncSession, user_id: int, arg: str, stars_amount: int) -> tuple[bool, str]:
    gift_id, recipient_id = _transfer_args(arg)
    try:
        await _transferable_gift(db, user_id, gift_id)
        await _transfer_recipient(db, user_id, recipient_id)
    except AppError as exc:
        return False, exc.message
    if stars_amount < await transfer_price(db):
        return False, "Цена передачи изменилась — попробуй ещё раз"
    return True, ""


async def _move(db: AsyncSession, user: User, gift_ids: list[int], recipient_id: int, message: Optional[str], rows=None) -> list[Gift]:
    """Already paid: each copy changes owner under its row lock. It keeps its
    serial and stays claimed (its prize was already taken), comes unpinned and
    unseen, and the payer becomes its sender. The caller commits."""
    from app.models.gift import GiftTransfer
    from app.services.notification_service import notify

    now = datetime.now(timezone.utc)
    by_gift = {r.gift_id: r for r in rows or []}
    moved = []
    for gid in sorted(gift_ids):
        gift = await _transferable_gift(db, user.id, gid, lock=True)
        row = by_gift.get(gid)
        if row is None:
            row = GiftTransfer(batch=f"single-{gid}-{int(now.timestamp())}", gift_id=gid, from_user_id=user.id,
                               to_user_id=recipient_id, message=message)
            db.add(row)
        row.prev_sender_id = gift.sender_id
        row.status = "done"
        row.completed_at = now
        gift.recipient_id = recipient_id
        gift.sender_id = user.id
        gift.message = message
        gift.is_admin_gift = False
        gift.is_pinned = False
        gift.pinned_at = None
        gift.transfer_unseen = True
        db.add(gift)
        moved.append(gift)
    name = moved[0].gift_set.name
    if len(moved) == 1:
        serial = f" №{moved[0].serial_number}" if moved[0].serial_number is not None else ""
        body = f"{user.full_display_name()} передал(а) тебе подарок «{name}»{serial}."
    else:
        body = f"{user.full_display_name()} передал(а) тебе {_gifts_word(len(moved))}: {_serials(moved)}."
    if message:
        body += f" «{message}»"
    await notify(
        db, recipient_id, NotificationType.admin_message, "🎁 Тебе передали подарок", body,
        related_object_type="gift", related_object_id=moved[0].id,
    )
    return moved


async def deliver_batch_stars(db: AsyncSession, user: User, batch: str) -> dict:
    rows = await _batch_rows(db, batch)
    if not rows or any(r.status != "pending" for r in rows):
        raise ConflictError("Эта передача уже не действует")
    moved = await _move(db, user, [r.gift_id for r in rows], rows[0].to_user_id, rows[0].message, rows)
    return {"kind": "gift_batch", "count": len(moved), "serials": [g.serial_number for g in moved]}


async def deliver_transfer_stars(db: AsyncSession, user: User, arg: str) -> dict:
    gift_id, recipient_id = _transfer_args(arg)
    moved = await _move(db, user, [gift_id], recipient_id, None)
    return {"kind": "gift_transfer", "name": moved[0].gift_set.name, "serial_number": moved[0].serial_number}


async def mark_transfers_seen(db: AsyncSession, user: User) -> int:
    result = await db.execute(
        update(Gift).where(Gift.recipient_id == user.id, Gift.transfer_unseen.is_(True)).values(transfer_unseen=False)
    )
    await db.commit()
    return result.rowcount or 0


# --- a copy's story, the profile shelf and the collectors' table -------------------------


async def gift_history(db: AsyncSession, user: User, gift_id: int):
    from app.models.gift import GiftTransfer
    from app.schemas.gift import GiftHistoryEntry, GiftHistoryOut
    from app.schemas.user import UserPublicOut

    gift = await db.get(Gift, gift_id)
    if gift is None or gift.recipient_id != user.id:
        raise NotFoundError("Подарок не найден")
    rows = list((await db.execute(
        select(GiftTransfer).where(GiftTransfer.gift_id == gift_id, GiftTransfer.status == "done")
        .order_by(GiftTransfer.completed_at, GiftTransfer.id)
    )).scalars().all())
    ids = {i for r in rows for i in (r.from_user_id, r.to_user_id, r.prev_sender_id) if i}
    first_sender = rows[0].prev_sender_id if rows else gift.sender_id
    first_owner = rows[0].from_user_id if rows else gift.recipient_id
    ids |= {i for i in (first_sender, first_owner) if i}
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()} if ids else {}

    def pub(uid):
        return UserPublicOut.model_validate(users[uid]) if uid in users else None

    entries = [GiftHistoryEntry(
        kind="issued", at=gift.created_at, from_user=pub(first_sender), to_user=pub(first_owner),
        message=None,
    )]
    for r in rows:
        entries.append(GiftHistoryEntry(
            kind="transfer", at=r.completed_at, from_user=pub(r.from_user_id), to_user=pub(r.to_user_id), message=r.message,
        ))
    return GiftHistoryOut(gift_id=gift.id, serial_number=gift.serial_number, entries=entries)


def _owned_collectibles():
    return (
        select(Gift.id, Gift.recipient_id, Gift.gift_set_id, Gift.serial_number, Gift.is_pinned)
        .join(GiftSet, GiftSet.id == Gift.gift_set_id)
        .where(GiftSet.kind == GiftKind.collectible, Gift.claimed_at.is_not(None))
    )


SHELF_SIZE = 6


async def gift_shelf(db: AsyncSession, user_id: int):
    """«Полка подарков» on a profile: pinned copies first, then the rarest
    serials, one copy per set; plus totals. Notes and senders stay private."""
    from app.schemas.gift import GiftShelfItem, GiftShelfOut

    rows = (await db.execute(_owned_collectibles().where(Gift.recipient_id == user_id))).all()
    rank = {code: i for i, code in enumerate(SPECIAL_ORDER)}

    def key(r):
        sp = special_serial(r.serial_number)
        return (0 if r.is_pinned else 1, rank.get(sp, 99), r.serial_number or 10**9)

    picked, seen_sets = [], set()
    for r in sorted(rows, key=key):
        if r.gift_set_id in seen_sets:
            continue
        if not r.is_pinned and special_serial(r.serial_number) is None and len(picked) >= 3:
            continue
        seen_sets.add(r.gift_set_id)
        picked.append(r)
        if len(picked) >= SHELF_SIZE:
            break
    sets = {s.id: s for s in (await db.execute(
        select(GiftSet).where(GiftSet.id.in_({r.gift_set_id for r in picked}))
    )).scalars().all()} if picked else {}
    return GiftShelfOut(
        sets=len({r.gift_set_id for r in rows}),
        copies=len(rows),
        special=sum(1 for r in rows if special_serial(r.serial_number)),
        items=[
            GiftShelfItem(
                id=r.id, gift_set=GiftSetOut.model_validate(sets[r.gift_set_id]), serial_number=r.serial_number,
                is_pinned=r.is_pinned, special=special_serial(r.serial_number),
            )
            for r in picked
        ],
    )


LEADERBOARD_SIZE = 20


async def gift_leaderboard(db: AsyncSession, user: User):
    """Collectors of collectible gifts: different sets, then copies; the
    special serials are counted for the shown rows only."""
    from app.schemas.gift import GiftLeaderboardOut, GiftLeaderRow
    from app.schemas.user import UserPublicOut

    owned = _owned_collectibles().subquery()
    sets_col = func.count(func.distinct(owned.c.gift_set_id))
    copies_col = func.count(owned.c.id)
    totals = (await db.execute(
        select(owned.c.recipient_id, sets_col.label("sets"), copies_col.label("copies"))
        .join(User, User.id == owned.c.recipient_id)
        .where(User.is_banned.is_(False))
        .group_by(owned.c.recipient_id)
        .order_by(sets_col.desc(), copies_col.desc(), owned.c.recipient_id)
    )).all()
    place_of = {r.recipient_id: i + 1 for i, r in enumerate(totals)}
    shown = totals[:LEADERBOARD_SIZE]
    my = next((r for r in totals if r.recipient_id == user.id), None)
    ids = {r.recipient_id for r in shown} | ({my.recipient_id} if my else set())
    serials = (await db.execute(
        select(owned.c.recipient_id, owned.c.serial_number).where(owned.c.recipient_id.in_(ids))
    )).all() if ids else []
    special: dict[int, int] = {}
    for uid, n in serials:
        if special_serial(n):
            special[uid] = special.get(uid, 0) + 1
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()} if ids else {}

    def row(r):
        return GiftLeaderRow(
            place=place_of[r.recipient_id], user=UserPublicOut.model_validate(users[r.recipient_id]),
            sets=r.sets, copies=r.copies, special=special.get(r.recipient_id, 0),
        )

    return GiftLeaderboardOut(rows=[row(r) for r in shown], me=row(my) if my else None)



async def admin_transfer_stats(db: AsyncSession, days: int = 30) -> dict:
    """Admin: what passing gifts on brings — Stars paid for completed transfer
    invoices, copies moved, distinct senders and the most passed-on sets."""
    from datetime import timedelta

    from sqlalchemy import or_

    from app.models.gift import GiftTransfer

    since = datetime.now(timezone.utc) - timedelta(days=days)
    paid = or_(StarsInvoice.shop_product.like("gift_batch:%"), StarsInvoice.shop_product.like("gift_transfer:%"))
    stars, invoices = (await db.execute(
        select(func.coalesce(func.sum(StarsInvoice.stars_amount), 0), func.count(StarsInvoice.id))
        .where(paid, StarsInvoice.completed_at.is_not(None), StarsInvoice.completed_at >= since)
    )).one()
    done = (GiftTransfer.status == "done", GiftTransfer.completed_at >= since)
    copies, senders = (await db.execute(
        select(func.count(GiftTransfer.id), func.count(func.distinct(GiftTransfer.from_user_id))).where(*done)
    )).one()
    top = (await db.execute(
        select(GiftSet.name, func.count(GiftTransfer.id).label("n"))
        .join(Gift, Gift.id == GiftTransfer.gift_id).join(GiftSet, GiftSet.id == Gift.gift_set_id)
        .where(*done).group_by(GiftSet.name).order_by(func.count(GiftTransfer.id).desc()).limit(5)
    )).all()
    return {
        "days": days, "stars": int(stars or 0), "invoices": int(invoices or 0), "copies": int(copies or 0),
        "senders": int(senders or 0), "top_sets": [{"name": name, "copies": n} for name, n in top],
    }
